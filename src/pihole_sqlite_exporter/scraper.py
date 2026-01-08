import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from prometheus_client import generate_latest

from . import metrics
from .constants import BLOCKED_STATUSES, QUERY_TYPE_MAP, REPLY_TYPE_MAP
from .db import fetch_scalar, sqlite_ro
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
from .settings import Settings

logger = logging.getLogger("pihole_sqlite_exporter")


@dataclass
class ScrapeContext:
    settings: Settings
    metrics: metrics.Metrics
    logger: logging.Logger
    scrape_lock: threading.Lock = field(default_factory=threading.Lock)
    gravity_db_fallback_logged: bool = False
    gravity_ftl_fallback_logged: bool = False
    lifetime_dest_cache: dict[str, int] = field(default_factory=dict)
    lifetime_dest_cache_ts: float = 0.0
    lifetime_dest_scan_count: int = 0


def new_context(
    *,
    settings: Settings | None = None,
    metrics_obj: metrics.Metrics | None = None,
    logger_obj: logging.Logger | None = None,
) -> ScrapeContext:
    resolved_settings = settings or Settings.from_env()
    resolved_metrics = metrics_obj or metrics.Metrics(resolved_settings.hostname_label)
    resolved_logger = logger_obj or logging.getLogger("pihole_sqlite_exporter")
    resolved_metrics.set_hostname_label(resolved_settings.hostname_label)
    return ScrapeContext(
        settings=resolved_settings,
        metrics=resolved_metrics,
        logger=resolved_logger,
    )


SETTINGS = Settings.from_env()
_DEFAULT_CONTEXT = new_context(
    settings=SETTINGS,
    metrics_obj=metrics.METRICS,
    logger_obj=logger,
)


def _get_context(context: ScrapeContext | None) -> ScrapeContext:
    return context or _DEFAULT_CONTEXT


def get_tz(context: ScrapeContext | None = None) -> ZoneInfo:
    ctx = _get_context(context)
    try:
        return ZoneInfo(ctx.settings.exporter_tz)
    except Exception as e:
        ctx.logger.warning(
            "Invalid EXPORTER_TZ=%r; falling back to local tz. Reason: %s",
            ctx.settings.exporter_tz,
            e,
        )
        return datetime.now().astimezone().tzinfo  # type: ignore[return-value]


def start_of_day_ts(context: ScrapeContext | None = None) -> int:
    tz = get_tz(context)
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


def _log_context(
    context: ScrapeContext, host: str, sod: int, now: int
) -> tuple[str, str, int, int]:
    return host, context.settings.exporter_tz, sod, now


def _load_counters(context: ScrapeContext, cur: sqlite3.Cursor, host: str) -> tuple[int, int]:
    context.metrics.pihole_status.labels(host).set(1)

    total_queries_lifetime = int(fetch_scalar(cur, SQL_COUNTER_TOTAL, default=0))
    blocked_queries_lifetime = int(fetch_scalar(cur, SQL_COUNTER_BLOCKED, default=0))

    context.metrics.set_lifetime_totals(total_queries_lifetime, blocked_queries_lifetime)
    context.logger.debug(
        "FTL counters: total=%d blocked=%d",
        total_queries_lifetime,
        blocked_queries_lifetime,
    )
    return total_queries_lifetime, blocked_queries_lifetime


def _load_lifetime_destinations(
    context: ScrapeContext, cur: sqlite3.Cursor, blocked_list: str, host: str
) -> None:
    if not context.settings.enable_lifetime_dest_counters:
        context.metrics.set_forward_destinations_lifetime({})
        context.lifetime_dest_cache = {}
        context.lifetime_dest_cache_ts = 0.0
        return

    if context.settings.summary_only:
        context.metrics.set_forward_destinations_lifetime({})
        context.lifetime_dest_cache = {}
        context.lifetime_dest_cache_ts = 0.0
        return

    cache_seconds = context.settings.lifetime_dest_cache_seconds
    now = time.time()
    if (
        cache_seconds > 0
        and context.lifetime_dest_cache
        and (now - context.lifetime_dest_cache_ts) < cache_seconds
    ):
        context.metrics.set_forward_destinations_lifetime(context.lifetime_dest_cache)
        context.metrics.record_cache_hit(host, "lifetime_destinations")
        context.logger.debug(
            "Lifetime destinations cache hit: age=%.0fs labelsets=%d",
            now - context.lifetime_dest_cache_ts,
            len(context.lifetime_dest_cache),
        )
        return

    scan_interval = context.settings.lifetime_dest_scan_interval
    scan_due = True
    if scan_interval > 1:
        scan_due = context.lifetime_dest_scan_count % scan_interval == 0
    if not scan_due and context.lifetime_dest_cache:
        context.metrics.set_forward_destinations_lifetime(context.lifetime_dest_cache)
        context.metrics.record_cache_hit(host, "lifetime_destinations")
        context.logger.debug(
            "Lifetime destinations scan skipped: interval=%d labelsets=%d",
            scan_interval,
            len(context.lifetime_dest_cache),
        )
        return

    context.metrics.record_cache_miss(host, "lifetime_destinations")
    lifetime = {}
    cur.execute(SQL_LIFETIME_FORWARD_DESTS)
    forward_entries = [(str(fwd), int(cnt)) for fwd, cnt in cur.fetchall()]
    max_entries = context.settings.lifetime_dest_max_entries
    if max_entries > 0 and len(forward_entries) > max_entries:
        forward_entries = sorted(forward_entries, key=lambda item: (-item[1], item[0]))[
            :max_entries
        ]
        context.logger.debug(
            "Lifetime destinations capped: max=%d labelsets=%d",
            max_entries,
            len(forward_entries),
        )
    for dest, cnt in forward_entries:
        lifetime[dest] = cnt

    lifetime["cache"] = int(fetch_scalar(cur, SQL_LIFETIME_CACHE, default=0))

    blocklist_value = fetch_scalar(
        cur,
        SQL_LIFETIME_BLOCKED.format(blocked_list=blocked_list),
        default=0,
    )
    lifetime["blocklist"] = int(blocklist_value)

    context.metrics.set_forward_destinations_lifetime(lifetime)
    context.lifetime_dest_cache = dict(lifetime)
    context.lifetime_dest_cache_ts = now
    context.logger.debug("Lifetime destinations computed: %d labelsets", len(lifetime))


def _load_clients_ever_seen(context: ScrapeContext, cur: sqlite3.Cursor, host: str) -> None:
    clients_seen = float(fetch_scalar(cur, SQL_CLIENTS_EVER_SEEN, default=0))
    context.metrics.pihole_clients_ever_seen.labels(host).set(clients_seen)


def _load_queries_today(
    context: ScrapeContext, cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str
) -> None:
    q_today = int(fetch_scalar(cur, SQL_QUERIES_TODAY, (sod,), default=0))

    blocked_value = fetch_scalar(
        cur,
        SQL_BLOCKED_TODAY.format(blocked_list=blocked_list),
        (sod,),
        default=0,
    )
    b_today = int(blocked_value)

    context.metrics.pihole_dns_queries_today.labels(host).set(float(q_today))
    context.metrics.pihole_dns_queries_all_types.labels(host).set(float(q_today))
    context.metrics.pihole_ads_blocked_today.labels(host).set(float(b_today))
    percentage = 0.0
    if q_today > 0:
        percentage = b_today / q_today * 100.0
    context.metrics.pihole_ads_percentage_today.labels(host).set(percentage)


def _load_unique_counts(context: ScrapeContext, cur: sqlite3.Cursor, host: str, now: int) -> None:
    unique_clients = float(fetch_scalar(cur, SQL_UNIQUE_CLIENTS, (now - 86400,), default=0))
    context.metrics.pihole_unique_clients.labels(host).set(unique_clients)

    unique_domains = float(fetch_scalar(cur, SQL_UNIQUE_DOMAINS, (now - 86400,), default=0))
    context.metrics.pihole_unique_domains.labels(host).set(unique_domains)


def _load_query_types(context: ScrapeContext, cur: sqlite3.Cursor, host: str, sod: int) -> None:
    cur.execute(SQL_QUERY_TYPES, (sod,))
    counts_by_type = {k: 0 for k in QUERY_TYPE_MAP.keys()}
    for t, c in cur.fetchall():
        counts_by_type[int(t)] = int(c)
    for tid, name in QUERY_TYPE_MAP.items():
        context.metrics.pihole_querytypes.labels(host, name).set(float(counts_by_type.get(tid, 0)))


def _load_reply_types(context: ScrapeContext, cur: sqlite3.Cursor, host: str, sod: int) -> None:
    cur.execute(SQL_REPLY_TYPES, (sod,))
    counts_by_reply = {k: 0 for k in REPLY_TYPE_MAP.keys()}
    for rt, c in cur.fetchall():
        if rt is None:
            continue
        counts_by_reply[int(rt)] = int(c)
    for rid, label in REPLY_TYPE_MAP.items():
        context.metrics.pihole_reply.labels(host, label).set(float(counts_by_reply.get(rid, 0)))


def _load_forwarded_cached(
    context: ScrapeContext, cur: sqlite3.Cursor, host: str, sod: int
) -> None:
    forwarded = int(fetch_scalar(cur, SQL_FORWARDED_TODAY, (sod,), default=0))
    cached = int(fetch_scalar(cur, SQL_CACHED_TODAY, (sod,), default=0))

    context.metrics.pihole_queries_forwarded.labels(host).set(float(forwarded))
    context.metrics.pihole_queries_cached.labels(host).set(float(cached))


def _load_forward_destinations(
    context: ScrapeContext, cur: sqlite3.Cursor, host: str, sod: int
) -> None:
    cur.execute(SQL_FORWARD_DESTS_TODAY, (sod,))
    forwards = cur.fetchall()
    for fwd, cnt, avg_rt in forwards:
        dest = str(fwd)
        context.metrics.pihole_forward_destinations.labels(host, dest, dest).set(float(cnt))
        context.metrics.pihole_forward_destinations_responsetime.labels(host, dest, dest).set(
            float(avg_rt or 0.0)
        )

        cur.execute(SQL_FORWARD_REPLY_TIMES, (sod, fwd))
        vals = [float(r[0]) for r in cur.fetchall()]
        context.metrics.pihole_forward_destinations_responsevariance.labels(host, dest, dest).set(
            float(variance(vals))
        )


def _load_synthetic_destinations(
    context: ScrapeContext, cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str
) -> None:
    cache_cnt = int(fetch_scalar(cur, SQL_CACHED_TODAY, (sod,), default=0))
    context.metrics.pihole_forward_destinations.labels(host, "cache", "cache").set(float(cache_cnt))
    context.metrics.pihole_forward_destinations_responsetime.labels(host, "cache", "cache").set(0.0)
    context.metrics.pihole_forward_destinations_responsevariance.labels(host, "cache", "cache").set(
        0.0
    )

    blocklist_value = fetch_scalar(
        cur,
        SQL_BLOCKED_TODAY.format(blocked_list=blocked_list),
        (sod,),
        default=0,
    )
    bl_cnt = int(blocklist_value)
    context.metrics.pihole_forward_destinations.labels(host, "blocklist", "blocklist").set(
        float(bl_cnt)
    )
    context.metrics.pihole_forward_destinations_responsetime.labels(
        host, "blocklist", "blocklist"
    ).set(0.0)
    context.metrics.pihole_forward_destinations_responsevariance.labels(
        host, "blocklist", "blocklist"
    ).set(0.0)


def _load_top_lists(
    context: ScrapeContext, cur: sqlite3.Cursor, host: str, sod: int, blocked_list: str, top_n: int
) -> None:
    cur.execute(SQL_TOP_ADS.format(blocked_list=blocked_list, top_n=top_n), (sod,))
    for domain, cnt in cur.fetchall():
        context.metrics.pihole_top_ads.labels(host, str(domain)).set(float(cnt))

    cur.execute(SQL_TOP_QUERIES.format(top_n=top_n), (sod,))
    for domain, cnt in cur.fetchall():
        context.metrics.pihole_top_queries.labels(host, str(domain)).set(float(cnt))

    cur.execute(SQL_TOP_SOURCES.format(top_n=top_n), (sod,))
    for ip, name, cnt in cur.fetchall():
        context.metrics.pihole_top_sources.labels(host, str(ip), str(name or "")).set(float(cnt))


def _load_domains_blocked(context: ScrapeContext, host: str) -> None:
    domains_value = None
    try:
        with sqlite_ro(context.settings.gravity_db_path) as gconn:
            gcur = gconn.cursor()
            domains_value = int(fetch_scalar(gcur, SQL_GRAVITY_COUNT, default=0))
    except Exception as e:
        if not context.gravity_db_fallback_logged:
            context.logger.info("Gravity DB unavailable; falling back (reason: %s)", e)
            context.gravity_db_fallback_logged = True
        domains_value = None

    if domains_value is None:
        try:
            with sqlite_ro(context.settings.ftl_db_path) as conn:
                cur = conn.cursor()
                domains_value = int(fetch_scalar(cur, SQL_DOMAIN_BY_ID_COUNT, default=0))
                if not context.gravity_ftl_fallback_logged:
                    context.logger.info("Gravity DB fallback: using FTL domain count")
                    context.gravity_ftl_fallback_logged = True
        except Exception as e:
            context.logger.warning("Fallback domain count failed: %s", e)
            domains_value = 0

    context.metrics.pihole_domains_being_blocked.labels(host).set(float(domains_value))


def scrape_and_update(context: ScrapeContext | None = None) -> None:
    ctx = _get_context(context)
    if not ctx.scrape_lock.acquire(blocking=False):
        log_ctx = _log_context(ctx, ctx.settings.hostname_label, start_of_day_ts(ctx), now_ts())
        ctx.logger.info(
            "Scrape skipped (host=%s, tz=%s, sod=%s, now=%s); another scrape is still in progress",
            log_ctx[0],
            log_ctx[1],
            log_ctx[2],
            log_ctx[3],
        )
        return
    host = ctx.settings.hostname_label
    sod = start_of_day_ts(ctx)
    now = now_ts()
    log_ctx = _log_context(ctx, host, sod, now)
    start = time.perf_counter()
    success = 0.0
    ctx.lifetime_dest_scan_count += 1

    ctx.logger.debug(
        "Scrape start (host=%s, sod=%s, now=%s, tz=%s)",
        log_ctx[0],
        log_ctx[2],
        log_ctx[3],
        log_ctx[1],
    )

    try:
        ctx.metrics.clear_dynamic_series()
        blocked_list = _blocked_status_list()

        with sqlite_ro(ctx.settings.ftl_db_path) as conn:
            cur = conn.cursor()
            _time_call(ctx, host, "counters", _load_counters, ctx, cur, host)
            _time_call(
                ctx,
                host,
                "lifetime_destinations",
                _load_lifetime_destinations,
                ctx,
                cur,
                blocked_list,
                host,
            )
            _time_call(ctx, host, "clients_ever_seen", _load_clients_ever_seen, ctx, cur, host)
            _time_call(
                ctx, host, "queries_today", _load_queries_today, ctx, cur, host, sod, blocked_list
            )
            _time_call(ctx, host, "unique_counts", _load_unique_counts, ctx, cur, host, now)
            _time_call(ctx, host, "query_types", _load_query_types, ctx, cur, host, sod)
            _time_call(ctx, host, "reply_types", _load_reply_types, ctx, cur, host, sod)
            _time_call(ctx, host, "forwarded_cached", _load_forwarded_cached, ctx, cur, host, sod)
            if not ctx.settings.summary_only:
                _time_call(
                    ctx,
                    host,
                    "forward_destinations",
                    _load_forward_destinations,
                    ctx,
                    cur,
                    host,
                    sod,
                )
                _time_call(
                    ctx,
                    host,
                    "synthetic_destinations",
                    _load_synthetic_destinations,
                    ctx,
                    cur,
                    host,
                    sod,
                    blocked_list,
                )
                _time_call(
                    ctx,
                    host,
                    "top_lists",
                    _load_top_lists,
                    ctx,
                    cur,
                    host,
                    sod,
                    blocked_list,
                    ctx.settings.top_n,
                )

        _time_call(ctx, host, "domains_blocked", _load_domains_blocked, ctx, host)
        success = 1.0
    except Exception:
        ctx.metrics.record_error(host, "scrape")
        ctx.logger.exception(
            "Scrape failed (host=%s, tz=%s, sod=%s, now=%s)",
            log_ctx[0],
            log_ctx[1],
            log_ctx[2],
            log_ctx[3],
        )
        raise
    finally:
        ctx.scrape_lock.release()
        duration = time.perf_counter() - start
        scrape_timestamp = time.time()
        ctx.metrics.pihole_scrape_duration_seconds.labels(host).set(duration)
        ctx.metrics.pihole_scrape_success.labels(host).set(success)
        ctx.metrics.record_scrape_result(success == 1.0, timestamp=scrape_timestamp)
        if success == 1.0:
            ctx.metrics.clear_error(host)
        try:
            ctx.metrics.update_snapshot(
                generate_latest(ctx.metrics.registry),
                timestamp=scrape_timestamp,
            )
        except Exception:
            ctx.metrics.record_error(host, "snapshot")
            ctx.logger.exception("Failed to update metrics snapshot cache")
        ctx.logger.debug(
            "Scrape completed (host=%s, tz=%s, sod=%s, now=%s) duration=%.3fs success=%s",
            log_ctx[0],
            log_ctx[1],
            log_ctx[2],
            log_ctx[3],
            duration,
            int(success),
        )


def _time_call(context: ScrapeContext, host: str, name: str, func, *args):
    start = time.perf_counter()
    result = func(*args)
    duration = time.perf_counter() - start
    context.metrics.record_query_duration(host, name, duration)
    return result


def _scrape_loop(
    context: ScrapeContext | None = None,
    stop_event: threading.Event | None = None,
    sleep_fn=time.sleep,
    time_fn=time.time,
    initial_delay: float = 0.0,
) -> None:
    ctx = _get_context(context)
    interval = max(1, ctx.settings.scrape_interval)
    host = ctx.settings.hostname_label
    last_start = None
    if initial_delay > 0:
        sleep_fn(initial_delay)
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        start = time_fn()
        if last_start is not None:
            expected = last_start + interval
            lag = 0.0
            if start > expected:
                lag = start - expected
            ctx.metrics.pihole_exporter_scrape_loop_lag_seconds.labels(host).set(lag)
        last_start = start
        try:
            scrape_and_update(context=ctx)
        except Exception:
            ctx.logger.warning("Background scrape failed")
        elapsed = time_fn() - start
        sleep_fn(max(1.0, interval - elapsed))


def start_background_scrape(
    initial_delay: float = 0.0, *, context: ScrapeContext | None = None
) -> threading.Thread:
    thread = threading.Thread(
        target=_scrape_loop,
        kwargs={"initial_delay": initial_delay, "context": _get_context(context)},
        daemon=True,
    )
    thread.start()
    return thread
