import logging
import sqlite3
import time
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry, Gauge

from pihole_sqlite_exporter.db import sqlite_ro
from pihole_sqlite_exporter.request_rate import RequestRateTracker


def _create_request_rate_db(path: Path, without_rowid: bool) -> None:
    now_ts = int(time.time())
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE counters (id INTEGER, value INTEGER);")
    cur.executemany(
        "INSERT INTO counters (id, value) VALUES (?, ?);",
        [(0, 10), (1, 2)],
    )

    if without_rowid:
        cur.execute(
            """
            CREATE TABLE queries (
                timestamp INTEGER,
                status INTEGER,
                type INTEGER,
                reply_type INTEGER,
                forward TEXT,
                reply_time REAL,
                domain TEXT,
                client TEXT,
                PRIMARY KEY (timestamp, domain, client)
            ) WITHOUT ROWID;
            """
        )
    else:
        cur.execute(
            """
            CREATE TABLE queries (
                timestamp INTEGER,
                status INTEGER,
                type INTEGER,
                reply_type INTEGER,
                forward TEXT,
                reply_time REAL,
                domain TEXT,
                client TEXT
            );
            """
        )

    cur.execute(
        """
        INSERT INTO queries (
            timestamp, status, type, reply_type, forward, reply_time, domain, client
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (now_ts - 10, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
    )
    conn.commit()
    conn.close()


def _make_rate_tracker() -> tuple[RequestRateTracker, Gauge]:
    registry = CollectorRegistry()
    rate_gauge = Gauge("request_rate", "rate", ["hostname"], registry=registry)
    return RequestRateTracker(), rate_gauge


class TestRequestRate:
    def test_request_rate_uses_rowid_cursor(self, tmp_path: Path, caplog) -> None:
        db_path = tmp_path / "ftl.db"
        _create_request_rate_db(db_path, without_rowid=False)
        tracker, rate_gauge = _make_rate_tracker()
        logger = logging.getLogger("pihole_sqlite_exporter")

        with caplog.at_level("WARNING"):
            tracker.update(
                now=1000.0,
                db_path=str(db_path),
                host="test-host",
                rate_gauge=rate_gauge,
                sqlite_ro=sqlite_ro,
                logger=logger,
            )

        assert "Request rate cursor unavailable" not in caplog.text

    def test_request_rate_logs_fallback_once(self, tmp_path: Path, caplog) -> None:
        db_path = tmp_path / "ftl-no-rowid.db"
        _create_request_rate_db(db_path, without_rowid=True)
        tracker, rate_gauge = _make_rate_tracker()
        logger = logging.getLogger("pihole_sqlite_exporter")

        with caplog.at_level("WARNING"):
            tracker.update(
                now=1000.0,
                db_path=str(db_path),
                host="test-host",
                rate_gauge=rate_gauge,
                sqlite_ro=sqlite_ro,
                logger=logger,
            )
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("UPDATE counters SET value = ? WHERE id = 0;", (15,))
            conn.commit()
            conn.close()
            tracker.update(
                now=1010.0,
                db_path=str(db_path),
                host="test-host",
                rate_gauge=rate_gauge,
                sqlite_ro=sqlite_ro,
                logger=logger,
            )

        warnings = [
            record
            for record in caplog.records
            if "Request rate cursor unavailable" in record.message
        ]
        assert len(warnings) == 1
        assert rate_gauge.labels("test-host")._value.get() == pytest.approx(0.5)
