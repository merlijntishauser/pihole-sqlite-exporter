import io

import pytest

from pihole_sqlite_exporter import http_server, metrics

HandlerCls = http_server.make_handler(lambda *_: None, metrics.METRICS.registry)


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


class TestHandler:
    def test_handler_returns_200_for_metrics(self, monkeypatch: pytest.MonkeyPatch) -> None:
        handler = DummyHandler("/metrics")

        monkeypatch.setattr(http_server, "generate_latest", lambda registry: b"ok")
        handler.do_GET()
        assert handler.sent_status == 200
        assert handler.wfile.getvalue() == b"ok"

    def test_handler_returns_404_for_unknown_path(self) -> None:
        handler = DummyHandler("/nope")
        handler.do_GET()
        assert handler.sent_status == 404

    def test_handler_returns_500_on_scrape_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        handler = DummyHandler("/metrics")

        def _raise(registry):
            raise RuntimeError("boom")

        monkeypatch.setattr(http_server, "generate_latest", _raise)
        handler.do_GET()
        assert handler.sent_status == 500

    def test_handler_returns_500_on_update_failure(self) -> None:
        HandlerWithError = http_server.make_handler(
            lambda *_: (_ for _ in ()).throw(RuntimeError("update failed")),
            metrics.METRICS.registry,
        )

        class Handler(HandlerWithError):
            def __init__(self) -> None:
                self.path = "/metrics"
                self.command = "GET"
                self.sent_status = None
                self.wfile = io.BytesIO()

            def send_response(self, code, message=None):
                self.sent_status = code

            def send_header(self, key, value):
                return None

            def end_headers(self):
                return None

        handler = Handler()
        handler.do_GET()
        assert handler.sent_status == 500

    def test_handler_handles_broken_pipe(self) -> None:
        handler = DummyHandler("/metrics")

        class BrokenWriter(io.BytesIO):
            def write(self, data):
                raise BrokenPipeError("boom")

        handler.wfile = BrokenWriter()
        handler.do_GET()
        assert handler.sent_status == 200
