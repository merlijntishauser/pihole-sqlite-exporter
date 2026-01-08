from pathlib import Path

import pytest
from fixtures import (
    add_queries as _add_queries,
)
from fixtures import (
    create_ftl_db,
    create_gravity_db,
)
from fixtures import (
    update_counters as _update_counters,
)

from pihole_sqlite_exporter import metrics, scraper


def _iter_metric_lines(text: str, name: str):
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        if not line.startswith(name):
            continue
        yield line


def _parse_labels(line: str) -> dict[str, str]:
    if "{" not in line:
        return {}
    label_part = line.split("{", 1)[1].split("}", 1)[0]
    label_items = {}
    for item in label_part.split(","):
        if not item:
            continue
        key, value = item.split("=", 1)
        label_items[key] = value.strip('"')
    return label_items


def _labels_match(line: str, labels: dict[str, str] | None) -> bool:
    if not labels:
        return True
    line_labels = _parse_labels(line)
    for key, value in labels.items():
        if line_labels.get(key) != value:
            return False
    return True


@pytest.fixture
def ftl_db(tmp_path: Path) -> Path:
    path = tmp_path / "pihole-FTL.db"
    create_ftl_db(path)
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
        create_ftl_db(
            path, counters=counters, queries=queries, clients=clients, domain_count=domain_count
        )
        return path

    return _factory


@pytest.fixture
def update_counters():
    def _update(path: Path, total: int, blocked: int) -> None:
        _update_counters(path, total, blocked)

    return _update


@pytest.fixture
def add_queries():
    def _add(
        path: Path,
        queries: list[tuple[int, int, int, int | None, str | None, float | None, str, str]],
    ) -> None:
        _add_queries(path, queries)

    return _add


@pytest.fixture
def gravity_db(tmp_path: Path) -> Path:
    path = tmp_path / "gravity.db"
    create_gravity_db(path)
    return path


@pytest.fixture
def exporter_config(monkeypatch: pytest.MonkeyPatch, ftl_db: Path, gravity_db: Path) -> None:
    monkeypatch.setattr(scraper.SETTINGS, "ftl_db_path", str(ftl_db))
    monkeypatch.setattr(scraper.SETTINGS, "gravity_db_path", str(gravity_db))
    monkeypatch.setattr(scraper.SETTINGS, "hostname_label", "test-host")
    monkeypatch.setattr(scraper.SETTINGS, "exporter_tz", "UTC")
    monkeypatch.setattr(scraper.SETTINGS, "top_n", 10)
    monkeypatch.setattr(scraper.SETTINGS, "enable_lifetime_dest_counters", False)
    monkeypatch.setattr(scraper.SETTINGS, "summary_only", False)
    metrics.METRICS.set_hostname_label("test-host")


@pytest.fixture
def metrics_text(exporter_config: None) -> str:
    scraper.scrape_and_update()
    snapshot = metrics.METRICS.get_snapshot()
    return snapshot.payload.decode("utf-8")


@pytest.fixture
def metric_value():
    def _metric_value(text: str, name: str, labels: dict[str, str] | None = None) -> float:
        for line in _iter_metric_lines(text, name):
            if not _labels_match(line, labels):
                continue
            return float(line.split()[-1])
        raise AssertionError(f"Metric {name} with labels {labels} not found")

    return _metric_value
