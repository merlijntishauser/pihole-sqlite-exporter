from pihole_sqlite_exporter import exporter
from pihole_sqlite_exporter.metrics import MetricsSnapshot


def test_health_status_ok(monkeypatch) -> None:
    monkeypatch.setattr(exporter.scraper.SETTINGS, "scrape_interval", 10)
    monkeypatch.setattr(
        exporter.metrics.METRICS,
        "get_snapshot",
        lambda: MetricsSnapshot(payload=b"x", timestamp=100.0),
    )
    monkeypatch.setattr(
        exporter.metrics.METRICS,
        "get_scrape_status",
        lambda: (1, 100.0, 100.0),
    )
    monkeypatch.setattr(exporter.time, "time", lambda: 115.0)

    ok, msg = exporter._health_status()

    assert ok is True
    assert msg == "ok\n"


def test_health_status_too_old(monkeypatch) -> None:
    monkeypatch.setattr(exporter.scraper.SETTINGS, "scrape_interval", 10)
    monkeypatch.setattr(
        exporter.metrics.METRICS,
        "get_snapshot",
        lambda: MetricsSnapshot(payload=b"x", timestamp=100.0),
    )
    monkeypatch.setattr(
        exporter.metrics.METRICS,
        "get_scrape_status",
        lambda: (1, 100.0, 100.0),
    )
    monkeypatch.setattr(exporter.time, "time", lambda: 121.0)

    ok, msg = exporter._health_status()

    assert ok is False
    assert msg == "snapshot too old: 21s\n"


def test_health_status_failed_scrape(monkeypatch) -> None:
    monkeypatch.setattr(exporter.scraper.SETTINGS, "scrape_interval", 10)
    monkeypatch.setattr(
        exporter.metrics.METRICS,
        "get_snapshot",
        lambda: MetricsSnapshot(payload=b"x", timestamp=100.0),
    )
    monkeypatch.setattr(
        exporter.metrics.METRICS,
        "get_scrape_status",
        lambda: (0, 100.0, 0.0),
    )
    monkeypatch.setattr(exporter.time, "time", lambda: 110.0)

    ok, msg = exporter._health_status()

    assert ok is False
    assert msg == "last scrape failed\n"


def test_ready_status_waiting(monkeypatch) -> None:
    monkeypatch.setattr(
        exporter.metrics.METRICS,
        "get_scrape_status",
        lambda: (0, 0.0, 0.0),
    )

    ok, msg = exporter._ready_status()

    assert ok is False
    assert msg == "waiting for first successful scrape\n"


def test_ready_status_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        exporter.metrics.METRICS,
        "get_scrape_status",
        lambda: (1, 120.0, 120.0),
    )

    ok, msg = exporter._ready_status()

    assert ok is True
    assert msg == "ready\n"
