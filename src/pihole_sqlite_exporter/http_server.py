import logging
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def make_handler(update_request_rate, registry, logger=None):
    if logger is None:
        logger = logging.getLogger("pihole_sqlite_exporter")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/metrics", "/"):
                self.send_response(404)
                self.end_headers()
                return

            try:
                logger.info("HTTP request: %s %s", self.command, self.path)
                start = time.time()
                update_request_rate(start)
                payload = generate_latest(registry)
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                elapsed = time.time() - start
                logger.info(
                    "HTTP 200 served metrics bytes=%d scrape_time=%.3fs",
                    len(payload),
                    elapsed,
                )
            except (BrokenPipeError, ConnectionResetError) as e:
                logger.debug("Client disconnected while serving request: %s", e)
            except Exception as e:
                logger.exception("Scrape failed while serving request")
                msg = f"scrape failed: {e}\n".encode()
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)

        def log_message(self, format, *args):
            return

    return Handler


def serve(listen_addr: str, listen_port: int, handler_cls) -> None:
    httpd = HTTPServer((listen_addr, listen_port), handler_cls)
    logging.getLogger("pihole_sqlite_exporter").info("HTTP server ready; waiting for scrapes")
    httpd.serve_forever()
