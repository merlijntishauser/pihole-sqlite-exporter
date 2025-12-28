import logging
import sqlite3
from typing import TypeVar
from urllib.parse import quote

logger = logging.getLogger("pihole_sqlite_exporter")
T = TypeVar("T")


def sqlite_ro(db_path: str) -> sqlite3.Connection:
    if db_path.startswith("file:"):
        dsn = db_path
    else:
        dsn = f"file:{quote(db_path, safe='/')}?mode=ro"
    logger.debug("Opening SQLite DB read-only: %s", db_path)
    return sqlite3.connect(dsn, uri=True)


def fetch_scalar(cur: sqlite3.Cursor, sql: str, params=(), default: T | None = None) -> T | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else default
