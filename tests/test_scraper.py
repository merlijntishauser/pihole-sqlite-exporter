import threading
import time

import pytest

from pihole_sqlite_exporter import constants, metrics, scraper


def test_variance_empty() -> None:
    assert scraper.variance([]) == 0.0


def test_variance_constant() -> None:
    assert scraper.variance([1, 1, 1]) == 0.0


def test_variance_simple_series() -> None:
    assert scraper.variance([1, 2, 3]) == pytest.approx(2.0 / 3.0)


def test_get_tz_falls_back_on_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scraper.SETTINGS, "exporter_tz", "Invalid/Timezone")
    assert scraper.get_tz() is not None


def test_blocked_status_list_is_sorted() -> None:
    expected = ",".join(str(x) for x in sorted(constants.BLOCKED_STATUSES))
    assert scraper._blocked_status_list() == expected


def test_scrape_skipped_when_lock_held(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(scraper.SETTINGS, "hostname_label", "test-host")
    metrics.METRICS.set_hostname_label("test-host")
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )

    context.scrape_lock.acquire()
    try:
        with caplog.at_level("INFO"):
            scraper.scrape_and_update(context=context)
        assert "Scrape skipped" in caplog.text
    finally:
        context.scrape_lock.release()


def test_lifetime_destinations_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    host = "test-host"
    monkeypatch.setattr(scraper.SETTINGS, "hostname_label", host)
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )
    monkeypatch.setattr(scraper.SETTINGS, "enable_lifetime_dest_counters", True)
    monkeypatch.setattr(scraper.SETTINGS, "lifetime_dest_cache_seconds", 60)
    monkeypatch.setattr(scraper.SETTINGS, "lifetime_dest_scan_interval", 1)
    monkeypatch.setattr(scraper.SETTINGS, "summary_only", False)
    monkeypatch.setattr(scraper.time, "time", lambda: 1000.0)
    context.lifetime_dest_scan_count = 1
    cache_counter = metrics.METRICS.pihole_exporter_cache_hits_total.labels(
        host, "lifetime_destinations"
    )
    before_hits = cache_counter._value.get()
    cached = {"1.1.1.1": 2, "cache": 1, "blocklist": 0}
    called = {}

    class DummyCursor:
        def execute(self, *args, **kwargs):
            raise AssertionError("execute should not be called on cache hit")

    monkeypatch.setattr(
        metrics.METRICS,
        "set_forward_destinations_lifetime",
        lambda value: called.setdefault("value", value),
    )

    try:
        context.lifetime_dest_cache = dict(cached)
        context.lifetime_dest_cache_ts = 999.0
        scraper._load_lifetime_destinations(context, DummyCursor(), "1,2", host)
    finally:
        context.lifetime_dest_cache = {}
        context.lifetime_dest_cache_ts = 0.0

    assert called["value"] == cached
    assert cache_counter._value.get() == before_hits + 1


def test_lifetime_destinations_disabled_resets_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scraper.SETTINGS, "enable_lifetime_dest_counters", False)
    monkeypatch.setattr(scraper.SETTINGS, "summary_only", False)
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )
    called = {}

    monkeypatch.setattr(
        metrics.METRICS,
        "set_forward_destinations_lifetime",
        lambda value: called.setdefault("value", value),
    )

    try:
        context.lifetime_dest_cache = {"1.1.1.1": 2}
        context.lifetime_dest_cache_ts = 123.0
        scraper._load_lifetime_destinations(context, None, "1,2", "test-host")
    finally:
        context.lifetime_dest_cache = {}
        context.lifetime_dest_cache_ts = 0.0

    assert called["value"] == {}


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        ("pihole_dns_queries_today", 3.0),
        ("pihole_ads_blocked_today", 1.0),
        ("pihole_ads_percentage_today", pytest.approx(100.0 / 3.0)),
        ("pihole_queries_forwarded", 1.0),
        ("pihole_queries_cached", 1.0),
        ("pihole_domains_being_blocked", 4.0),
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
    monkeypatch.setattr(scraper.SETTINGS, "ftl_db_path", str(ftl_path))
    monkeypatch.setattr(scraper.SETTINGS, "gravity_db_path", str(gravity_path))
    monkeypatch.setattr(scraper.SETTINGS, "hostname_label", "test-host")
    monkeypatch.setattr(scraper.SETTINGS, "exporter_tz", "UTC")
    monkeypatch.setattr(scraper.SETTINGS, "enable_lifetime_dest_counters", False)
    metrics.METRICS.set_hostname_label("test-host")
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )

    scraper.scrape_and_update(context=context)
    metrics_text = context.metrics.get_snapshot().payload.decode("utf-8")
    assert (
        metric_value(metrics_text, "pihole_domains_being_blocked", {"hostname": "test-host"}) == 2.0
    )


def test_lifetime_destinations_metric(
    ftl_db_factory, monkeypatch: pytest.MonkeyPatch, metric_value
) -> None:
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )
    now_ts = int(time.time())
    queries = [
        (now_ts - 10, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
        (now_ts - 20, 2, 1, 3, "1.1.1.1", 0.2, "example.com", "10.0.0.1"),
        (now_ts - 30, 3, 2, 2, None, None, "cached.com", "10.0.0.2"),
        (now_ts - 40, 1, 1, 2, None, None, "ads.com", "10.0.0.1"),
    ]
    ftl_path = ftl_db_factory(queries=queries)
    monkeypatch.setattr(scraper.SETTINGS, "ftl_db_path", str(ftl_path))
    monkeypatch.setattr(scraper.SETTINGS, "gravity_db_path", str(ftl_path))
    monkeypatch.setattr(scraper.SETTINGS, "hostname_label", "test-host")
    monkeypatch.setattr(scraper.SETTINGS, "exporter_tz", "UTC")
    monkeypatch.setattr(scraper.SETTINGS, "enable_lifetime_dest_counters", True)
    monkeypatch.setattr(scraper.SETTINGS, "lifetime_dest_scan_interval", 1)
    monkeypatch.setattr(scraper.SETTINGS, "lifetime_dest_max_entries", 10)
    monkeypatch.setattr(scraper.SETTINGS, "summary_only", False)
    metrics.METRICS.set_hostname_label("test-host")

    scraper.scrape_and_update(context=context)
    metrics_text = context.metrics.get_snapshot().payload.decode("utf-8")
    assert (
        metric_value(
            metrics_text,
            "pihole_forward_destinations_total",
            {"hostname": "test-host", "destination": "1.1.1.1", "destination_name": "1.1.1.1"},
        )
        == 2.0
    )
    assert (
        metric_value(
            metrics_text,
            "pihole_exporter_query_duration_seconds",
            {"hostname": "test-host", "query": "counters"},
        )
        >= 0.0
    )


def test_lifetime_destinations_scan_interval_skips_when_cache_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scraper.SETTINGS, "enable_lifetime_dest_counters", True)
    monkeypatch.setattr(scraper.SETTINGS, "lifetime_dest_cache_seconds", 0)
    monkeypatch.setattr(scraper.SETTINGS, "lifetime_dest_scan_interval", 2)
    monkeypatch.setattr(scraper.SETTINGS, "summary_only", False)
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )
    context.lifetime_dest_scan_count = 1
    cached = {"1.1.1.1": 2, "cache": 1, "blocklist": 0}
    called = {}

    class DummyCursor:
        def execute(self, *args, **kwargs):
            raise AssertionError("execute should not be called when scan is skipped")

    monkeypatch.setattr(
        metrics.METRICS,
        "set_forward_destinations_lifetime",
        lambda value: called.setdefault("value", value),
    )

    try:
        context.lifetime_dest_cache = dict(cached)
        context.lifetime_dest_cache_ts = 0.0
        scraper._load_lifetime_destinations(context, DummyCursor(), "1,2", "test-host")
    finally:
        context.lifetime_dest_cache = {}
        context.lifetime_dest_cache_ts = 0.0

    assert called["value"] == cached


def test_lifetime_destinations_apply_max_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scraper.SETTINGS, "enable_lifetime_dest_counters", True)
    monkeypatch.setattr(scraper.SETTINGS, "lifetime_dest_cache_seconds", 0)
    monkeypatch.setattr(scraper.SETTINGS, "lifetime_dest_scan_interval", 1)
    monkeypatch.setattr(scraper.SETTINGS, "lifetime_dest_max_entries", 1)
    monkeypatch.setattr(scraper.SETTINGS, "summary_only", False)
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )
    context.lifetime_dest_scan_count = 1
    called = {}

    class DummyCursor:
        def execute(self, *args, **kwargs):
            return None

        def fetchall(self):
            return [("1.1.1.1", 5), ("2.2.2.2", 2)]

    def _fake_fetch_scalar(*args, **kwargs):
        return 1

    monkeypatch.setattr(scraper, "fetch_scalar", _fake_fetch_scalar)
    monkeypatch.setattr(
        metrics.METRICS,
        "set_forward_destinations_lifetime",
        lambda value: called.setdefault("value", value),
    )

    try:
        scraper._load_lifetime_destinations(context, DummyCursor(), "1,2", "test-host")
    finally:
        context.lifetime_dest_cache = {}
        context.lifetime_dest_cache_ts = 0.0

    assert called["value"]["1.1.1.1"] == 5
    assert "2.2.2.2" not in called["value"]
    assert called["value"]["cache"] == 1
    assert called["value"]["blocklist"] == 1


def test_summary_only_skips_high_cardinality(
    ftl_db_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )
    ftl_path = ftl_db_factory()
    monkeypatch.setattr(scraper.SETTINGS, "ftl_db_path", str(ftl_path))
    monkeypatch.setattr(scraper.SETTINGS, "gravity_db_path", str(ftl_path))
    monkeypatch.setattr(scraper.SETTINGS, "hostname_label", "test-host")
    monkeypatch.setattr(scraper.SETTINGS, "exporter_tz", "UTC")
    monkeypatch.setattr(scraper.SETTINGS, "enable_lifetime_dest_counters", True)
    monkeypatch.setattr(scraper.SETTINGS, "summary_only", True)
    metrics.METRICS.set_hostname_label("test-host")

    scraper.scrape_and_update(context=context)
    metrics_text = context.metrics.get_snapshot().payload.decode("utf-8")
    assert "pihole_top_ads{" not in metrics_text
    assert "pihole_top_queries{" not in metrics_text
    assert "pihole_top_sources{" not in metrics_text
    assert "pihole_forward_destinations{" not in metrics_text
    assert "pihole_forward_destinations_total{" not in metrics_text


def test_load_domains_blocked_warns_on_double_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )

    class FakeGauge:
        def __init__(self) -> None:
            self.calls = []

        def labels(self, *args):
            self._labels = args
            return self

        def set(self, value: float) -> None:
            self.calls.append((self._labels, value))

    def _boom(_path):
        raise RuntimeError("db error")

    fake = FakeGauge()
    monkeypatch.setattr(metrics.METRICS, "pihole_domains_being_blocked", fake)
    monkeypatch.setattr(scraper, "sqlite_ro", _boom)
    context.gravity_db_fallback_logged = False
    context.gravity_ftl_fallback_logged = False

    with caplog.at_level("INFO"):
        scraper._load_domains_blocked(context, "test-host")

    assert "Gravity DB unavailable" in caplog.text
    assert "Fallback domain count failed" in caplog.text
    assert fake.calls == [(("test-host",), 0.0)]


def test_scrape_and_update_logs_failure_and_snapshot_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )

    class DummyConn:
        def cursor(self):
            return object()

    class DummyCtx:
        def __enter__(self):
            return DummyConn()

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(scraper, "sqlite_ro", lambda _path: DummyCtx())
    monkeypatch.setattr(scraper, "_load_counters", _boom)
    monkeypatch.setattr(metrics.METRICS, "update_snapshot", _boom)
    monkeypatch.setattr(scraper.SETTINGS, "hostname_label", "test-host")
    metrics.METRICS.set_hostname_label("test-host")
    monkeypatch.setattr(scraper.time, "time", lambda: 1234.0)
    monkeypatch.setattr(scraper.time, "perf_counter", lambda: 1.0)

    with pytest.raises(RuntimeError), caplog.at_level("ERROR"):
        scraper.scrape_and_update(context=context)

    assert "Scrape failed" in caplog.text
    assert "Failed to update metrics snapshot cache" in caplog.text
    last_success, last_scrape_ts, _last_success_ts = metrics.METRICS.get_scrape_status()
    assert last_success == 0
    assert last_scrape_ts == 1234.0


def test_scrape_loop_sleeps_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    stop_event = threading.Event()
    calls = {"scrape": 0, "sleep": []}
    host = "test-host"
    monkeypatch.setattr(scraper.SETTINGS, "hostname_label", host)
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )

    def _scrape(*_args, **_kwargs):
        calls["scrape"] += 1
        stop_event.set()

    def _time_fn():
        return times.pop(0)

    def _sleep_fn(duration: float) -> None:
        calls["sleep"].append(duration)

    monkeypatch.setattr(scraper, "scrape_and_update", _scrape)
    monkeypatch.setattr(scraper.SETTINGS, "scrape_interval", 5)
    times = [100.0, 101.0]

    scraper._scrape_loop(
        context=context,
        stop_event=stop_event,
        sleep_fn=_sleep_fn,
        time_fn=_time_fn,
    )

    assert calls["scrape"] == 1
    assert calls["sleep"] == [4.0]
    lag = metrics.METRICS.pihole_exporter_scrape_loop_lag_seconds.labels(host)._value.get()
    assert lag == 0.0


def test_scrape_loop_logs_warning_on_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    stop_event = threading.Event()
    times = [100.0, 101.0]
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )

    def _scrape():
        raise RuntimeError("boom")

    def _time_fn():
        return times.pop(0)

    def _sleep_fn(duration: float) -> None:
        stop_event.set()

    monkeypatch.setattr(scraper, "scrape_and_update", _scrape)
    monkeypatch.setattr(scraper.SETTINGS, "scrape_interval", 5)

    with caplog.at_level("WARNING"):
        scraper._scrape_loop(
            context=context,
            stop_event=stop_event,
            sleep_fn=_sleep_fn,
            time_fn=_time_fn,
        )

    assert "Background scrape failed" in caplog.text


def test_start_background_scrape_starts_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    created = {}
    context = scraper.new_context(
        settings=scraper.SETTINGS,
        metrics_obj=metrics.METRICS,
        logger_obj=scraper.logger,
    )

    class FakeThread:
        def __init__(self, *, target, kwargs, daemon) -> None:
            created["target"] = target
            created["kwargs"] = kwargs
            created["daemon"] = daemon
            self.started = False

        def start(self) -> None:
            self.started = True

    monkeypatch.setattr(scraper.threading, "Thread", FakeThread)

    thread = scraper.start_background_scrape(initial_delay=2.5, context=context)

    assert created["target"] == scraper._scrape_loop
    assert created["kwargs"] == {"initial_delay": 2.5, "context": context}
    assert created["daemon"] is True
    assert thread.started is True
