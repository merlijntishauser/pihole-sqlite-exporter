import sqlite3
import time
from pathlib import Path

import pytest
from prometheus_client import generate_latest

from pihole_sqlite_exporter import exporter as exp


def _create_ftl_db(
    path: Path,
    now_ts: int,
    counters: tuple[int, int] = (5, 1),
    queries: list[tuple[int, int, int, int | None, str | None, float | None, str, str]]
    | None = None,
    clients: list[tuple[str, str]] | None = None,
    domain_count: int = 2,
) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE counters (id INTEGER, value INTEGER);")
    cur.executemany(
        "INSERT INTO counters (id, value) VALUES (?, ?);",
        [(0, counters[0]), (1, counters[1])],
    )
    cur.execute("CREATE TABLE client_by_id (ip TEXT, name TEXT);")
    if clients is None:
        clients = [("10.0.0.1", "client-a"), ("10.0.0.2", "")]
    cur.executemany("INSERT INTO client_by_id (ip, name) VALUES (?, ?);", clients)
    cur.execute("CREATE TABLE domain_by_id (id INTEGER);")
    cur.executemany(
        "INSERT INTO domain_by_id (id) VALUES (?);", [(idx,) for idx in range(domain_count)]
    )

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
    if queries is None:
        queries = [
            (now_ts - 10, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
            (now_ts - 20, 3, 2, 2, None, None, "cached.com", "10.0.0.2"),
            (now_ts - 30, 1, 1, 2, None, None, "ads.com", "10.0.0.1"),
        ]
    cur.executemany(
        """
        INSERT INTO queries (
            timestamp, status, type, reply_type, forward, reply_time, domain, client
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        queries,
    )
    conn.commit()
    conn.close()


def _create_gravity_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE gravity (id INTEGER);")
    cur.executemany("INSERT INTO gravity (id) VALUES (?);", [(1,), (2,), (3,), (4,)])
    conn.commit()
    conn.close()


@pytest.fixture
def ftl_db(tmp_path: Path) -> Path:
    path = tmp_path / "pihole-FTL.db"
    _create_ftl_db(path, int(time.time()))
    return path


@pytest.fixture
def ftl_db_factory(tmp_path: Path):
    def _factory(
        *,
        counters: tuple[int, int] = (5, 1),
        queries: list[tuple[int, int, int, int | None, str | None, float | None, str, str]]
        | None = None,
        clients: list[tuple[str, str]] | None = None,
        domain_count: int = 2,
    ) -> Path:
        path = tmp_path / "pihole-FTL.db"
        _create_ftl_db(
            path,
            int(time.time()),
            counters=counters,
            queries=queries,
            clients=clients,
            domain_count=domain_count,
        )
        return path

    return _factory


@pytest.fixture
def update_counters():
    def _update(path: Path, total: int, blocked: int) -> None:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("UPDATE counters SET value = ? WHERE id = 0;", (total,))
        cur.execute("UPDATE counters SET value = ? WHERE id = 1;", (blocked,))
        conn.commit()
        conn.close()

    return _update


@pytest.fixture
def add_queries():
    def _add(
        path: Path,
        queries: list[tuple[int, int, int, int | None, str | None, float | None, str, str]],
    ) -> None:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO queries (
                timestamp, status, type, reply_type, forward, reply_time, domain, client
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            queries,
        )
        conn.commit()
        conn.close()

    return _add


@pytest.fixture
def gravity_db(tmp_path: Path) -> Path:
    path = tmp_path / "gravity.db"
    _create_gravity_db(path)
    return path


@pytest.fixture
def exporter_config(monkeypatch: pytest.MonkeyPatch, ftl_db: Path, gravity_db: Path) -> None:
    monkeypatch.setattr(exp, "FTL_DB_PATH", str(ftl_db))
    monkeypatch.setattr(exp, "GRAVITY_DB_PATH", str(gravity_db))
    monkeypatch.setattr(exp, "HOSTNAME_LABEL", "test-host")
    monkeypatch.setattr(exp, "EXPORTER_TZ", "UTC")
    monkeypatch.setattr(exp, "TOP_N", 10)
    monkeypatch.setattr(exp, "ENABLE_LIFETIME_DEST_COUNTERS", False)
    monkeypatch.setattr(exp, "_last_request_ts", None)
    monkeypatch.setattr(exp, "_last_request_total", None)
    monkeypatch.setattr(exp, "_last_request_rowid", None)


@pytest.fixture
def metrics_text(exporter_config: None) -> str:
    exp.scrape_and_update()
    exp.update_request_rate_for_request()
    return generate_latest(exp.REGISTRY).decode("utf-8")


@pytest.fixture
def metric_value():
    def _metric_value(text: str, name: str, labels: dict[str, str] | None = None) -> float:
        for line in text.splitlines():
            if line.startswith("#") or not line.startswith(name):
                continue
            if labels:
                if "{" not in line:
                    continue
                label_part = line.split("{", 1)[1].split("}", 1)[0]
                label_items = {}
                for item in label_part.split(","):
                    if not item:
                        continue
                    key, value = item.split("=", 1)
                    label_items[key] = value.strip('"')
                if any(label_items.get(k) != v for k, v in labels.items()):
                    continue
            return float(line.split()[-1])
        raise AssertionError(f"Metric {name} with labels {labels} not found")

    return _metric_value
