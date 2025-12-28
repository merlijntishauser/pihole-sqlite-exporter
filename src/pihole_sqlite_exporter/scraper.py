import logging
import os
import sqlite3
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import metrics
from .db import sqlite_ro
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
    SQL_TOP_ADS,
    SQL_TOP_QUERIES,
    SQL_TOP_SOURCES,
    SQL_UNIQUE_CLIENTS,
    SQL_UNIQUE_DOMAINS,
)

logger = logging.getLogger("pihole_sqlite_exporter")
_SCRAPE_LOCK = threading.Lock()


def env_truthy(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


FTL_DB_PATH = os.getenv("FTL_DB_PATH", "/etc/pihole/pihole-FTL.db")
GRAVITY_DB_PATH = os.getenv("GRAVITY_DB_PATH", "/etc/pihole/gravity.db")

LISTEN_ADDR = os.getenv("LISTEN_ADDR", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "9617"))

HOSTNAME_LABEL = os.getenv("HOSTNAME_LABEL", "host.docker.internal")
TOP_N = int(os.getenv("TOP_N", "10"))
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "15"))

EXPORTER_TZ = os.getenv("EXPORTER_TZ", "Europe/Amsterdam")
ENABLE_LIFETIME_DEST_COUNTERS = env_truthy("ENABLE_LIFETIME_DEST_COUNTERS", "true")

metrics.METRICS.set_hostname_label(HOSTNAME_LABEL)


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
    1: "no_data",
    2: "nx_domain",
    3: "cname",
    4: "ip",
    5: "domain",
    6: "rr_name",
    7: "serv_fail",
    8: "refused",
    9: "not_imp",
    10: "other",
    11: "dnssec",
    12: "none",
    13: "blob",
}


def get_tz() -> ZoneInfo:
    try:
        return ZoneInfo(EXPORTER_TZ)
    except Exception as e:
        logger.warning(
            "Invalid EXPORTER_TZ=%r; falling back to local tz. Reason: %s", EXPORTER_TZ, e
        )
        return datetime.now().astimezone().tzinfo  # type: ignore[return-value]


def start_of_day_ts() -> int:
    tz = get_tz()
    now = datetime.now(tz=tz)
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(sod.timestamp())


def now_ts() -> int:
    return int(time.time())


def variance(values):
    count = len(values)
    if count == 0:
        return 0.0
    mean = sum(values) / count
    return sum((x - mean) ** 2 for x in values) / count


def _blocked_status_list() -> str:
    return ",".join(str(x) for x in sorted(BLOCKED_STATUSES))


def _load_counters(cur: sqlite3.Cursor, host: str) -> tuple[int, int]:
    metrics.METRICS.pihole_status.labels(host).set(1)

    cur.execute(SQL_COUNTER_TOTAL)
    total_queries_lifetime = int(cur.fetchone()[0])

    cur.execute(SQL_COUNTER_BLOCKED)
    blocked_queries_lifetime = int(cur.fetchone()[0])

    metrics.METRICS.set_lifetime_totals(total_queries_lifetime, blocked_queries_lifetime)
    logger.debug(
        "FTL counters: total=%d blocked=%d",
        total_queries_lifetime,
        blocked_queries_lifetime,
    )
    return total_queries_lifetime, blocked_queries_lifetime


def _load_lifetime_destinations(cur: sqlite3.Cursor, blocked_list: str) -> None:
    if not ENABLE_LIFETIME_DEST_COUNTERS:
        metrics.METRICS.set_forward_destinations_lifetime({})
        return

    lifetime = {}
    cur.execute(SQL_LIFETIME_FORWARD_DESTS)
    for fwd, cnt in cur.fetchall():
        lifetime[str(fwd)] = int(cnt)

    cur.execute(SQL_LIFETIME_CACHE)
    lifetime["cache"] = int(cur.fetchone()[0])

    cur.execute(SQL_LIFETIME_BLOCKED.format(blocked_list=blocked_list))
    lifetime["blocklist"] = int(cur.fetchone()[0])

    metrics.METRICS.set_forward_destinations_lifetime(lifetime)
    logger.debug("Lifetime destinations computed: %d labelsets", len(lifetime))


def _load_clients_ever_seen(cur: sqlite3.Cursor, host: str) -> None:
    cur.execute(SQL_CLIENTS_EVER_SEEN)
    metrics.METRICS.pihole_clients_ever_seen.labels(host).set(float(cur.fetchone()[0]))


def _load_queries_today(cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str) -> None:
    cur.execute(SQL_QUERIES_TODAY, (sod,))
    q_today = int(cur.fetchone()[0])

    cur.execute(SQL_BLOCKED_TODAY.format(blocked_list=blocked_list), (sod,))
    b_today = int(cur.fetchone()[0])

    metrics.METRICS.pihole_dns_queries_today.labels(host).set(float(q_today))
    metrics.METRICS.pihole_dns_queries_all_types.labels(host).set(float(q_today))
    metrics.METRICS.pihole_ads_blocked_today.labels(host).set(float(b_today))
    metrics.METRICS.pihole_ads_percentage_today.labels(host).set(
        (b_today / q_today * 100.0) if q_today > 0 else 0.0
    )


def _load_unique_counts(cur: sqlite3.Cursor, host: str, now: int) -> None:
    cur.execute(SQL_UNIQUE_CLIENTS, (now - 86400,))
    metrics.METRICS.pihole_unique_clients.labels(host).set(float(cur.fetchone()[0]))

    cur.execute(SQL_UNIQUE_DOMAINS, (now - 86400,))
    metrics.METRICS.pihole_unique_domains.labels(host).set(float(cur.fetchone()[0]))


def _load_query_types(cur: sqlite3.Cursor, host: str, sod: int) -> None:
    cur.execute(SQL_QUERY_TYPES, (sod,))
    counts_by_type = {k: 0 for k in QUERY_TYPE_MAP.keys()}
    for t, c in cur.fetchall():
        counts_by_type[int(t)] = int(c)
    for tid, name in QUERY_TYPE_MAP.items():
        metrics.METRICS.pihole_querytypes.labels(host, name).set(float(counts_by_type.get(tid, 0)))


def _load_reply_types(cur: sqlite3.Cursor, host: str, sod: int) -> None:
    cur.execute(SQL_REPLY_TYPES, (sod,))
    counts_by_reply = {k: 0 for k in REPLY_TYPE_MAP.keys()}
    for rt, c in cur.fetchall():
        if rt is None:
            continue
        counts_by_reply[int(rt)] = int(c)
    for rid, label in REPLY_TYPE_MAP.items():
        metrics.METRICS.pihole_reply.labels(host, label).set(float(counts_by_reply.get(rid, 0)))


def _load_forwarded_cached(cur: sqlite3.Cursor, host: str, sod: int) -> None:
    cur.execute(SQL_FORWARDED_TODAY, (sod,))
    forwarded = int(cur.fetchone()[0])

    cur.execute(SQL_CACHED_TODAY, (sod,))
    cached = int(cur.fetchone()[0])

    metrics.METRICS.pihole_queries_forwarded.labels(host).set(float(forwarded))
    metrics.METRICS.pihole_queries_cached.labels(host).set(float(cached))


def _load_forward_destinations(cur: sqlite3.Cursor, host: str, sod: int) -> None:
    cur.execute(SQL_FORWARD_DESTS_TODAY, (sod,))
    forwards = cur.fetchall()
    for fwd, cnt, avg_rt in forwards:
        dest = str(fwd)
        metrics.METRICS.pihole_forward_destinations.labels(host, dest, dest).set(float(cnt))
        metrics.METRICS.pihole_forward_destinations_responsetime.labels(host, dest, dest).set(
            float(avg_rt or 0.0)
        )

        cur.execute(SQL_FORWARD_REPLY_TIMES, (sod, fwd))
        vals = [float(r[0]) for r in cur.fetchall()]
        metrics.METRICS.pihole_forward_destinations_responsevariance.labels(host, dest, dest).set(
            float(variance(vals))
        )


def _load_synthetic_destinations(
    cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str
) -> None:
    cur.execute(SQL_CACHED_TODAY, (sod,))
    cache_cnt = int(cur.fetchone()[0])
    metrics.METRICS.pihole_forward_destinations.labels(host, "cache", "cache").set(float(cache_cnt))
    metrics.METRICS.pihole_forward_destinations_responsetime.labels(host, "cache", "cache").set(0.0)
    metrics.METRICS.pihole_forward_destinations_responsevariance.labels(host, "cache", "cache").set(
        0.0
    )

    cur.execute(SQL_BLOCKED_TODAY.format(blocked_list=blocked_list), (sod,))
    bl_cnt = int(cur.fetchone()[0])
    metrics.METRICS.pihole_forward_destinations.labels(host, "blocklist", "blocklist").set(
        float(bl_cnt)
    )
    metrics.METRICS.pihole_forward_destinations_responsetime.labels(
        host, "blocklist", "blocklist"
    ).set(0.0)
    metrics.METRICS.pihole_forward_destinations_responsevariance.labels(
        host, "blocklist", "blocklist"
    ).set(0.0)


def _load_top_lists(
    cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str, top_n: int
) -> None:
    cur.execute(SQL_TOP_ADS.format(blocked_list=blocked_list, top_n=top_n), (sod,))
    for domain, cnt in cur.fetchall():
        metrics.METRICS.pihole_top_ads.labels(host, str(domain)).set(float(cnt))

    cur.execute(SQL_TOP_QUERIES.format(top_n=top_n), (sod,))
    for domain, cnt in cur.fetchall():
        metrics.METRICS.pihole_top_queries.labels(host, str(domain)).set(float(cnt))

    cur.execute(SQL_TOP_SOURCES.format(top_n=top_n), (sod,))
    for ip, name, cnt in cur.fetchall():
        metrics.METRICS.pihole_top_sources.labels(host, str(ip), str(name or "")).set(float(cnt))


def _load_domains_blocked(host: str) -> None:
    domains_value = None
    try:
        with sqlite_ro(GRAVITY_DB_PATH) as gconn:
            gcur = gconn.cursor()
            gcur.execute(SQL_GRAVITY_COUNT)
            domains_value = int(gcur.fetchone()[0])
    except Exception as e:
        logger.info("Gravity DB unavailable; falling back (reason: %s)", e)
        domains_value = None

    if domains_value is None:
        try:
            with sqlite_ro(FTL_DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute(SQL_DOMAIN_BY_ID_COUNT)
                domains_value = int(cur.fetchone()[0])
        except Exception as e:
            logger.warning("Fallback domain count failed: %s", e)
            domains_value = 0

    metrics.METRICS.pihole_domains_being_blocked.labels(host).set(float(domains_value))


def scrape_and_update():
    if not _SCRAPE_LOCK.acquire(blocking=False):
        logger.info("Scrape skipped; another scrape is still in progress")
        return
    host = HOSTNAME_LABEL
    sod = start_of_day_ts()
    now = now_ts()
    start = time.perf_counter()
    success = 0.0

    logger.debug("Scrape start (host=%s, sod=%s, now=%s, tz=%s)", host, sod, now, EXPORTER_TZ)

    try:
        metrics.METRICS.clear_dynamic_series()
        blocked_list = _blocked_status_list()

        with sqlite_ro(FTL_DB_PATH) as conn:
            cur = conn.cursor()
            _load_counters(cur, host)
            _load_lifetime_destinations(cur, blocked_list)
            _load_clients_ever_seen(cur, host)
            _load_queries_today(cur, host, sod, blocked_list)
            _load_unique_counts(cur, host, now)
            _load_query_types(cur, host, sod)
            _load_reply_types(cur, host, sod)
            _load_forwarded_cached(cur, host, sod)
            _load_forward_destinations(cur, host, sod)
            _load_synthetic_destinations(cur, host, sod, blocked_list)
            _load_top_lists(cur, host, sod, blocked_list, TOP_N)

        _load_domains_blocked(host)
        success = 1.0
    finally:
        _SCRAPE_LOCK.release()
        duration = time.perf_counter() - start
        metrics.METRICS.pihole_scrape_duration_seconds.labels(host).set(duration)
        metrics.METRICS.pihole_scrape_success.labels(host).set(success)


def update_request_rate_for_request(now: float | None = None) -> None:
    total, blocked = metrics.METRICS.state.request_rate.update(
        now=now,
        db_path=FTL_DB_PATH,
        host=HOSTNAME_LABEL,
        rate_gauge=metrics.METRICS.pihole_request_rate,
        sqlite_ro=sqlite_ro,
        logger=logger,
    )
    if total is not None and blocked is not None:
        metrics.METRICS.set_lifetime_totals(total, blocked)


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


def start_background_scrape() -> threading.Thread:
    thread = threading.Thread(target=_scrape_loop, daemon=True)
    thread.start()
    return thread
