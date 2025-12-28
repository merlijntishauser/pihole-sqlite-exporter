import logging
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import metrics
from .db import sqlite_ro

logger = logging.getLogger("pihole_sqlite_exporter")


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

metrics.set_hostname_label(HOSTNAME_LABEL)


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


def scrape_and_update():
    host = HOSTNAME_LABEL
    sod = start_of_day_ts()
    now = now_ts()

    logger.debug("Scrape start (host=%s, sod=%s, now=%s, tz=%s)", host, sod, now, EXPORTER_TZ)

    metrics.clear_dynamic_series()
    blocked_list = ",".join(str(x) for x in sorted(BLOCKED_STATUSES))

    with sqlite_ro(FTL_DB_PATH) as conn:
        cur = conn.cursor()

        metrics.pihole_status.labels(host).set(1)

        cur.execute("SELECT value FROM counters WHERE id = 0;")
        total_queries_lifetime = int(cur.fetchone()[0])

        cur.execute("SELECT value FROM counters WHERE id = 1;")
        blocked_queries_lifetime = int(cur.fetchone()[0])

        metrics.set_lifetime_totals(total_queries_lifetime, blocked_queries_lifetime)
        logger.debug(
            "FTL counters: total=%d blocked=%d",
            total_queries_lifetime,
            blocked_queries_lifetime,
        )

        if ENABLE_LIFETIME_DEST_COUNTERS:
            lifetime = {}
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

            cur.execute("SELECT COUNT(*) FROM queries WHERE status = 3;")
            lifetime["cache"] = int(cur.fetchone()[0])

            cur.execute(f"SELECT COUNT(*) FROM queries WHERE status IN ({blocked_list});")
            lifetime["blocklist"] = int(cur.fetchone()[0])

            metrics.set_forward_destinations_lifetime(lifetime)
            logger.debug(
                "Lifetime destinations computed: %d labelsets",
                len(lifetime),
            )
        else:
            metrics.set_forward_destinations_lifetime({})

        cur.execute("SELECT COUNT(*) FROM client_by_id;")
        metrics.pihole_clients_ever_seen.labels(host).set(float(cur.fetchone()[0]))

        cur.execute(
            """
            SELECT COUNT(*)
            FROM queries
            WHERE timestamp >= ?;
            """,
            (sod,),
        )
        q_today = int(cur.fetchone()[0])

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

        metrics.pihole_dns_queries_today.labels(host).set(float(q_today))
        metrics.pihole_dns_queries_all_types.labels(host).set(float(q_today))
        metrics.pihole_ads_blocked_today.labels(host).set(float(b_today))
        metrics.pihole_ads_percentage_today.labels(host).set(
            (b_today / q_today * 100.0) if q_today > 0 else 0.0
        )

        cur.execute(
            "SELECT COUNT(DISTINCT client) FROM queries WHERE timestamp >= ?;", (now - 86400,)
        )
        metrics.pihole_unique_clients.labels(host).set(float(cur.fetchone()[0]))

        cur.execute(
            "SELECT COUNT(DISTINCT domain) FROM queries WHERE timestamp >= ?;", (now - 86400,)
        )
        metrics.pihole_unique_domains.labels(host).set(float(cur.fetchone()[0]))

        cur.execute(
            """
            SELECT type, COUNT(*) AS cnt
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
            metrics.pihole_querytypes.labels(host, name).set(float(counts_by_type.get(tid, 0)))

        cur.execute(
            """
            SELECT reply_type, COUNT(*) AS cnt
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
            metrics.pihole_reply.labels(host, label).set(float(counts_by_reply.get(rid, 0)))

        cur.execute("SELECT COUNT(*) FROM queries WHERE timestamp >= ? AND status = 2;", (sod,))
        forwarded = int(cur.fetchone()[0])

        cur.execute("SELECT COUNT(*) FROM queries WHERE timestamp >= ? AND status = 3;", (sod,))
        cached = int(cur.fetchone()[0])

        metrics.pihole_queries_forwarded.labels(host).set(float(forwarded))
        metrics.pihole_queries_cached.labels(host).set(float(cached))

        cur.execute(
            """
            SELECT forward, COUNT(*) AS cnt, AVG(reply_time) AS avg_rt
            FROM queries
            WHERE timestamp >= ?
              AND status = 2
              AND forward IS NOT NULL
            GROUP BY forward;
            """,
            (sod,),
        )
        forwards = cur.fetchall()
        for fwd, cnt, avg_rt in forwards:
            dest = str(fwd)
            metrics.pihole_forward_destinations.labels(host, dest, dest).set(float(cnt))
            metrics.pihole_forward_destinations_responsetime.labels(host, dest, dest).set(
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
            metrics.pihole_forward_destinations_responsevariance.labels(host, dest, dest).set(
                float(variance(vals))
            )

        cur.execute("SELECT COUNT(*) FROM queries WHERE timestamp >= ? AND status = 3;", (sod,))
        cache_cnt = int(cur.fetchone()[0])
        metrics.pihole_forward_destinations.labels(host, "cache", "cache").set(float(cache_cnt))
        metrics.pihole_forward_destinations_responsetime.labels(host, "cache", "cache").set(0.0)
        metrics.pihole_forward_destinations_responsevariance.labels(host, "cache", "cache").set(0.0)

        cur.execute(
            f"""
            SELECT COUNT(*) FROM queries
            WHERE timestamp >= ?
              AND status IN ({blocked_list});
            """,
            (sod,),
        )
        bl_cnt = int(cur.fetchone()[0])
        metrics.pihole_forward_destinations.labels(host, "blocklist", "blocklist").set(
            float(bl_cnt)
        )
        metrics.pihole_forward_destinations_responsetime.labels(host, "blocklist", "blocklist").set(
            0.0
        )
        metrics.pihole_forward_destinations_responsevariance.labels(
            host, "blocklist", "blocklist"
        ).set(0.0)

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
            metrics.pihole_top_ads.labels(host, str(domain)).set(float(cnt))

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
            metrics.pihole_top_queries.labels(host, str(domain)).set(float(cnt))

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
            metrics.pihole_top_sources.labels(host, str(ip), str(name or "")).set(float(cnt))

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

    metrics.pihole_domains_being_blocked.labels(host).set(float(domains_value))


def update_request_rate_for_request(now: float | None = None) -> None:
    total, blocked = metrics.STATE.request_rate.update(
        now=now,
        db_path=FTL_DB_PATH,
        host=HOSTNAME_LABEL,
        rate_gauge=metrics.pihole_request_rate,
        sqlite_ro=sqlite_ro,
        logger=logger,
    )
    if total is not None and blocked is not None:
        metrics.set_lifetime_totals(total, blocked)


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
