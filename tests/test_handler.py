import io

from pihole_sqlite_exporter import exporter as exp


def _make_dummy_handler(handler_cls, path: str):
    class DummyHandler(handler_cls):
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

    return DummyHandler(path)


def test_handler_returns_404_for_unknown_path(config: exp.Config) -> None:
    scraper = exp.Scraper(config)
    handler_cls = exp.make_handler(scraper)
    handler = _make_dummy_handler(handler_cls, "/nope")
    handler.do_GET()
    assert handler.sent_status == 404


def test_handler_returns_500_on_scrape_error(config: exp.Config) -> None:
    scraper = exp.Scraper(config)

    def _raise():
        raise RuntimeError("boom")

    scraper.refresh = _raise  # type: ignore[assignment]
    handler_cls = exp.make_handler(scraper)
    handler = _make_dummy_handler(handler_cls, "/metrics")
    handler.do_GET()
    assert handler.sent_status == 500


def test_handler_uses_cached_payload(config: exp.Config) -> None:
    scraper = exp.Scraper(config)
    scraper._cache.set(b"cached", 123.0)

    def _raise():
        raise RuntimeError("boom")

    scraper.refresh = _raise  # type: ignore[assignment]
    handler_cls = exp.make_handler(scraper)
    handler = _make_dummy_handler(handler_cls, "/metrics")
    handler.do_GET()
    assert handler.sent_status == 200
