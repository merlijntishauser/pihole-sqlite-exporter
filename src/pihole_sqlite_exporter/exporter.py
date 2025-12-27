import argparse
import logging
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from .config import Config
from .gauges import Gauges
from .metrics import PiholeDestTotalsCollector, PiholeTotalsCollector
from .payload_cache import PayloadCache
from .queries import (
    SQL_BLOCKED_TODAY,
    SQL_CACHED_TODAY,
    SQL_CLIENTS_EVER_SEEN,
    SQL_COUNTER_BLOCKED,
    SQL_COUNTER_TOTAL,
    SQL_DOMAIN_BY_ID_COUNT,
    SQL_FORWARD_DESTS_TODAY,
    SQL_FORWARD_REPLY_TIMES,
    SQL_FORWARDED_TODAY,
    SQL_GRAVITY_COUNT,
    SQL_LIFETIME_BLOCKED,
    SQL_LIFETIME_CACHE,
    SQL_LIFETIME_FORWARD_DESTS,
    SQL_QUERIES_TODAY,
    SQL_QUERY_TYPES,
    SQL_REPLY_TYPES,
    SQL_REQUEST_RATE_WINDOW,
    SQL_TOP_ADS,
    SQL_TOP_QUERIES,
    SQL_TOP_SOURCES,
    SQL_UNIQUE_CLIENTS,
    SQL_UNIQUE_DOMAINS,
)
from .utils import env_truthy, get_tz, now_ts, sqlite_ro, start_of_day_ts, variance

# ----------------------------
# Logging
# ----------------------------
logger = logging.getLogger("pihole_sqlite_exporter")


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# Pi-hole status codes: documented list
BLOCKED_STATUSES = {1, 4, 5, 6, 7, 8, 9, 10, 11, 15}

QUERY_TYPE_MAP = {
    1: "A",
    2: "AAAA",
    3: "ANY",
    4: "SRV",
    5: "SOA",
    6: "PTR",
    7: "TXT",
    8: "NAPTR",
    9: "MX",
    10: "DS",
    11: "RRSIG",
    12: "DNSKEY",
    13: "NS",
    14: "OTHER",
    15: "SVCB",
    16: "HTTPS",
}

REPLY_TYPE_MAP = {
    0: "unknown",
    1: "no_data",  # NODATA
    2: "nx_domain",  # NXDOMAIN
    3: "cname",  # CNAME
    4: "ip",  # a valid IP record
    5: "domain",  # DOMAIN
    6: "rr_name",  # RRNAME
    7: "serv_fail",  # SERVFAIL
    8: "refused",  # REFUSED
    9: "not_imp",  # NOTIMP
    10: "other",  # OTHER
    11: "dnssec",  # DNSSEC
    12: "none",  # NONE
    13: "blob",  # BLOB
}


class Scraper:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.registry = CollectorRegistry()

        self.total_queries_lifetime = 0
        self.blocked_queries_lifetime = 0
        self.forward_destinations_lifetime: dict[str, int] = {}
        self._last_total_queries_lifetime: int | None = None
        self._last_rate_ts: float | None = None

        self._scrape_lock = threading.Lock()
        self._cache = PayloadCache()

        self.registry.register(PiholeTotalsCollector(self))
        self.registry.register(PiholeDestTotalsCollector(self))

        self.gauges = Gauges.create(self.registry)

    def refresh(self) -> None:
        with self._scrape_lock:
            self.scrape_and_update()
            payload = generate_latest(self.registry)
        self._cache.set(payload, time.time())

    def get_payload(self) -> tuple[bytes | None, str | None]:
        return self._cache.get()

    def ensure_payload(self) -> tuple[bytes | None, str | None]:
        payload, err = self.get_payload()
        if payload is not None:
            return payload, err
        try:
            self.refresh()
        except Exception as e:
            msg = f"scrape failed: {e}"
            self._cache.set_error(msg)
            return None, msg
        return self.get_payload()

    def _blocked_status_list(self) -> str:
        return ",".join(str(x) for x in sorted(BLOCKED_STATUSES))

    def _clear_series(self) -> None:
        self.gauges.clear_dynamic_series()

    def _load_counters(self, cur: sqlite3.Cursor, host: str) -> None:
        self.gauges.status.labels(host).set(1)

        cur.execute(SQL_COUNTER_TOTAL)
        self.total_queries_lifetime = int(cur.fetchone()[0])

        cur.execute(SQL_COUNTER_BLOCKED)
        self.blocked_queries_lifetime = int(cur.fetchone()[0])

        logger.debug(
            "FTL counters: total=%d blocked=%d",
            self.total_queries_lifetime,
            self.blocked_queries_lifetime,
        )

    def _load_lifetime_destinations(self, cur: sqlite3.Cursor, blocked_list: str) -> None:
        if self.config.enable_lifetime_dest_counters:
            lifetime = {}
            cur.execute(SQL_LIFETIME_FORWARD_DESTS)
            for fwd, cnt in cur.fetchall():
                lifetime[str(fwd)] = int(cnt)

            cur.execute(SQL_LIFETIME_CACHE)
            lifetime["cache"] = int(cur.fetchone()[0])

            cur.execute(SQL_LIFETIME_BLOCKED.format(blocked_list=blocked_list))
            lifetime["blocklist"] = int(cur.fetchone()[0])

            self.forward_destinations_lifetime = lifetime
            logger.debug(
                "Lifetime destinations computed: %d labelsets",
                len(self.forward_destinations_lifetime),
            )
        else:
            self.forward_destinations_lifetime = {}

    def _load_clients_ever_seen(self, cur: sqlite3.Cursor, host: str) -> None:
        cur.execute(SQL_CLIENTS_EVER_SEEN)
        self.gauges.clients_ever_seen.labels(host).set(float(cur.fetchone()[0]))

    def _fetch_queries_today(
        self, cur: sqlite3.Cursor, sod: int, blocked_list: str
    ) -> tuple[int, int]:
        cur.execute(SQL_QUERIES_TODAY, (sod,))
        q_today = int(cur.fetchone()[0])

        cur.execute(SQL_BLOCKED_TODAY.format(blocked_list=blocked_list), (sod,))
        b_today = int(cur.fetchone()[0])
        return q_today, b_today

    def _set_queries_today(self, host: str, q_today: int, b_today: int) -> None:
        self.gauges.dns_queries_today.labels(host).set(float(q_today))
        self.gauges.dns_queries_all_types.labels(host).set(float(q_today))
        self.gauges.ads_blocked_today.labels(host).set(float(b_today))
        self.gauges.ads_percentage_today.labels(host).set(
            (b_today / q_today * 100.0) if q_today > 0 else 0.0
        )

    def _fetch_unique_counts(self, cur: sqlite3.Cursor, now: int) -> tuple[int, int]:
        cur.execute(SQL_UNIQUE_CLIENTS, (now - 86400,))
        unique_clients = int(cur.fetchone()[0])

        cur.execute(SQL_UNIQUE_DOMAINS, (now - 86400,))
        unique_domains = int(cur.fetchone()[0])
        return unique_clients, unique_domains

    def _set_unique_counts(self, host: str, unique_clients: int, unique_domains: int) -> None:
        self.gauges.unique_clients.labels(host).set(float(unique_clients))
        self.gauges.unique_domains.labels(host).set(float(unique_domains))

    def _load_query_types(self, cur: sqlite3.Cursor, host: str, sod: int) -> None:
        cur.execute(SQL_QUERY_TYPES, (sod,))
        counts_by_type = {k: 0 for k in QUERY_TYPE_MAP.keys()}
        for t, c in cur.fetchall():
            counts_by_type[int(t)] = int(c)

        for tid, name in QUERY_TYPE_MAP.items():
            self.gauges.querytypes.labels(host, name).set(float(counts_by_type.get(tid, 0)))

    def _load_reply_types(self, cur: sqlite3.Cursor, host: str, sod: int) -> None:
        cur.execute(SQL_REPLY_TYPES, (sod,))
        counts_by_reply = {k: 0 for k in REPLY_TYPE_MAP.keys()}
        for rt, c in cur.fetchall():
            if rt is None:
                continue
            counts_by_reply[int(rt)] = int(c)

        for rid, label in REPLY_TYPE_MAP.items():
            self.gauges.reply.labels(host, label).set(float(counts_by_reply.get(rid, 0)))

    def _fetch_cache_forwarded(self, cur: sqlite3.Cursor, sod: int) -> tuple[int, int]:
        cur.execute(SQL_FORWARDED_TODAY, (sod,))
        forwarded = int(cur.fetchone()[0])

        cur.execute(SQL_CACHED_TODAY, (sod,))
        cached = int(cur.fetchone()[0])
        return forwarded, cached

    def _set_cache_forwarded(self, host: str, forwarded: int, cached: int) -> None:
        self.gauges.queries_forwarded.labels(host).set(float(forwarded))
        self.gauges.queries_cached.labels(host).set(float(cached))

    def _load_forward_destinations(self, cur: sqlite3.Cursor, host: str, sod: int) -> None:
        cur.execute(SQL_FORWARD_DESTS_TODAY, (sod,))
        forwards = cur.fetchall()

        for fwd, cnt, avg_rt in forwards:
            dest = str(fwd)
            self.gauges.forward_destinations.labels(host, dest, dest).set(float(cnt))
            self.gauges.forward_destinations_responsetime.labels(host, dest, dest).set(
                float(avg_rt or 0.0)
            )

            cur.execute(SQL_FORWARD_REPLY_TIMES, (sod, fwd))
            vals = [float(r[0]) for r in cur.fetchall()]
            self.gauges.forward_destinations_responsevariance.labels(host, dest, dest).set(
                float(variance(vals))
            )

    def _load_synthetic_destinations(
        self, cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str
    ) -> None:
        cur.execute(SQL_CACHED_TODAY, (sod,))
        cache_cnt = int(cur.fetchone()[0])
        self.gauges.forward_destinations.labels(host, "cache", "cache").set(float(cache_cnt))
        self.gauges.forward_destinations_responsetime.labels(host, "cache", "cache").set(0.0)
        self.gauges.forward_destinations_responsevariance.labels(host, "cache", "cache").set(0.0)

        cur.execute(SQL_BLOCKED_TODAY.format(blocked_list=blocked_list), (sod,))
        bl_cnt = int(cur.fetchone()[0])
        self.gauges.forward_destinations.labels(host, "blocklist", "blocklist").set(float(bl_cnt))
        self.gauges.forward_destinations_responsetime.labels(host, "blocklist", "blocklist").set(
            0.0
        )
        self.gauges.forward_destinations_responsevariance.labels(
            host, "blocklist", "blocklist"
        ).set(0.0)

    def _load_top_lists(self, cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str) -> None:
        cur.execute(SQL_TOP_ADS.format(blocked_list=blocked_list, top_n=self.config.top_n), (sod,))
        for domain, cnt in cur.fetchall():
            self.gauges.top_ads.labels(host, str(domain)).set(float(cnt))

        cur.execute(SQL_TOP_QUERIES.format(top_n=self.config.top_n), (sod,))
        for domain, cnt in cur.fetchall():
            self.gauges.top_queries.labels(host, str(domain)).set(float(cnt))

        cur.execute(SQL_TOP_SOURCES.format(top_n=self.config.top_n), (sod,))
        for ip, name, cnt in cur.fetchall():
            self.gauges.top_sources.labels(host, str(ip), str(name or "")).set(float(cnt))

    def _load_domains_blocked(self, host: str) -> None:
        domains_value = None
        try:
            with sqlite_ro(self.config.gravity_db_path) as gconn:
                gcur = gconn.cursor()
                gcur.execute(SQL_GRAVITY_COUNT)
                domains_value = int(gcur.fetchone()[0])
        except Exception as e:
            logger.info("Gravity DB unavailable; falling back (reason: %s)", e)
            domains_value = None

        if domains_value is None:
            try:
                with sqlite_ro(self.config.ftl_db_path) as conn:
                    cur = conn.cursor()
                    cur.execute(SQL_DOMAIN_BY_ID_COUNT)
                    domains_value = int(cur.fetchone()[0])
            except Exception as e:
                logger.warning("Fallback domain count failed: %s", e)
                domains_value = 0

        self.gauges.domains_being_blocked.labels(host).set(float(domains_value))

    def _update_request_rate(self, cur: sqlite3.Cursor, host: str, now: int) -> None:
        window = max(1, self.config.request_rate_window_sec)
        cur.execute(SQL_REQUEST_RATE_WINDOW, (now - window,))
        count = int(cur.fetchone()[0])
        rate = count / float(window)
        self.gauges.request_rate.labels(host).set(rate)
        logger.debug("Request rate window=%ds count=%d rate=%.6f", window, count, rate)

    def scrape_and_update(self) -> None:
        start = time.time()
        host = self.config.hostname_label
        tz = get_tz(self.config.exporter_tz)
        sod = start_of_day_ts(tz)
        now = now_ts()

        logger.debug(
            "Scrape start (host=%s, sod=%s, now=%s, tz=%s)",
            host,
            sod,
            now,
            self.config.exporter_tz,
        )

        self._clear_series()
        blocked_list = self._blocked_status_list()

        with sqlite_ro(self.config.ftl_db_path) as conn:
            cur = conn.cursor()

            self._load_counters(cur, host)
            self._load_lifetime_destinations(cur, blocked_list)
            self._load_clients_ever_seen(cur, host)
            q_today, b_today = self._fetch_queries_today(cur, sod, blocked_list)
            self._set_queries_today(host, q_today, b_today)

            unique_clients, unique_domains = self._fetch_unique_counts(cur, now)
            self._set_unique_counts(host, unique_clients, unique_domains)
            self._load_query_types(cur, host, sod)
            self._load_reply_types(cur, host, sod)

            forwarded, cached = self._fetch_cache_forwarded(cur, sod)
            self._set_cache_forwarded(host, forwarded, cached)
            self._load_forward_destinations(cur, host, sod)
            self._load_synthetic_destinations(cur, host, sod, blocked_list)
            self._load_top_lists(cur, host, sod, blocked_list)
            self._update_request_rate(cur, host, now)

        ftl_elapsed = time.time() - start

        self._load_domains_blocked(host)
        total_elapsed = time.time() - start
        logger.debug(
            "Scrape finished in %.3fs (ftl=%.3fs, gravity=%.3fs)",
            total_elapsed,
            ftl_elapsed,
            total_elapsed - ftl_elapsed,
        )


def make_handler(scraper: Scraper):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/metrics", "/"):
                self.send_response(404)
                self.end_headers()
                return

            try:
                logger.info("HTTP request: %s %s", self.command, self.path)
                payload, err = scraper.ensure_payload()
                if payload is None:
                    msg = (err or "scrape failed") + "\n"
                    body = msg.encode()
                    self.send_response(500)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                logger.info("HTTP 200 served metrics bytes=%d", len(payload))
            except Exception as e:
                logger.exception("Scrape failed while serving request")
                msg = f"scrape failed: {e}\n".encode()
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)

        def log_message(self, format, *args):
            return

    return Handler


def _scrape_loop(
    scraper: Scraper,
    stop_event: threading.Event | None = None,
    sleep_fn=time.sleep,
    time_fn=time.time,
) -> None:
    interval = max(1, scraper.config.scrape_interval)
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        start = time_fn()
        try:
            scraper.refresh()
        except Exception:
            logger.exception("Background scrape failed")
        elapsed = time_fn() - start
        sleep_fn(max(1.0, interval - elapsed))


def parse_args():
    parser = argparse.ArgumentParser(description="Pi-hole SQLite Prometheus exporter")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose (debug) logging")
    return parser.parse_args()


def main():
    args = parse_args()
    verbose = bool(args.verbose) or env_truthy("DEBUG", "false")
    configure_logging(verbose)

    config = Config.from_env()
    scraper = Scraper(config)

    logger.info(
        (
            "Starting exporter (listen=%s:%s, tz=%s, ftl_db=%s, gravity_db=%s, top_n=%s, "
            "lifetime_dest_counters=%s, scrape_interval=%s)"
        ),
        config.listen_addr,
        config.listen_port,
        config.exporter_tz,
        config.ftl_db_path,
        config.gravity_db_path,
        config.top_n,
        config.enable_lifetime_dest_counters,
        config.scrape_interval,
    )

    thread = threading.Thread(target=_scrape_loop, args=(scraper,), daemon=True)
    thread.start()

    handler = make_handler(scraper)
    httpd = ThreadingHTTPServer((config.listen_addr, config.listen_port), handler)
    logger.info("HTTP server ready; waiting for scrapes")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
