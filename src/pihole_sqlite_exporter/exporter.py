import argparse
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest
from prometheus_client.core import CounterMetricFamily

# ----------------------------
# Logging
# ----------------------------
logger = logging.getLogger("pihole_sqlite_exporter")


def _read_version() -> str:
    version_path = Path(__file__).resolve().parents[2] / "VERSION"
    if version_path.is_file():
        return version_path.read_text().strip()
    try:
        from . import __version__  # type: ignore

        return str(__version__)
    except Exception:
        return "unknown"


def _read_commit() -> str:
    return (
        os.getenv("GIT_COMMIT") or os.getenv("GIT_SHA") or os.getenv("SOURCE_COMMIT") or "unknown"
    )


def _env_truthy(name: str, default: str = "false") -> bool:
    v = os.getenv(name, default)
    return str(v).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# ----------------------------
# Config
# ----------------------------
FTL_DB_PATH = os.getenv("FTL_DB_PATH", "/etc/pihole/pihole-FTL.db")
GRAVITY_DB_PATH = os.getenv("GRAVITY_DB_PATH", "/etc/pihole/gravity.db")

LISTEN_ADDR = os.getenv("LISTEN_ADDR", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "9617"))

HOSTNAME_LABEL = os.getenv("HOSTNAME_LABEL", "host.docker.internal")
TOP_N = int(os.getenv("TOP_N", "10"))
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "15"))

# Timezone for “start_of_day” calculations (env-driven)
EXPORTER_TZ = os.getenv("EXPORTER_TZ", "Europe/Amsterdam")

# If true, compute lifetime per-destination counters by scanning the full queries table.
# On large databases this can be heavy; keep it enabled only if you really need totals.
ENABLE_LIFETIME_DEST_COUNTERS = _env_truthy("ENABLE_LIFETIME_DEST_COUNTERS", "true")

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

# ----------------------------
# Prometheus registry (NO default collectors)
# ----------------------------
REGISTRY = CollectorRegistry()

# ----------------------------
# Counter state (served via custom collectors)
# ----------------------------
_total_queries_lifetime = 0
_blocked_queries_lifetime = 0

# destination -> count (lifetime, monotonic, derived)
_forward_destinations_lifetime = {}  # type: dict[str, int]
_last_request_ts = None
_last_request_total = None
_last_request_rowid = None


class PiholeTotalsCollector:
    """
    Expose Pi-hole lifetime totals as Prometheus COUNTER type.
    Values are updated during scrape_and_update(), then emitted here.
    """

    def collect(self):
        host = HOSTNAME_LABEL

        m1 = CounterMetricFamily(
            "pihole_dns_queries_total",
            (
                "Total number of DNS queries (lifetime, monotonic) as reported by Pi-hole FTL "
                "counters table"
            ),
            labels=["hostname"],
        )
        m1.add_metric([host], float(_total_queries_lifetime))
        yield m1

        m2 = CounterMetricFamily(
            "pihole_ads_blocked_total",
            (
                "Total number of blocked queries (lifetime, monotonic) as reported by Pi-hole FTL "
                "counters table"
            ),
            labels=["hostname"],
        )
        m2.add_metric([host], float(_blocked_queries_lifetime))
        yield m2


class PiholeDestTotalsCollector:
    """
    Expose per-destination lifetime totals as Prometheus COUNTER type.

    Metric name: pihole_forward_destinations_total
    Labels: hostname, destination, destination_name

    NOTE: These lifetime totals are derived from the queries table.
    """

    def collect(self):
        host = HOSTNAME_LABEL
        m = CounterMetricFamily(
            "pihole_forward_destinations_total",
            (
                "Total number of forward destinations requests made by Pi-hole by destination "
                "(lifetime, derived from queries table)"
            ),
            labels=["hostname", "destination", "destination_name"],
        )

        # Emit stable sorted for readability
        for dest in sorted(_forward_destinations_lifetime.keys()):
            cnt = _forward_destinations_lifetime.get(dest, 0)
            # match existing style: destination_name mirrors destination
            m.add_metric([host, dest, dest], float(cnt))

        yield m


REGISTRY.register(PiholeTotalsCollector())
REGISTRY.register(PiholeDestTotalsCollector())

# ----------------------------
# Gauges (names/help matching your desired output)
# ----------------------------
pihole_ads_blocked_today = Gauge(
    "pihole_ads_blocked_today",
    "Represents the number of ads blocked over the current day",
    ["hostname"],
    registry=REGISTRY,
)

pihole_ads_percentage_today = Gauge(
    "pihole_ads_percentage_today",
    "Represents the percentage of ads blocked over the current day",
    ["hostname"],
    registry=REGISTRY,
)

pihole_clients_ever_seen = Gauge(
    "pihole_clients_ever_seen",
    "Represents the number of clients ever seen",
    ["hostname"],
    registry=REGISTRY,
)

pihole_dns_queries_all_types = Gauge(
    "pihole_dns_queries_all_types",
    "Represents the number of DNS queries across all types",
    ["hostname"],
    registry=REGISTRY,
)

pihole_dns_queries_today = Gauge(
    "pihole_dns_queries_today",
    "Represents the number of DNS queries made over the current day",
    ["hostname"],
    registry=REGISTRY,
)

pihole_domains_being_blocked = Gauge(
    "pihole_domains_being_blocked",
    "Represents the number of domains being blocked",
    ["hostname"],
    registry=REGISTRY,
)

pihole_forward_destinations = Gauge(
    "pihole_forward_destinations",
    "Represents the number of forward destination requests made by Pi-hole by destination",
    ["hostname", "destination", "destination_name"],
    registry=REGISTRY,
)

pihole_forward_destinations_responsetime = Gauge(
    "pihole_forward_destinations_responsetime",
    "Represents the seconds a forward destination took to process a request made by Pi-hole",
    ["hostname", "destination", "destination_name"],
    registry=REGISTRY,
)

pihole_forward_destinations_responsevariance = Gauge(
    "pihole_forward_destinations_responsevariance",
    "Represents the variance in response time for forward destinations",
    ["hostname", "destination", "destination_name"],
    registry=REGISTRY,
)

pihole_queries_cached = Gauge(
    "pihole_queries_cached",
    "Represents the number of cached queries",
    ["hostname"],
    registry=REGISTRY,
)

pihole_queries_forwarded = Gauge(
    "pihole_queries_forwarded",
    "Represents the number of forwarded queries",
    ["hostname"],
    registry=REGISTRY,
)

pihole_querytypes = Gauge(
    "pihole_querytypes",
    "Represents the number of queries made by Pi-hole by type",
    ["hostname", "type"],
    registry=REGISTRY,
)

pihole_reply = Gauge(
    "pihole_reply",
    "Represents the number of replies by type",
    ["hostname", "type"],
    registry=REGISTRY,
)

pihole_request_rate = Gauge(
    "pihole_request_rate",
    "Represents the number of requests per second",
    ["hostname"],
    registry=REGISTRY,
)

pihole_status = Gauge(
    "pihole_status",
    "Whether Pi-hole is enabled",
    ["hostname"],
    registry=REGISTRY,
)

pihole_top_ads = Gauge(
    "pihole_top_ads",
    "Represents the number of top ads by domain",
    ["hostname", "domain"],
    registry=REGISTRY,
)

pihole_top_queries = Gauge(
    "pihole_top_queries",
    "Represents the number of top queries by domain",
    ["hostname", "domain"],
    registry=REGISTRY,
)

pihole_top_sources = Gauge(
    "pihole_top_sources",
    "Represents the number of top sources by source host",
    ["hostname", "source", "source_name"],
    registry=REGISTRY,
)

pihole_unique_clients = Gauge(
    "pihole_unique_clients",
    "Represents the number of unique clients seen in the last 24h",
    ["hostname"],
    registry=REGISTRY,
)

pihole_unique_domains = Gauge(
    "pihole_unique_domains",
    "Represents the number of unique domains seen",
    ["hostname"],
    registry=REGISTRY,
)


# ----------------------------
# Helpers
# ----------------------------
def sqlite_ro(db_path: str) -> sqlite3.Connection:
    dsn = f"file:{db_path}?mode=ro"
    logger.debug("Opening SQLite DB read-only: %s", db_path)
    return sqlite3.connect(dsn, uri=True)


def _get_tz() -> ZoneInfo:
    try:
        return ZoneInfo(EXPORTER_TZ)
    except Exception as e:
        logger.warning(
            "Invalid EXPORTER_TZ=%r; falling back to local tz. Reason: %s", EXPORTER_TZ, e
        )
        return datetime.now().astimezone().tzinfo  # type: ignore[return-value]


def start_of_day_ts() -> int:
    tz = _get_tz()
    now = datetime.now(tz=tz)
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(sod.timestamp())


def now_ts() -> int:
    return int(time.time())


def variance(values):
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    return sum((x - mean) ** 2 for x in values) / n


# ----------------------------
# Scrape + update metrics
# ----------------------------
def scrape_and_update():
    global _total_queries_lifetime, _blocked_queries_lifetime, _forward_destinations_lifetime

    host = HOSTNAME_LABEL
    sod = start_of_day_ts()
    now = now_ts()

    logger.debug("Scrape start (host=%s, sod=%s, now=%s, tz=%s)", host, sod, now, EXPORTER_TZ)

    # clear “top” and destination series each scrape to avoid stale labelsets
    pihole_top_ads.clear()
    pihole_top_queries.clear()
    pihole_top_sources.clear()
    pihole_forward_destinations.clear()
    pihole_forward_destinations_responsetime.clear()
    pihole_forward_destinations_responsevariance.clear()

    blocked_list = ",".join(str(x) for x in sorted(BLOCKED_STATUSES))

    with sqlite_ro(FTL_DB_PATH) as conn:
        cur = conn.cursor()

        # Pi-hole status: DB reachable => 1 (best-effort without API)
        pihole_status.labels(host).set(1)

        # --- Lifetime totals from FTL counters table (2 SQL queries) ---
        # id=0: total queries, id=1: blocked queries
        cur.execute("SELECT value FROM counters WHERE id = 0;")
        _total_queries_lifetime = int(cur.fetchone()[0])

        cur.execute("SELECT value FROM counters WHERE id = 1;")
        _blocked_queries_lifetime = int(cur.fetchone()[0])

        logger.debug(
            "FTL counters: total=%d blocked=%d", _total_queries_lifetime, _blocked_queries_lifetime
        )

        # --- NEW: Lifetime per-destination totals (derived) ---
        # These are computed from the full queries table (no timestamp filter).
        # This enables proper per-hour rates in HA via utility_meter/statistics.
        if ENABLE_LIFETIME_DEST_COUNTERS:
            lifetime = {}

            # Forwarded destinations: status=2, forward not null
            cur.execute(
                """
                SELECT forward, COUNT(*)
                FROM queries
                WHERE status = 2
                  AND forward IS NOT NULL
                GROUP BY forward;
                """
            )
            for fwd, cnt in cur.fetchall():
                lifetime[str(fwd)] = int(cnt)

            # Cache: status=3
            cur.execute("SELECT COUNT(*) FROM queries WHERE status = 3;")
            lifetime["cache"] = int(cur.fetchone()[0])

            # Blocklist/blocked: status in blocked list
            cur.execute(f"SELECT COUNT(*) FROM queries WHERE status IN ({blocked_list});")
            lifetime["blocklist"] = int(cur.fetchone()[0])

            _forward_destinations_lifetime = lifetime
            logger.debug(
                "Lifetime destinations computed: %d labelsets", len(_forward_destinations_lifetime)
            )
        else:
            _forward_destinations_lifetime = {}

        # Clients ever seen
        cur.execute("SELECT COUNT(*) FROM client_by_id;")
        pihole_clients_ever_seen.labels(host).set(float(cur.fetchone()[0]))

        # Queries today (time-windowed)
        cur.execute(
            """
            SELECT COUNT(*)
            FROM queries
            WHERE timestamp >= ?;
            """,
            (sod,),
        )
        q_today = int(cur.fetchone()[0])

        # Blocked today (time-windowed)
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM queries
            WHERE timestamp >= ?
              AND status IN ({blocked_list});
            """,
            (sod,),
        )
        b_today = int(cur.fetchone()[0])

        pihole_dns_queries_today.labels(host).set(float(q_today))
        pihole_dns_queries_all_types.labels(host).set(float(q_today))
        pihole_ads_blocked_today.labels(host).set(float(b_today))
        pihole_ads_percentage_today.labels(host).set(
            (b_today / q_today * 100.0) if q_today > 0 else 0.0
        )

        # Unique clients/domains in last 24h
        cur.execute(
            "SELECT COUNT(DISTINCT client) FROM queries WHERE timestamp >= ?;", (now - 86400,)
        )
        pihole_unique_clients.labels(host).set(float(cur.fetchone()[0]))

        cur.execute(
            "SELECT COUNT(DISTINCT domain) FROM queries WHERE timestamp >= ?;", (now - 86400,)
        )
        pihole_unique_domains.labels(host).set(float(cur.fetchone()[0]))

        # Query types today
        cur.execute(
            """
            SELECT type, COUNT(*)
            FROM queries
            WHERE timestamp >= ?
            GROUP BY type;
            """,
            (sod,),
        )
        counts_by_type = {k: 0 for k in QUERY_TYPE_MAP.keys()}
        for t, c in cur.fetchall():
            counts_by_type[int(t)] = int(c)

        for tid, name in QUERY_TYPE_MAP.items():
            pihole_querytypes.labels(host, name).set(float(counts_by_type.get(tid, 0)))

        # Reply types today
        cur.execute(
            """
            SELECT reply_type, COUNT(*)
            FROM queries
            WHERE timestamp >= ?
            GROUP BY reply_type;
            """,
            (sod,),
        )
        counts_by_reply = {k: 0 for k in REPLY_TYPE_MAP.keys()}
        for rt, c in cur.fetchall():
            if rt is None:
                continue
            counts_by_reply[int(rt)] = int(c)

        for rid, label in REPLY_TYPE_MAP.items():
            pihole_reply.labels(host, label).set(float(counts_by_reply.get(rid, 0)))

        # Cached vs forwarded today
        cur.execute("SELECT COUNT(*) FROM queries WHERE timestamp >= ? AND status = 2;", (sod,))
        pihole_queries_forwarded.labels(host).set(float(cur.fetchone()[0]))

        cur.execute("SELECT COUNT(*) FROM queries WHERE timestamp >= ? AND status = 3;", (sod,))
        pihole_queries_cached.labels(host).set(float(cur.fetchone()[0]))

        # Forward destinations (today)
        cur.execute(
            """
            SELECT forward, COUNT(*), AVG(reply_time)
            FROM queries
            WHERE timestamp >= ?
              AND status = 2
              AND forward IS NOT NULL
            GROUP BY forward
            ORDER BY COUNT(*) DESC;
            """,
            (sod,),
        )
        forwards = cur.fetchall()

        for fwd, cnt, avg_rt in forwards:
            dest = str(fwd)
            pihole_forward_destinations.labels(host, dest, dest).set(float(cnt))
            pihole_forward_destinations_responsetime.labels(host, dest, dest).set(
                float(avg_rt or 0.0)
            )

            cur.execute(
                """
                SELECT reply_time
                FROM queries
                WHERE timestamp >= ?
                  AND status = 2
                  AND forward = ?
                  AND reply_time IS NOT NULL;
                """,
                (sod, fwd),
            )
            vals = [float(r[0]) for r in cur.fetchall()]
            pihole_forward_destinations_responsevariance.labels(host, dest, dest).set(
                float(variance(vals))
            )

        # Synthetic destinations cache + blocklist (today)
        cur.execute("SELECT COUNT(*) FROM queries WHERE timestamp >= ? AND status = 3;", (sod,))
        cache_cnt = int(cur.fetchone()[0])
        pihole_forward_destinations.labels(host, "cache", "cache").set(float(cache_cnt))
        pihole_forward_destinations_responsetime.labels(host, "cache", "cache").set(0.0)
        pihole_forward_destinations_responsevariance.labels(host, "cache", "cache").set(0.0)

        cur.execute(
            f"""
            SELECT COUNT(*) FROM queries
            WHERE timestamp >= ?
              AND status IN ({blocked_list});
            """,
            (sod,),
        )
        bl_cnt = int(cur.fetchone()[0])
        pihole_forward_destinations.labels(host, "blocklist", "blocklist").set(float(bl_cnt))
        pihole_forward_destinations_responsetime.labels(host, "blocklist", "blocklist").set(0.0)
        pihole_forward_destinations_responsevariance.labels(host, "blocklist", "blocklist").set(0.0)

        # Top ads / queries / sources today
        cur.execute(
            f"""
            SELECT domain, COUNT(*) AS cnt
            FROM queries
            WHERE timestamp >= ?
              AND status IN ({blocked_list})
            GROUP BY domain
            ORDER BY cnt DESC
            LIMIT {TOP_N};
            """,
            (sod,),
        )
        for domain, cnt in cur.fetchall():
            pihole_top_ads.labels(host, str(domain)).set(float(cnt))

        cur.execute(
            f"""
            SELECT domain, COUNT(*) AS cnt
            FROM queries
            WHERE timestamp >= ?
            GROUP BY domain
            ORDER BY cnt DESC
            LIMIT {TOP_N};
            """,
            (sod,),
        )
        for domain, cnt in cur.fetchall():
            pihole_top_queries.labels(host, str(domain)).set(float(cnt))

        cur.execute(
            f"""
            SELECT q.client, COALESCE(c.name,''), COUNT(*) AS cnt
            FROM queries q
            LEFT JOIN client_by_id c ON c.ip = q.client
            WHERE q.timestamp >= ?
            GROUP BY q.client, c.name
            ORDER BY cnt DESC
            LIMIT {TOP_N};
            """,
            (sod,),
        )
        for ip, name, cnt in cur.fetchall():
            pihole_top_sources.labels(host, str(ip), str(name or "")).set(float(cnt))

    # domains_being_blocked: try gravity.db if present, else fallback
    domains_value = None
    try:
        with sqlite_ro(GRAVITY_DB_PATH) as gconn:
            gcur = gconn.cursor()
            gcur.execute("SELECT COUNT(*) FROM gravity;")
            domains_value = int(gcur.fetchone()[0])
    except Exception as e:
        logger.info("Gravity DB unavailable; falling back (reason: %s)", e)
        domains_value = None

    if domains_value is None:
        try:
            with sqlite_ro(FTL_DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM domain_by_id;")
                domains_value = int(cur.fetchone()[0])
        except Exception as e:
            logger.warning("Fallback domain count failed: %s", e)
            domains_value = 0

    pihole_domains_being_blocked.labels(host).set(float(domains_value))


def refresh_counters_only() -> None:
    global _total_queries_lifetime, _blocked_queries_lifetime

    host = HOSTNAME_LABEL
    with sqlite_ro(FTL_DB_PATH) as conn:
        cur = conn.cursor()
        pihole_status.labels(host).set(1)

        cur.execute("SELECT value FROM counters WHERE id = 0;")
        _total_queries_lifetime = int(cur.fetchone()[0])

        cur.execute("SELECT value FROM counters WHERE id = 1;")
        _blocked_queries_lifetime = int(cur.fetchone()[0])

    logger.debug(
        "FTL counters: total=%d blocked=%d", _total_queries_lifetime, _blocked_queries_lifetime
    )


def update_request_rate_for_request(now: float | None = None) -> None:
    global _last_request_ts, _last_request_total, _last_request_rowid
    global _total_queries_lifetime, _blocked_queries_lifetime

    if now is None:
        now = time.time()

    host = HOSTNAME_LABEL
    rowid = _last_request_rowid
    try:
        with sqlite_ro(FTL_DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM counters WHERE id = 0;")
            _total_queries_lifetime = int(cur.fetchone()[0])
            cur.execute("SELECT value FROM counters WHERE id = 1;")
            _blocked_queries_lifetime = int(cur.fetchone()[0])
            cur.execute("SELECT MAX(rowid) FROM queries;")
            rowid = cur.fetchone()[0]
    except Exception:
        logger.exception("Failed to refresh counters for request rate")

    if _last_request_ts is not None:
        dt = max(1.0, now - _last_request_ts)
        dq = 0
        if _last_request_rowid is not None and rowid is not None and rowid > _last_request_rowid:
            try:
                with sqlite_ro(FTL_DB_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT COUNT(*) FROM queries WHERE rowid > ?;",
                        (_last_request_rowid,),
                    )
                    dq = int(cur.fetchone()[0])
            except Exception:
                logger.exception("Failed to compute request rate from queries table")
                dq = 0
        elif _last_request_total is not None:
            dq = max(0, _total_queries_lifetime - _last_request_total)

        rate = dq / dt
        pihole_request_rate.labels(host).set(rate)
        logger.debug("Request rate queries_delta=%d time_delta=%.3f rate=%.6f", dq, dt, rate)
    else:
        pihole_request_rate.labels(host).set(0.0)
        logger.debug("Request rate initialized to 0.0")

    _last_request_ts = now
    _last_request_total = _total_queries_lifetime
    _last_request_rowid = rowid


# ----------------------------
# HTTP handler
# ----------------------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/metrics", "/"):
            self.send_response(404)
            self.end_headers()
            return

        try:
            logger.info("HTTP request: %s %s", self.command, self.path)
            start = time.time()
            update_request_rate_for_request(start)
            payload = generate_latest(REGISTRY)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            elapsed = time.time() - start
            logger.info("HTTP 200 served metrics bytes=%d scrape_time=%.3fs", len(payload), elapsed)
        except (BrokenPipeError, ConnectionResetError) as e:
            logger.debug("Client disconnected while serving request: %s", e)
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


def _scrape_loop(
    stop_event: threading.Event | None = None,
    sleep_fn=time.sleep,
    time_fn=time.time,
) -> None:
    interval = max(1, SCRAPE_INTERVAL)
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        start = time_fn()
        try:
            scrape_and_update()
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
    verbose = bool(args.verbose) or _env_truthy("DEBUG", "false")
    configure_logging(verbose)
    logger.info("Exporter version=%s commit=%s", _read_version(), _read_commit())

    logger.info(
        (
            "Starting exporter (listen=%s:%s, tz=%s, ftl_db=%s, gravity_db=%s, top_n=%s, "
            "lifetime_dest_counters=%s)"
        ),
        LISTEN_ADDR,
        LISTEN_PORT,
        EXPORTER_TZ,
        FTL_DB_PATH,
        GRAVITY_DB_PATH,
        TOP_N,
        ENABLE_LIFETIME_DEST_COUNTERS,
    )

    try:
        scrape_and_update()
    except Exception:
        logger.exception("Initial scrape failed")

    thread = threading.Thread(target=_scrape_loop, daemon=True)
    thread.start()

    httpd = HTTPServer((LISTEN_ADDR, LISTEN_PORT), Handler)
    logger.info("HTTP server ready; waiting for scrapes")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
