import io

from pihole_sqlite_exporter import http_server
from pihole_sqlite_exporter.metrics import MetricsSnapshot

HandlerCls = http_server.make_handler(lambda: MetricsSnapshot(payload=b"ok", timestamp=1.0))


class DummyHandler(HandlerCls):
    def __init__(self, path: str) -> None:
        self.path = path
        self.command = "GET"
        self.sent_status = None
        self.client_address = ("127.0.0.1", 12345)
        self.headers = {"User-Agent": "pytest"}
        self.wfile = io.BytesIO()

    def send_response(self, code, message=None):
        self.sent_status = code

    def send_header(self, key, value):
        return None

    def end_headers(self):
        return None


class TestHandler:
    def test_handler_returns_200_for_metrics(self) -> None:
        handler = DummyHandler("/metrics")
        handler.do_GET()
        assert handler.sent_status == 200
        assert handler.wfile.getvalue() == b"ok"

    def test_handler_returns_404_for_unknown_path(self) -> None:
        handler = DummyHandler("/nope")
        handler.do_GET()
        assert handler.sent_status == 404

    def test_handler_returns_503_on_empty_snapshot(self) -> None:
        HandlerWithEmpty = http_server.make_handler(
            lambda: MetricsSnapshot(payload=b"", timestamp=0.0)
        )

        class Handler(HandlerWithEmpty):
            def __init__(self) -> None:
                self.path = "/metrics"
                self.command = "GET"
                self.sent_status = None
                self.client_address = ("127.0.0.1", 12345)
                self.headers = {"User-Agent": "pytest"}
                self.wfile = io.BytesIO()

            def send_response(self, code, message=None):
                self.sent_status = code

            def send_header(self, key, value):
                return None

            def end_headers(self):
                return None

        handler = Handler()
        handler.do_GET()
        assert handler.sent_status == 503

    def test_handler_returns_500_on_snapshot_failure(self) -> None:
        HandlerWithError = http_server.make_handler(
            lambda: (_ for _ in ()).throw(RuntimeError("snapshot failed")),
        )

        class Handler(HandlerWithError):
            def __init__(self) -> None:
                self.path = "/metrics"
                self.command = "GET"
                self.sent_status = None
                self.client_address = ("127.0.0.1", 12345)
                self.headers = {"User-Agent": "pytest"}
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
