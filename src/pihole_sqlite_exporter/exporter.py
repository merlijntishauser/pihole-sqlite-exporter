import argparse
import logging
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

from .config import Config
from .metrics import PiholeDestTotalsCollector, PiholeTotalsCollector
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

SQL_COUNTER_TOTAL = "SELECT value FROM counters WHERE id = 0;"
SQL_COUNTER_BLOCKED = "SELECT value FROM counters WHERE id = 1;"
SQL_LIFETIME_FORWARD_DESTS = """
    SELECT forward, COUNT(*)
    FROM queries
    WHERE status = 2
      AND forward IS NOT NULL
    GROUP BY forward;
"""
SQL_LIFETIME_CACHE = "SELECT COUNT(*) FROM queries WHERE status = 3;"
SQL_LIFETIME_BLOCKED = "SELECT COUNT(*) FROM queries WHERE status IN ({blocked_list});"
SQL_CLIENTS_EVER_SEEN = "SELECT COUNT(*) FROM client_by_id;"
SQL_QUERIES_TODAY = """
    SELECT COUNT(*)
    FROM queries
    WHERE timestamp >= ?;
"""
SQL_BLOCKED_TODAY = """
    SELECT COUNT(*)
    FROM queries
    WHERE timestamp >= ?
      AND status IN ({blocked_list});
"""
SQL_UNIQUE_CLIENTS = "SELECT COUNT(DISTINCT client) FROM queries WHERE timestamp >= ?;"
SQL_UNIQUE_DOMAINS = "SELECT COUNT(DISTINCT domain) FROM queries WHERE timestamp >= ?;"
SQL_QUERY_TYPES = """
    SELECT type, COUNT(*)
    FROM queries
    WHERE timestamp >= ?
    GROUP BY type;
"""
SQL_REPLY_TYPES = """
    SELECT reply_type, COUNT(*)
    FROM queries
    WHERE timestamp >= ?
    GROUP BY reply_type;
"""
SQL_FORWARDED_TODAY = "SELECT COUNT(*) FROM queries WHERE timestamp >= ? AND status = 2;"
SQL_CACHED_TODAY = "SELECT COUNT(*) FROM queries WHERE timestamp >= ? AND status = 3;"
SQL_FORWARD_DESTS_TODAY = """
    SELECT forward, COUNT(*), AVG(reply_time)
    FROM queries
    WHERE timestamp >= ?
      AND status = 2
      AND forward IS NOT NULL
    GROUP BY forward
    ORDER BY COUNT(*) DESC;
"""
SQL_FORWARD_REPLY_TIMES = """
    SELECT reply_time
    FROM queries
    WHERE timestamp >= ?
      AND status = 2
      AND forward = ?
      AND reply_time IS NOT NULL;
"""
SQL_TOP_ADS = """
    SELECT domain, COUNT(*) AS cnt
    FROM queries
    WHERE timestamp >= ?
      AND status IN ({blocked_list})
    GROUP BY domain
    ORDER BY cnt DESC
    LIMIT {top_n};
"""
SQL_TOP_QUERIES = """
    SELECT domain, COUNT(*) AS cnt
    FROM queries
    WHERE timestamp >= ?
    GROUP BY domain
    ORDER BY cnt DESC
    LIMIT {top_n};
"""
SQL_TOP_SOURCES = """
    SELECT q.client, COALESCE(c.name,''), COUNT(*) AS cnt
    FROM queries q
    LEFT JOIN client_by_id c ON c.ip = q.client
    WHERE q.timestamp >= ?
    GROUP BY q.client, c.name
    ORDER BY cnt DESC
    LIMIT {top_n};
"""
SQL_GRAVITY_COUNT = "SELECT COUNT(*) FROM gravity;"
SQL_DOMAIN_BY_ID_COUNT = "SELECT COUNT(*) FROM domain_by_id;"


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
        self._payload_lock = threading.Lock()
        self._payload: bytes | None = None
        self._payload_ts: float | None = None
        self._last_error: str | None = None

        self.registry.register(PiholeTotalsCollector(self))
        self.registry.register(PiholeDestTotalsCollector(self))

        self.pihole_ads_blocked_today = Gauge(
            "pihole_ads_blocked_today",
            "Represents the number of ads blocked over the current day",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_ads_percentage_today = Gauge(
            "pihole_ads_percentage_today",
            "Represents the percentage of ads blocked over the current day",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_clients_ever_seen = Gauge(
            "pihole_clients_ever_seen",
            "Represents the number of clients ever seen",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_dns_queries_all_types = Gauge(
            "pihole_dns_queries_all_types",
            "Represents the number of DNS queries across all types",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_dns_queries_today = Gauge(
            "pihole_dns_queries_today",
            "Represents the number of DNS queries made over the current day",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_domains_being_blocked = Gauge(
            "pihole_domains_being_blocked",
            "Represents the number of domains being blocked",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_forward_destinations = Gauge(
            "pihole_forward_destinations",
            "Represents the number of forward destination requests made by Pi-hole by destination",
            ["hostname", "destination", "destination_name"],
            registry=self.registry,
        )
        self.pihole_forward_destinations_responsetime = Gauge(
            "pihole_forward_destinations_responsetime",
            (
                "Represents the seconds a forward destination took to process a request made by "
                "Pi-hole"
            ),
            ["hostname", "destination", "destination_name"],
            registry=self.registry,
        )
        self.pihole_forward_destinations_responsevariance = Gauge(
            "pihole_forward_destinations_responsevariance",
            "Represents the variance in response time for forward destinations",
            ["hostname", "destination", "destination_name"],
            registry=self.registry,
        )
        self.pihole_queries_cached = Gauge(
            "pihole_queries_cached",
            "Represents the number of cached queries",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_queries_forwarded = Gauge(
            "pihole_queries_forwarded",
            "Represents the number of forwarded queries",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_querytypes = Gauge(
            "pihole_querytypes",
            "Represents the number of queries made by Pi-hole by type",
            ["hostname", "type"],
            registry=self.registry,
        )
        self.pihole_reply = Gauge(
            "pihole_reply",
            "Represents the number of replies by type",
            ["hostname", "type"],
            registry=self.registry,
        )
        self.pihole_request_rate = Gauge(
            "pihole_request_rate",
            "Represents the number of requests per second",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_status = Gauge(
            "pihole_status",
            "Whether Pi-hole is enabled",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_top_ads = Gauge(
            "pihole_top_ads",
            "Represents the number of top ads by domain",
            ["hostname", "domain"],
            registry=self.registry,
        )
        self.pihole_top_queries = Gauge(
            "pihole_top_queries",
            "Represents the number of top queries by domain",
            ["hostname", "domain"],
            registry=self.registry,
        )
        self.pihole_top_sources = Gauge(
            "pihole_top_sources",
            "Represents the number of top sources by source host",
            ["hostname", "source", "source_name"],
            registry=self.registry,
        )
        self.pihole_unique_clients = Gauge(
            "pihole_unique_clients",
            "Represents the number of unique clients seen in the last 24h",
            ["hostname"],
            registry=self.registry,
        )
        self.pihole_unique_domains = Gauge(
            "pihole_unique_domains",
            "Represents the number of unique domains seen",
            ["hostname"],
            registry=self.registry,
        )

    def refresh(self) -> None:
        with self._scrape_lock:
            self.scrape_and_update()
            payload = generate_latest(self.registry)
        with self._payload_lock:
            self._payload = payload
            self._payload_ts = time.time()
            self._last_error = None

    def get_payload(self) -> tuple[bytes | None, str | None]:
        with self._payload_lock:
            return self._payload, self._last_error

    def ensure_payload(self) -> tuple[bytes | None, str | None]:
        payload, err = self.get_payload()
        if payload is not None:
            return payload, err
        try:
            self.refresh()
        except Exception as e:
            msg = f"scrape failed: {e}"
            with self._payload_lock:
                self._last_error = msg
            return None, msg
        return self.get_payload()

    def _blocked_status_list(self) -> str:
        return ",".join(str(x) for x in sorted(BLOCKED_STATUSES))

    def _clear_series(self) -> None:
        self.pihole_top_ads.clear()
        self.pihole_top_queries.clear()
        self.pihole_top_sources.clear()
        self.pihole_forward_destinations.clear()
        self.pihole_forward_destinations_responsetime.clear()
        self.pihole_forward_destinations_responsevariance.clear()

    def _load_counters(self, cur: sqlite3.Cursor, host: str) -> None:
        self.pihole_status.labels(host).set(1)

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
        self.pihole_clients_ever_seen.labels(host).set(float(cur.fetchone()[0]))

    def _load_queries_today(
        self, cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str
    ) -> None:
        cur.execute(SQL_QUERIES_TODAY, (sod,))
        q_today = int(cur.fetchone()[0])

        cur.execute(SQL_BLOCKED_TODAY.format(blocked_list=blocked_list), (sod,))
        b_today = int(cur.fetchone()[0])

        self.pihole_dns_queries_today.labels(host).set(float(q_today))
        self.pihole_dns_queries_all_types.labels(host).set(float(q_today))
        self.pihole_ads_blocked_today.labels(host).set(float(b_today))
        self.pihole_ads_percentage_today.labels(host).set(
            (b_today / q_today * 100.0) if q_today > 0 else 0.0
        )

    def _load_unique_counts(self, cur: sqlite3.Cursor, host: str, now: int) -> None:
        cur.execute(SQL_UNIQUE_CLIENTS, (now - 86400,))
        self.pihole_unique_clients.labels(host).set(float(cur.fetchone()[0]))

        cur.execute(SQL_UNIQUE_DOMAINS, (now - 86400,))
        self.pihole_unique_domains.labels(host).set(float(cur.fetchone()[0]))

    def _load_query_types(self, cur: sqlite3.Cursor, host: str, sod: int) -> None:
        cur.execute(SQL_QUERY_TYPES, (sod,))
        counts_by_type = {k: 0 for k in QUERY_TYPE_MAP.keys()}
        for t, c in cur.fetchall():
            counts_by_type[int(t)] = int(c)

        for tid, name in QUERY_TYPE_MAP.items():
            self.pihole_querytypes.labels(host, name).set(float(counts_by_type.get(tid, 0)))

    def _load_reply_types(self, cur: sqlite3.Cursor, host: str, sod: int) -> None:
        cur.execute(SQL_REPLY_TYPES, (sod,))
        counts_by_reply = {k: 0 for k in REPLY_TYPE_MAP.keys()}
        for rt, c in cur.fetchall():
            if rt is None:
                continue
            counts_by_reply[int(rt)] = int(c)

        for rid, label in REPLY_TYPE_MAP.items():
            self.pihole_reply.labels(host, label).set(float(counts_by_reply.get(rid, 0)))

    def _load_cache_forwarded(self, cur: sqlite3.Cursor, host: str, sod: int) -> None:
        cur.execute(SQL_FORWARDED_TODAY, (sod,))
        self.pihole_queries_forwarded.labels(host).set(float(cur.fetchone()[0]))

        cur.execute(SQL_CACHED_TODAY, (sod,))
        self.pihole_queries_cached.labels(host).set(float(cur.fetchone()[0]))

    def _load_forward_destinations(self, cur: sqlite3.Cursor, host: str, sod: int) -> None:
        cur.execute(SQL_FORWARD_DESTS_TODAY, (sod,))
        forwards = cur.fetchall()

        for fwd, cnt, avg_rt in forwards:
            dest = str(fwd)
            self.pihole_forward_destinations.labels(host, dest, dest).set(float(cnt))
            self.pihole_forward_destinations_responsetime.labels(host, dest, dest).set(
                float(avg_rt or 0.0)
            )

            cur.execute(SQL_FORWARD_REPLY_TIMES, (sod, fwd))
            vals = [float(r[0]) for r in cur.fetchall()]
            self.pihole_forward_destinations_responsevariance.labels(host, dest, dest).set(
                float(variance(vals))
            )

    def _load_synthetic_destinations(
        self, cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str
    ) -> None:
        cur.execute(SQL_CACHED_TODAY, (sod,))
        cache_cnt = int(cur.fetchone()[0])
        self.pihole_forward_destinations.labels(host, "cache", "cache").set(float(cache_cnt))
        self.pihole_forward_destinations_responsetime.labels(host, "cache", "cache").set(0.0)
        self.pihole_forward_destinations_responsevariance.labels(host, "cache", "cache").set(0.0)

        cur.execute(SQL_BLOCKED_TODAY.format(blocked_list=blocked_list), (sod,))
        bl_cnt = int(cur.fetchone()[0])
        self.pihole_forward_destinations.labels(host, "blocklist", "blocklist").set(float(bl_cnt))
        self.pihole_forward_destinations_responsetime.labels(host, "blocklist", "blocklist").set(
            0.0
        )
        self.pihole_forward_destinations_responsevariance.labels(
            host, "blocklist", "blocklist"
        ).set(0.0)

    def _load_top_lists(self, cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str) -> None:
        cur.execute(SQL_TOP_ADS.format(blocked_list=blocked_list, top_n=self.config.top_n), (sod,))
        for domain, cnt in cur.fetchall():
            self.pihole_top_ads.labels(host, str(domain)).set(float(cnt))

        cur.execute(SQL_TOP_QUERIES.format(top_n=self.config.top_n), (sod,))
        for domain, cnt in cur.fetchall():
            self.pihole_top_queries.labels(host, str(domain)).set(float(cnt))

        cur.execute(SQL_TOP_SOURCES.format(top_n=self.config.top_n), (sod,))
        for ip, name, cnt in cur.fetchall():
            self.pihole_top_sources.labels(host, str(ip), str(name or "")).set(float(cnt))

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

        self.pihole_domains_being_blocked.labels(host).set(float(domains_value))

    def _update_request_rate(self, host: str) -> None:
        if self._last_total_queries_lifetime is not None and self._last_rate_ts is not None:
            dt = max(1.0, time.time() - self._last_rate_ts)
            dq = max(0, self.total_queries_lifetime - self._last_total_queries_lifetime)
            self.pihole_request_rate.labels(host).set(dq / dt)
            logger.debug("Request rate queries_delta=%d time_delta=%.3f rate=%.6f", dq, dt, dq / dt)
        else:
            self.pihole_request_rate.labels(host).set(0.0)
            logger.debug("Request rate initialized to 0.0")

        self._last_total_queries_lifetime = self.total_queries_lifetime
        self._last_rate_ts = time.time()

    def scrape_and_update(self) -> None:
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
            self._load_queries_today(cur, host, sod, blocked_list)
            self._load_unique_counts(cur, host, now)
            self._load_query_types(cur, host, sod)
            self._load_reply_types(cur, host, sod)
            self._load_cache_forwarded(cur, host, sod)
            self._load_forward_destinations(cur, host, sod)
            self._load_synthetic_destinations(cur, host, sod, blocked_list)
            self._load_top_lists(cur, host, sod, blocked_list)

        self._load_domains_blocked(host)
        self._update_request_rate(host)


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
