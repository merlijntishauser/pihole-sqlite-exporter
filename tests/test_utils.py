import pytest

from pihole_sqlite_exporter import utils


def test_env_truthy_reads_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_TRUTHY", "yes")
    assert utils.env_truthy("TEST_TRUTHY") is True


def test_env_truthy_reads_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_FALSY", "0")
    assert utils.env_truthy("TEST_FALSY") is False


def test_env_truthy_default_true() -> None:
    assert utils.env_truthy("MISSING", "true") is True


def test_variance_empty() -> None:
    assert utils.variance([]) == 0.0


def test_variance_constant() -> None:
    assert utils.variance([1, 1, 1]) == 0.0


def test_variance_simple_series() -> None:
    assert utils.variance([1, 2, 3]) == pytest.approx(2.0 / 3.0)


def test_get_tz_falls_back_on_invalid() -> None:
    assert utils.get_tz("Invalid/Timezone") is not None
