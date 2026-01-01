import argparse
import logging
import os
from pathlib import Path

from . import http_server, metrics, scraper
from .settings import env_truthy

logger = logging.getLogger("pihole_sqlite_exporter")


def _env_truthy(name: str, default: str = "false") -> bool:
    return env_truthy(name, default)


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
    value = os.getenv("GIT_COMMIT") or os.getenv("GIT_SHA") or os.getenv("SOURCE_COMMIT") or ""
    value = value.strip()
    return value or "unknown"


def parse_args():
    parser = argparse.ArgumentParser(description="Pi-hole SQLite Prometheus exporter")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose (debug) logging")
    return parser.parse_args()


scrape_and_update = scraper.scrape_and_update
Handler = http_server.make_handler(metrics.METRICS.get_snapshot, logger)


def main():
    args = parse_args()
    verbose = bool(args.verbose) or _env_truthy("DEBUG", "false")
    configure_logging(verbose)
    version = _read_version()
    commit = _read_commit()
    if commit == "unknown":
        logger.info("Exporter version=%s", version)
    else:
        logger.info("Exporter version=%s commit=%s", version, commit)

    logger.info(
        (
            "Starting exporter (listen=%s:%s, tz=%s, ftl_db=%s, gravity_db=%s, top_n=%s, "
            "lifetime_dest_counters=%s, scrape_interval=%s)"
        ),
        scraper.SETTINGS.listen_addr,
        scraper.SETTINGS.listen_port,
        scraper.SETTINGS.exporter_tz,
        scraper.SETTINGS.ftl_db_path,
        scraper.SETTINGS.gravity_db_path,
        scraper.SETTINGS.top_n,
        scraper.SETTINGS.enable_lifetime_dest_counters,
        scraper.SETTINGS.scrape_interval,
    )

    try:
        scrape_and_update()
    except Exception:
        logger.exception("Initial scrape failed")

    scraper.start_background_scrape()

    handler = http_server.make_handler(metrics.METRICS.get_snapshot, logger)
    http_server.serve(scraper.SETTINGS.listen_addr, scraper.SETTINGS.listen_port, handler)


if __name__ == "__main__":
    main()
