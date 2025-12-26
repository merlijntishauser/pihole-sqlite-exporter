import sqlite3
import sys
import time
from pathlib import Path

import pytest
from prometheus_client import generate_latest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pihole_sqlite_exporter import exporter as exp  # noqa: E402


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


def _create_ftl_db(path: Path, now_ts: int) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE counters (id INTEGER, value INTEGER);")
    cur.executemany(
        "INSERT INTO counters (id, value) VALUES (?, ?);",
        [(0, 5), (1, 1)],
    )
    cur.execute("CREATE TABLE client_by_id (ip TEXT, name TEXT);")
    cur.executemany(
        "INSERT INTO client_by_id (ip, name) VALUES (?, ?);",
        [("10.0.0.1", "client-a"), ("10.0.0.2", "")],
    )
    cur.execute("CREATE TABLE domain_by_id (id INTEGER);")
    cur.executemany("INSERT INTO domain_by_id (id) VALUES (?);", [(1,), (2,)])

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
    cur.executemany(
        """
        INSERT INTO queries (
            timestamp, status, type, reply_type, forward, reply_time, domain, client
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        [
            (now_ts - 10, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
            (now_ts - 20, 3, 2, 2, None, None, "cached.com", "10.0.0.2"),
            (now_ts - 30, 1, 1, 2, None, None, "ads.com", "10.0.0.1"),
        ],
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


def test_env_truthy_reads_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_TRUTHY", "yes")
    assert exp._env_truthy("TEST_TRUTHY") is True


def test_env_truthy_reads_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_FALSY", "0")
    assert exp._env_truthy("TEST_FALSY") is False


def test_env_truthy_default_true() -> None:
    assert exp._env_truthy("MISSING", "true") is True


def test_variance_empty() -> None:
    assert exp.variance([]) == 0.0


def test_variance_constant() -> None:
    assert exp.variance([1, 1, 1]) == 0.0


def test_variance_simple_series() -> None:
    assert exp.variance([1, 2, 3]) == pytest.approx(2.0 / 3.0)


def _setup_scrape_env(tmp_path: Path) -> None:
    now_ts = int(time.time())
    ftl_path = tmp_path / "pihole-FTL.db"
    gravity_path = tmp_path / "gravity.db"
    _create_ftl_db(ftl_path, now_ts)
    _create_gravity_db(gravity_path)

    exp.FTL_DB_PATH = str(ftl_path)
    exp.GRAVITY_DB_PATH = str(gravity_path)
    exp.HOSTNAME_LABEL = "test-host"
    exp.EXPORTER_TZ = "UTC"
    exp.TOP_N = 10
    exp.ENABLE_LIFETIME_DEST_COUNTERS = False
    exp._last_total_queries_lifetime = None
    exp._last_rate_ts = None


def _scrape_metrics() -> str:
    exp.scrape_and_update()
    return generate_latest(exp.REGISTRY).decode("utf-8")


def test_scrape_dns_queries_today(tmp_path: Path) -> None:
    _setup_scrape_env(tmp_path)
    metrics = _scrape_metrics()
    assert _metric_value(metrics, "pihole_dns_queries_today", {"hostname": "test-host"}) == 3.0


def test_scrape_ads_blocked_today(tmp_path: Path) -> None:
    _setup_scrape_env(tmp_path)
    metrics = _scrape_metrics()
    assert _metric_value(metrics, "pihole_ads_blocked_today", {"hostname": "test-host"}) == 1.0


def test_scrape_ads_percentage_today(tmp_path: Path) -> None:
    _setup_scrape_env(tmp_path)
    metrics = _scrape_metrics()
    assert _metric_value(metrics, "pihole_ads_percentage_today", {"hostname": "test-host"}) == pytest.approx(
        100.0 / 3.0
    )


def test_scrape_queries_forwarded(tmp_path: Path) -> None:
    _setup_scrape_env(tmp_path)
    metrics = _scrape_metrics()
    assert _metric_value(metrics, "pihole_queries_forwarded", {"hostname": "test-host"}) == 1.0


def test_scrape_queries_cached(tmp_path: Path) -> None:
    _setup_scrape_env(tmp_path)
    metrics = _scrape_metrics()
    assert _metric_value(metrics, "pihole_queries_cached", {"hostname": "test-host"}) == 1.0


def test_scrape_domains_being_blocked(tmp_path: Path) -> None:
    _setup_scrape_env(tmp_path)
    metrics = _scrape_metrics()
    assert _metric_value(metrics, "pihole_domains_being_blocked", {"hostname": "test-host"}) == 4.0


def test_scrape_request_rate_initial(tmp_path: Path) -> None:
    _setup_scrape_env(tmp_path)
    metrics = _scrape_metrics()
    assert _metric_value(metrics, "pihole_request_rate", {"hostname": "test-host"}) == 0.0
