import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class RequestRateTracker:
    last_request_ts: float | None = None
    last_request_total: int | None = None
    last_request_rowid: int | None = None
    _cursor_col: str | None = None

    def reset(self) -> None:
        self.last_request_ts = None
        self.last_request_total = None
        self.last_request_rowid = None
        self._cursor_col = None

    def _detect_cursor(self, cur: sqlite3.Cursor) -> str | None:
        if self._cursor_col is not None:
            return self._cursor_col or None

        try:
            cur.execute("SELECT MAX(rowid) FROM queries;")
            cur.fetchone()
            self._cursor_col = "rowid"
            return "rowid"
        except sqlite3.OperationalError:
            pass

        cur.execute("PRAGMA table_info(queries);")
        cols = {row[1] for row in cur.fetchall()}
        if "id" in cols:
            self._cursor_col = "id"
            return "id"

        self._cursor_col = ""
        return None

    def update(
        self,
        *,
        now: float | None,
        db_path: str,
        host: str,
        rate_gauge,
        sqlite_ro: Callable[[str], sqlite3.Connection],
        logger,
    ) -> tuple[int | None, int | None]:
        if now is None:
            now = time.time()

        total = None
        blocked = None
        rowid = self.last_request_rowid
        cursor_col = None

        try:
            with sqlite_ro(db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT value FROM counters WHERE id = 0;")
                total = int(cur.fetchone()[0])
                cur.execute("SELECT value FROM counters WHERE id = 1;")
                blocked = int(cur.fetchone()[0])
                cursor_col = self._detect_cursor(cur)
                if cursor_col:
                    cur.execute(f"SELECT MAX({cursor_col}) FROM queries;")
                    rowid = cur.fetchone()[0]
        except Exception:
            logger.exception("Failed to refresh counters for request rate")

        if self.last_request_ts is not None:
            dt = max(1.0, now - self.last_request_ts)
            dq = 0
            if (
                cursor_col
                and self.last_request_rowid is not None
                and rowid is not None
                and rowid > self.last_request_rowid
            ):
                try:
                    with sqlite_ro(db_path) as conn:
                        cur = conn.cursor()
                        cur.execute(
                            f"SELECT COUNT(*) FROM queries WHERE {cursor_col} > ?;",
                            (self.last_request_rowid,),
                        )
                        dq = int(cur.fetchone()[0])
                except Exception:
                    logger.exception("Failed to compute request rate from queries table")
                    dq = 0
            elif self.last_request_total is not None and total is not None:
                dq = max(0, total - self.last_request_total)

            rate = dq / dt
            rate_gauge.labels(host).set(rate)
            logger.debug("Request rate queries_delta=%d time_delta=%.3f rate=%.6f", dq, dt, rate)
        else:
            rate_gauge.labels(host).set(0.0)
            logger.debug("Request rate initialized to 0.0")

        self.last_request_ts = now
        if total is not None:
            self.last_request_total = total
        if rowid is not None:
            self.last_request_rowid = rowid

        return total, blocked
