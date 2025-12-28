import time

import pytest
from prometheus_client import generate_latest

from pihole_sqlite_exporter import metrics, scraper


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        ("pihole_dns_queries_today", 3.0),
        ("pihole_ads_blocked_today", 1.0),
        ("pihole_ads_percentage_today", pytest.approx(100.0 / 3.0)),
        ("pihole_queries_forwarded", 1.0),
        ("pihole_queries_cached", 1.0),
        ("pihole_domains_being_blocked", 4.0),
        ("pihole_request_rate", 0.0),
    ],
)
def test_scrape_metrics(metric: str, expected, metrics_text: str, metric_value) -> None:
    assert metric_value(metrics_text, metric, {"hostname": "test-host"}) == expected


def test_scrape_duration_metrics(metrics_text: str, metric_value) -> None:
    duration = metric_value(
        metrics_text, "pihole_scrape_duration_seconds", {"hostname": "test-host"}
    )
    assert duration >= 0.0
    assert metric_value(metrics_text, "pihole_scrape_success", {"hostname": "test-host"}) == 1.0


def test_scrape_falls_back_when_gravity_missing(
    ftl_db_factory, tmp_path, monkeypatch: pytest.MonkeyPatch, metric_value
) -> None:
    ftl_path = ftl_db_factory(domain_count=2)
    gravity_path = tmp_path / "missing-gravity.db"
    monkeypatch.setattr(scraper, "FTL_DB_PATH", str(ftl_path))
    monkeypatch.setattr(scraper, "GRAVITY_DB_PATH", str(gravity_path))
    monkeypatch.setattr(scraper, "HOSTNAME_LABEL", "test-host")
    monkeypatch.setattr(scraper, "EXPORTER_TZ", "UTC")
    monkeypatch.setattr(scraper, "ENABLE_LIFETIME_DEST_COUNTERS", False)
    metrics.METRICS.set_hostname_label("test-host")
    metrics.METRICS.state.request_rate.reset()

    scraper.scrape_and_update()
    metrics_text = generate_latest(metrics.METRICS.registry).decode("utf-8")
    assert (
        metric_value(metrics_text, "pihole_domains_being_blocked", {"hostname": "test-host"}) == 2.0
    )


def test_request_rate_after_second_scrape(
    ftl_db_factory, monkeypatch: pytest.MonkeyPatch, add_queries, metric_value
) -> None:
    base_time = int(time.time())
    initial_queries = [
        (base_time - 120, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
        (base_time - 90, 3, 2, 2, None, None, "cached.com", "10.0.0.2"),
    ]
    ftl_path = ftl_db_factory(counters=(5, 1), queries=initial_queries)
    monkeypatch.setattr(scraper, "FTL_DB_PATH", str(ftl_path))
    monkeypatch.setattr(scraper, "GRAVITY_DB_PATH", str(ftl_path))
    monkeypatch.setattr(scraper, "HOSTNAME_LABEL", "test-host")
    monkeypatch.setattr(scraper, "EXPORTER_TZ", "UTC")
    monkeypatch.setattr(scraper, "ENABLE_LIFETIME_DEST_COUNTERS", False)
    metrics.METRICS.set_hostname_label("test-host")
    metrics.METRICS.state.request_rate.reset()

    scraper.scrape_and_update()
    scraper.update_request_rate_for_request(now=base_time)

    new_queries = [
        (base_time + 1, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
        (base_time + 2, 3, 2, 2, None, None, "cached.com", "10.0.0.2"),
        (base_time + 5, 1, 1, 2, None, None, "ads.com", "10.0.0.1"),
    ]
    add_queries(ftl_path, new_queries)
    scraper.update_request_rate_for_request(now=base_time + 10)

    metrics_text = generate_latest(metrics.METRICS.registry).decode("utf-8")
    assert metric_value(
        metrics_text, "pihole_request_rate", {"hostname": "test-host"}
    ) == pytest.approx(0.3)


def test_lifetime_destinations_metric(
    ftl_db_factory, monkeypatch: pytest.MonkeyPatch, metric_value
) -> None:
    now_ts = int(time.time())
    queries = [
        (now_ts - 10, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
        (now_ts - 20, 2, 1, 3, "1.1.1.1", 0.2, "example.com", "10.0.0.1"),
        (now_ts - 30, 3, 2, 2, None, None, "cached.com", "10.0.0.2"),
        (now_ts - 40, 1, 1, 2, None, None, "ads.com", "10.0.0.1"),
    ]
    ftl_path = ftl_db_factory(queries=queries)
    monkeypatch.setattr(scraper, "FTL_DB_PATH", str(ftl_path))
    monkeypatch.setattr(scraper, "GRAVITY_DB_PATH", str(ftl_path))
    monkeypatch.setattr(scraper, "HOSTNAME_LABEL", "test-host")
    monkeypatch.setattr(scraper, "EXPORTER_TZ", "UTC")
    monkeypatch.setattr(scraper, "ENABLE_LIFETIME_DEST_COUNTERS", True)
    metrics.METRICS.set_hostname_label("test-host")
    metrics.METRICS.state.request_rate.reset()

    scraper.scrape_and_update()
    metrics_text = generate_latest(metrics.METRICS.registry).decode("utf-8")
    assert (
        metric_value(
            metrics_text,
            "pihole_forward_destinations_total",
            {"hostname": "test-host", "destination": "1.1.1.1", "destination_name": "1.1.1.1"},
        )
        == 2.0
    )
