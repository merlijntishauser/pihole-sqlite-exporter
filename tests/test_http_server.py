import io

import pytest

from pihole_sqlite_exporter import http_server, metrics, scraper

HandlerCls = http_server.make_handler(
    scraper.update_request_rate_for_request,
    metrics.REGISTRY,
)


class DummyHandler(HandlerCls):
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


def test_handler_returns_404_for_unknown_path() -> None:
    handler = DummyHandler("/nope")
    handler.do_GET()
    assert handler.sent_status == 404


def test_handler_returns_500_on_scrape_error(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = DummyHandler("/metrics")

    def _raise(registry):
        raise RuntimeError("boom")

    monkeypatch.setattr(http_server, "generate_latest", _raise)
    handler.do_GET()
    assert handler.sent_status == 500
