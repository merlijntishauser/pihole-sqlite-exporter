import pytest

from pihole_sqlite_exporter import exporter as exp


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
