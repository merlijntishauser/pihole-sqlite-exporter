import io
import time

import pytest

from pihole_sqlite_exporter import exporter as exp


class DummyHandler(exp.Handler):
    def __init__(self, path: str) -> None:
        self.path = path
        self.command = "GET"
        self.sent_status = None
        self.wfile = io.BytesIO()

    def send_response(self, code, message=None):
        self.sent_status = code

    def send_header(self, key, value):
        return None

    def end_headers(self):
        return None


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


def test_get_tz_falls_back_on_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exp, "EXPORTER_TZ", "Invalid/Timezone")
    assert exp._get_tz() is not None


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


def test_scrape_falls_back_when_gravity_missing(
    ftl_db_factory, tmp_path, monkeypatch: pytest.MonkeyPatch, metric_value
) -> None:
    ftl_path = ftl_db_factory(domain_count=2)
    gravity_path = tmp_path / "missing-gravity.db"
    monkeypatch.setattr(exp, "FTL_DB_PATH", str(ftl_path))
    monkeypatch.setattr(exp, "GRAVITY_DB_PATH", str(gravity_path))
    monkeypatch.setattr(exp, "HOSTNAME_LABEL", "test-host")
    monkeypatch.setattr(exp, "EXPORTER_TZ", "UTC")
    monkeypatch.setattr(exp, "ENABLE_LIFETIME_DEST_COUNTERS", False)
    monkeypatch.setattr(exp, "_last_request_ts", None)
    monkeypatch.setattr(exp, "_last_request_total", None)

    exp.scrape_and_update()
    metrics = exp.generate_latest(exp.REGISTRY).decode("utf-8")
    assert metric_value(metrics, "pihole_domains_being_blocked", {"hostname": "test-host"}) == 2.0


def test_request_rate_after_second_scrape(
    ftl_db_factory, monkeypatch: pytest.MonkeyPatch, update_counters, metric_value
) -> None:
    ftl_path = ftl_db_factory(counters=(5, 1))
    monkeypatch.setattr(exp, "FTL_DB_PATH", str(ftl_path))
    monkeypatch.setattr(exp, "GRAVITY_DB_PATH", str(ftl_path))
    monkeypatch.setattr(exp, "HOSTNAME_LABEL", "test-host")
    monkeypatch.setattr(exp, "EXPORTER_TZ", "UTC")
    monkeypatch.setattr(exp, "ENABLE_LIFETIME_DEST_COUNTERS", False)
    monkeypatch.setattr(exp, "_last_request_ts", None)
    monkeypatch.setattr(exp, "_last_request_total", None)

    base_time = time.time()
    exp.scrape_and_update()
    exp.update_request_rate_for_request(now=base_time)

    update_counters(ftl_path, total=7, blocked=2)
    exp.scrape_and_update()
    exp.update_request_rate_for_request(now=base_time + 10)

    metrics = exp.generate_latest(exp.REGISTRY).decode("utf-8")
    assert metric_value(metrics, "pihole_request_rate", {"hostname": "test-host"}) == pytest.approx(
        0.2
    )


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
    monkeypatch.setattr(exp, "FTL_DB_PATH", str(ftl_path))
    monkeypatch.setattr(exp, "GRAVITY_DB_PATH", str(ftl_path))
    monkeypatch.setattr(exp, "HOSTNAME_LABEL", "test-host")
    monkeypatch.setattr(exp, "EXPORTER_TZ", "UTC")
    monkeypatch.setattr(exp, "ENABLE_LIFETIME_DEST_COUNTERS", True)
    monkeypatch.setattr(exp, "_last_request_ts", None)
    monkeypatch.setattr(exp, "_last_request_total", None)

    exp.scrape_and_update()
    metrics = exp.generate_latest(exp.REGISTRY).decode("utf-8")
    assert (
        metric_value(
            metrics,
            "pihole_forward_destinations_total",
            {"hostname": "test-host", "destination": "1.1.1.1", "destination_name": "1.1.1.1"},
        )
        == 2.0
    )


def test_handler_returns_404_for_unknown_path() -> None:
    handler = DummyHandler("/nope")
    handler.do_GET()
    assert handler.sent_status == 404


def test_handler_returns_500_on_scrape_error(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = DummyHandler("/metrics")

    def _raise(registry):
        raise RuntimeError("boom")

    monkeypatch.setattr(exp, "generate_latest", _raise)
    handler.do_GET()
    assert handler.sent_status == 500
