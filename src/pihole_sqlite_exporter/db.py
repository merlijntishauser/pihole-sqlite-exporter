import logging
import sqlite3
from urllib.parse import quote

logger = logging.getLogger("pihole_sqlite_exporter")


def sqlite_ro(db_path: str) -> sqlite3.Connection:
    if db_path.startswith("file:"):
        dsn = db_path
    else:
        dsn = f"file:{quote(db_path, safe='/')}?mode=ro"
    logger.debug("Opening SQLite DB read-only: %s", db_path)
    return sqlite3.connect(dsn, uri=True)
