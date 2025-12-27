import logging
import sqlite3
import time
from datetime import datetime, tzinfo
from urllib.parse import quote
from zoneinfo import ZoneInfo

logger = logging.getLogger("pihole_sqlite_exporter")


def env_truthy(name: str, default: str = "false") -> bool:
    v = __import__("os").getenv(name, default)
    return str(v).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def sqlite_ro(db_path: str) -> sqlite3.Connection:
    if db_path.startswith("file:"):
        dsn = db_path
    else:
        dsn = f"file:{quote(db_path, safe='/')}?mode=ro"
    logger.debug("Opening SQLite DB read-only: %s", db_path)
    return sqlite3.connect(dsn, uri=True)


def get_tz(exporter_tz: str) -> ZoneInfo | tzinfo:
    try:
        return ZoneInfo(exporter_tz)
    except Exception as e:
        logger.warning(
            "Invalid EXPORTER_TZ=%r; falling back to local tz. Reason: %s", exporter_tz, e
        )
        return datetime.now().astimezone().tzinfo


def start_of_day_ts(tz: ZoneInfo) -> int:
    now = datetime.now(tz=tz)
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(sod.timestamp())


def now_ts() -> int:
    return int(time.time())


def variance(values: list[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    return sum((x - mean) ** 2 for x in values) / n


__all__ = [
    "env_truthy",
    "sqlite_ro",
    "get_tz",
    "start_of_day_ts",
    "now_ts",
    "variance",
]
