import logging
import sqlite3
from typing import TypeVar, overload
from urllib.parse import quote

logger = logging.getLogger("pihole_sqlite_exporter")
T = TypeVar("T")


def sqlite_ro(db_path: str) -> sqlite3.Connection:
    dsn = f"file:{quote(db_path, safe='/')}?mode=ro"
    if db_path.startswith("file:"):
        dsn = db_path
    logger.debug("Opening SQLite DB read-only: %s", db_path)
    return sqlite3.connect(dsn, uri=True)


@overload
def fetch_scalar(cur: sqlite3.Cursor, sql: str, params: tuple = ()) -> None: ...


@overload
def fetch_scalar(
    cur: sqlite3.Cursor,
    sql: str,
    params: tuple = (),
    *,
    default: None = None,
) -> None: ...


@overload
def fetch_scalar(cur: sqlite3.Cursor, sql: str, params: tuple = (), *, default: T) -> T: ...


def fetch_scalar(
    cur: sqlite3.Cursor, sql: str, params: tuple = (), default: T | None = None
) -> T | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    if row:
        return row[0]
    return default
