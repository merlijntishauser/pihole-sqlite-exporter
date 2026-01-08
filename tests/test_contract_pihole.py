import os
import sqlite3
import time

import pytest

from pihole_sqlite_exporter import constants, metrics, queries, scraper
from pihole_sqlite_exporter.settings import Settings


def _get_contract_paths() -> tuple[str, str]:
    ftl_db = os.environ.get("PIHOLE_FTL_DB", "")
    gravity_db = os.environ.get("PIHOLE_GRAVITY_DB", "")
    if os.environ.get("PIHOLE_CONTRACT") != "1":
        pytest.skip("PIHOLE_CONTRACT not enabled")
    if not ftl_db or not gravity_db:
        pytest.skip("PIHOLE contract DB paths not provided")
    if not os.path.exists(ftl_db) or not os.path.exists(gravity_db):
        pytest.skip("PIHOLE contract DB files not found")
    return ftl_db, gravity_db


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return {row[1] for row in rows}


def test_pihole_schema_contract() -> None:
    ftl_db, gravity_db = _get_contract_paths()
    with sqlite3.connect(ftl_db) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table';")
        }
        assert "counters" in tables
        assert "queries" in tables
        assert "client_by_id" in tables
        assert "domain_by_id" in tables

        counters_cols = _columns(conn, "counters")
        assert {"id", "value"}.issubset(counters_cols)

        query_cols = _columns(conn, "queries")
        assert {
            "status",
            "forward",
            "timestamp",
            "reply_time",
            "type",
            "reply_type",
            "domain",
            "client",
        }.issubset(query_cols)

    with sqlite3.connect(gravity_db) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table';")
        }
        assert "gravity" in tables


def test_pihole_queries_execute() -> None:
    ftl_db, _gravity_db = _get_contract_paths()
    blocked_list = ",".join(str(x) for x in sorted(constants.BLOCKED_STATUSES))
    sod = int(time.time()) - 3600
    with sqlite3.connect(ftl_db) as conn:
        cur = conn.cursor()
        cur.execute(queries.SQL_COUNTER_TOTAL)
        cur.execute(queries.SQL_COUNTER_BLOCKED)
        cur.execute(queries.SQL_CLIENTS_EVER_SEEN)
        cur.execute(queries.SQL_DOMAIN_BY_ID_COUNT)
        cur.execute(queries.SQL_LIFETIME_FORWARD_DESTS)
        cur.execute(queries.SQL_LIFETIME_CACHE)
        cur.execute(queries.SQL_LIFETIME_BLOCKED.format(blocked_list=blocked_list))
        cur.execute(queries.SQL_QUERIES_TODAY, (sod,))
        cur.execute(queries.SQL_BLOCKED_TODAY.format(blocked_list=blocked_list), (sod,))
        cur.execute(queries.SQL_UNIQUE_CLIENTS, (sod,))
        cur.execute(queries.SQL_UNIQUE_DOMAINS, (sod,))
        cur.execute(queries.SQL_QUERY_TYPES, (sod,))
        cur.execute(queries.SQL_REPLY_TYPES, (sod,))
        cur.execute(queries.SQL_FORWARDED_TODAY, (sod,))
        cur.execute(queries.SQL_CACHED_TODAY, (sod,))
        cur.execute(queries.SQL_FORWARD_DESTS_TODAY, (sod,))
        cur.execute(queries.SQL_FORWARD_REPLY_TIMES, (sod, "1.1.1.1"))
        cur.execute(queries.SQL_TOP_ADS.format(blocked_list=blocked_list, top_n=5), (sod,))
        cur.execute(queries.SQL_TOP_QUERIES.format(top_n=5), (sod,))
        cur.execute(queries.SQL_TOP_SOURCES.format(top_n=5), (sod,))


def test_pihole_scrape_contract() -> None:
    ftl_db, gravity_db = _get_contract_paths()
    settings = Settings.from_env(
        {
            "FTL_DB_PATH": ftl_db,
            "GRAVITY_DB_PATH": gravity_db,
            "LISTEN_ADDR": "127.0.0.1",
            "LISTEN_PORT": "9617",
            "HOSTNAME_LABEL": "contract-host",
            "TOP_N": "5",
            "SCRAPE_INTERVAL": "10",
            "EXPORTER_TZ": "UTC",
            "ENABLE_LIFETIME_DEST_COUNTERS": "true",
            "LIFETIME_DEST_CACHE_SECONDS": "0",
            "LIFETIME_DEST_SCAN_INTERVAL": "1",
            "LIFETIME_DEST_MAX_ENTRIES": "2000",
            "SUMMARY_ONLY": "false",
        }
    )
    metrics_obj = metrics.Metrics(settings.hostname_label)
    context = scraper.new_context(
        settings=settings,
        metrics_obj=metrics_obj,
        logger_obj=scraper.logger,
    )

    scraper.scrape_and_update(context=context)
    snapshot = context.metrics.get_snapshot()
    assert snapshot.payload
