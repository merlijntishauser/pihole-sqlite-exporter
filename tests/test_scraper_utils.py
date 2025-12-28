import pytest

from pihole_sqlite_exporter import scraper


def test_env_truthy_reads_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_TRUTHY", "yes")
    assert scraper.env_truthy("TEST_TRUTHY") is True


def test_env_truthy_reads_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_FALSY", "0")
    assert scraper.env_truthy("TEST_FALSY") is False


def test_env_truthy_default_true() -> None:
    assert scraper.env_truthy("MISSING", "true") is True


def test_variance_empty() -> None:
    assert scraper.variance([]) == 0.0


def test_variance_constant() -> None:
    assert scraper.variance([1, 1, 1]) == 0.0


def test_variance_simple_series() -> None:
    assert scraper.variance([1, 2, 3]) == pytest.approx(2.0 / 3.0)


def test_get_tz_falls_back_on_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scraper, "EXPORTER_TZ", "Invalid/Timezone")
    assert scraper.get_tz() is not None
