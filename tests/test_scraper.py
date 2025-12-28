import time

import pytest
from prometheus_client import generate_latest

from pihole_sqlite_exporter import exporter as exp


def _make_config(
    ftl_path: str,
    gravity_path: str,
    *,
    hostname: str = "test-host",
    tz: str = "UTC",
    lifetime: bool = False,
    request_rate_window_sec: int = 60,
) -> exp.Config:
    return exp.Config(
        ftl_db_path=ftl_path,
        gravity_db_path=gravity_path,
        listen_addr="127.0.0.1",
        listen_port=9617,
        hostname_label=hostname,
        top_n=10,
        scrape_interval=15,
        request_rate_window_sec=request_rate_window_sec,
        exporter_tz=tz,
        enable_lifetime_dest_counters=lifetime,
    )


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        ("pihole_dns_queries_today", 3.0),
        ("pihole_ads_blocked_today", 1.0),
        ("pihole_queries_forwarded", 1.0),
        ("pihole_queries_cached", 1.0),
        ("pihole_domains_being_blocked", 4.0),
    ],
)
def test_scrape_metrics(metric: str, expected, metrics_text: str, metric_value) -> None:
    assert metric_value(metrics_text, metric, {"hostname": "test-host"}) == expected


def test_ads_percentage_today(metrics_text: str, metric_value) -> None:
    assert metric_value(
        metrics_text, "pihole_ads_percentage_today", {"hostname": "test-host"}
    ) == pytest.approx(100.0 / 3.0)


def test_request_rate_uses_window(ftl_db_factory, metric_value) -> None:
    now_ts = int(time.time())
    queries = [
        (now_ts - 10, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
        (now_ts - 20, 3, 2, 2, None, None, "cached.com", "10.0.0.2"),
        (now_ts - 30, 1, 1, 2, None, None, "ads.com", "10.0.0.1"),
    ]
    ftl_path = ftl_db_factory(queries=queries)
    config = _make_config(str(ftl_path), str(ftl_path), request_rate_window_sec=60)
    scraper = exp.Scraper(config)

    scraper.refresh()
    metrics = generate_latest(scraper.registry).decode("utf-8")
    assert metric_value(metrics, "pihole_request_rate", {"hostname": "test-host"}) == 0.0
    assert (
        metric_value(metrics, "pihole_request_rate_window_seconds", {"hostname": "test-host"})
        == 60.0
    )


def test_scrape_falls_back_when_gravity_missing(ftl_db_factory, tmp_path, metric_value) -> None:
    ftl_path = ftl_db_factory(domain_count=2)
    gravity_path = tmp_path / "missing-gravity.db"
    config = _make_config(str(ftl_path), str(gravity_path))
    scraper = exp.Scraper(config)

    scraper.refresh()
    metrics = generate_latest(scraper.registry).decode("utf-8")
    assert metric_value(metrics, "pihole_domains_being_blocked", {"hostname": "test-host"}) == 2.0


def test_request_rate_after_second_scrape(
    ftl_db_factory, update_counters, metric_value, monkeypatch: pytest.MonkeyPatch
) -> None:
    ftl_path = ftl_db_factory(counters=(5, 1))
    config = _make_config(str(ftl_path), str(ftl_path), request_rate_window_sec=60)
    scraper = exp.Scraper(config)

    base_time = time.time()
    monkeypatch.setattr(exp.time, "time", lambda: base_time)
    scraper.refresh()

    update_counters(ftl_path, total=7, blocked=2)
    monkeypatch.setattr(exp.time, "time", lambda: base_time + 10)
    scraper.refresh()

    metrics = generate_latest(scraper.registry).decode("utf-8")
    assert metric_value(metrics, "pihole_request_rate", {"hostname": "test-host"}) == pytest.approx(
        2.0 / 10.0
    )


def test_lifetime_destinations_metric(ftl_db_factory, metric_value) -> None:
    now_ts = int(time.time())
    queries = [
        (now_ts - 10, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
        (now_ts - 20, 2, 1, 3, "1.1.1.1", 0.2, "example.com", "10.0.0.1"),
        (now_ts - 30, 3, 2, 2, None, None, "cached.com", "10.0.0.2"),
        (now_ts - 40, 1, 1, 2, None, None, "ads.com", "10.0.0.1"),
    ]
    ftl_path = ftl_db_factory(queries=queries)
    config = _make_config(str(ftl_path), str(ftl_path), lifetime=True)
    scraper = exp.Scraper(config)

    scraper.refresh()
    metrics = generate_latest(scraper.registry).decode("utf-8")
    assert (
        metric_value(
            metrics,
            "pihole_forward_destinations_total",
            {"hostname": "test-host", "destination": "1.1.1.1", "destination_name": "1.1.1.1"},
        )
        == 2.0
    )


def test_lifetime_destinations_disabled_has_no_samples(ftl_db_factory, metric_value) -> None:
    now_ts = int(time.time())
    queries = [
        (now_ts - 10, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
    ]
    ftl_path = ftl_db_factory(queries=queries)
    config = _make_config(str(ftl_path), str(ftl_path), lifetime=False)
    scraper = exp.Scraper(config)

    scraper.refresh()
    metrics = generate_latest(scraper.registry).decode("utf-8")
    assert "pihole_forward_destinations_total{" not in metrics


def test_scrape_handles_null_reply_type(ftl_db_factory) -> None:
    now_ts = int(time.time())
    queries = [
        (now_ts - 10, 2, 1, None, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
        (now_ts - 20, 2, 1, 3, None, 0.2, "example.com", "10.0.0.1"),
    ]
    ftl_path = ftl_db_factory(queries=queries)
    config = _make_config(str(ftl_path), str(ftl_path))
    scraper = exp.Scraper(config)

    scraper.refresh()
