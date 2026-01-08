from prometheus_client import generate_latest

from pihole_sqlite_exporter.metrics import Metrics


def test_update_snapshot_sets_payload_and_timestamp() -> None:
    metrics = Metrics("example-host")
    metrics.update_snapshot(b"payload", timestamp=123.0)
    snapshot = metrics.get_snapshot()
    assert snapshot.payload == b"payload"
    assert snapshot.timestamp == 123.0


def test_record_scrape_result_tracks_last_success() -> None:
    metrics = Metrics("example-host")
    metrics.record_scrape_result(True, timestamp=10.0)
    success, scrape_ts, success_ts = metrics.get_scrape_status()
    assert success == 1
    assert scrape_ts == 10.0
    assert success_ts == 10.0

    metrics.record_scrape_result(False, timestamp=20.0)
    success, scrape_ts, success_ts = metrics.get_scrape_status()
    assert success == 0
    assert scrape_ts == 20.0
    assert success_ts == 10.0


def test_clear_dynamic_series_removes_samples() -> None:
    metrics = Metrics("example-host")
    metrics.pihole_top_ads.labels("example-host", "ad.example").set(1.0)
    metrics.pihole_top_queries.labels("example-host", "query.example").set(2.0)
    metrics.pihole_top_sources.labels("example-host", "1.2.3.4", "name").set(3.0)
    metrics.pihole_forward_destinations.labels("example-host", "1.1.1.1", "1.1.1.1").set(4.0)

    before = generate_latest(metrics.registry).decode("utf-8")
    assert "pihole_top_ads" in before
    assert "pihole_top_queries" in before
    assert "pihole_top_sources" in before
    assert "pihole_forward_destinations" in before

    metrics.clear_dynamic_series()
    after = generate_latest(metrics.registry).decode("utf-8")
    after_lines = [line for line in after.splitlines() if not line.startswith("#")]
    assert not any(line.startswith("pihole_top_ads{") for line in after_lines)
    assert not any(line.startswith("pihole_top_queries{") for line in after_lines)
    assert not any(line.startswith("pihole_top_sources{") for line in after_lines)
    assert not any(line.startswith("pihole_forward_destinations{") for line in after_lines)
