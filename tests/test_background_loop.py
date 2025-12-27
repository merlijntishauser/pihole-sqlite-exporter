import threading

from pihole_sqlite_exporter import exporter as exp


def test_scrape_loop_runs_and_handles_errors(config: exp.Config) -> None:
    scraper = exp.Scraper(config)
    stop_event = threading.Event()
    calls = {"count": 0}

    def _refresh():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        stop_event.set()

    scraper.refresh = _refresh  # type: ignore[assignment]

    exp._scrape_loop(scraper, stop_event=stop_event, sleep_fn=lambda _: None, time_fn=lambda: 0.0)
    assert calls["count"] == 2
