import logging
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from prometheus_client import CONTENT_TYPE_LATEST


def _handle_unknown_path(handler) -> bool:
    if handler.path in ("/metrics", "/", "/healthz", "/readyz"):
        return False
    handler.send_response(404)
    handler.end_headers()
    return True


def _handle_health_request(handler, get_health, get_ready, logger) -> None:
    client_ip, client_port = handler.client_address
    user_agent = handler.headers.get("User-Agent", "-")
    logger.debug(
        "Health request from %s:%s user_agent=%s path=%s",
        client_ip,
        client_port,
        user_agent,
        handler.path,
    )
    ok, msg = get_ready()
    if handler.path == "/healthz":
        ok, msg = get_health()
    status = 503
    if ok:
        status = 200
    payload = msg.encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _handle_metrics_request(handler, get_snapshot, logger) -> None:
    try:
        client_ip, client_port = handler.client_address
        user_agent = handler.headers.get("User-Agent", "-")
        logger.debug("Metrics request from %s:%s user_agent=%s", client_ip, client_port, user_agent)
        logger.debug("HTTP request: %s %s", handler.command, handler.path)
        start = time.time()
        snapshot = get_snapshot()
        payload = snapshot.payload
        if not payload:
            msg = b"metrics snapshot unavailable\n"
            handler.send_response(503)
            handler.send_header("Content-Type", "text/plain; charset=utf-8")
            handler.send_header("Content-Length", str(len(msg)))
            handler.end_headers()
            handler.wfile.write(msg)
            return
        handler.send_response(200)
        handler.send_header("Content-Type", CONTENT_TYPE_LATEST)
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)
        elapsed = time.time() - start
        logger.debug(
            "HTTP 200 served metrics bytes=%d scrape_time=%.3fs",
            len(payload),
            elapsed,
        )
    except (BrokenPipeError, ConnectionResetError) as e:
        logger.debug("Client disconnected while serving request: %s", e)
    except Exception as e:
        logger.exception("Scrape failed while serving request")
        msg = f"scrape failed: {e}\n".encode()
        handler.send_response(500)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(msg)))
        handler.end_headers()
        handler.wfile.write(msg)


def _handle_request(handler, get_snapshot, get_health, get_ready, logger) -> None:
    if _handle_unknown_path(handler):
        return
    if handler.path in ("/healthz", "/readyz"):
        _handle_health_request(handler, get_health, get_ready, logger)
        return
    _handle_metrics_request(handler, get_snapshot, logger)


def make_handler(get_snapshot, get_health, get_ready, logger=None):
    if logger is None:
        logger = logging.getLogger("pihole_sqlite_exporter")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            _handle_request(self, get_snapshot, get_health, get_ready, logger)

        def log_message(self, format, *args):
            return

    return Handler


def serve(listen_addr: str, listen_port: int, handler_cls) -> None:
    httpd = HTTPServer((listen_addr, listen_port), handler_cls)
    logging.getLogger("pihole_sqlite_exporter").info("HTTP server ready; waiting for scrapes")
    httpd.serve_forever()
