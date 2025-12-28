import argparse
import logging
import os
from pathlib import Path

from prometheus_client import generate_latest as _generate_latest

from . import http_server, metrics, scraper

logger = logging.getLogger("pihole_sqlite_exporter")


def _env_truthy(name: str, default: str = "false") -> bool:
    return scraper.env_truthy(name, default)


def _get_tz():
    return scraper.get_tz()


def variance(values):
    return scraper.variance(values)


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _read_version() -> str:
    version_path = Path(__file__).resolve().parents[2] / "VERSION"
    if version_path.is_file():
        return version_path.read_text().strip()
    try:
        from . import __version__  # type: ignore

        return str(__version__)
    except Exception:
        return "unknown"


def _read_commit() -> str:
    return (
        os.getenv("GIT_COMMIT") or os.getenv("GIT_SHA") or os.getenv("SOURCE_COMMIT") or "unknown"
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Pi-hole SQLite Prometheus exporter")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose (debug) logging")
    return parser.parse_args()


scrape_and_update = scraper.scrape_and_update
update_request_rate_for_request = scraper.update_request_rate_for_request

REGISTRY = metrics.REGISTRY
Handler = http_server.make_handler(update_request_rate_for_request, REGISTRY, logger)
generate_latest = _generate_latest


def main():
    args = parse_args()
    verbose = bool(args.verbose) or _env_truthy("DEBUG", "false")
    configure_logging(verbose)
    logger.info("Exporter version=%s commit=%s", _read_version(), _read_commit())

    logger.info(
        (
            "Starting exporter (listen=%s:%s, tz=%s, ftl_db=%s, gravity_db=%s, top_n=%s, "
            "lifetime_dest_counters=%s, scrape_interval=%s)"
        ),
        scraper.LISTEN_ADDR,
        scraper.LISTEN_PORT,
        scraper.EXPORTER_TZ,
        scraper.FTL_DB_PATH,
        scraper.GRAVITY_DB_PATH,
        scraper.TOP_N,
        scraper.ENABLE_LIFETIME_DEST_COUNTERS,
        scraper.SCRAPE_INTERVAL,
    )

    try:
        scrape_and_update()
    except Exception:
        logger.exception("Initial scrape failed")

    scraper.start_background_scrape()

    handler = http_server.make_handler(update_request_rate_for_request, REGISTRY, logger)
    http_server.serve(scraper.LISTEN_ADDR, scraper.LISTEN_PORT, handler)


if __name__ == "__main__":
    main()
