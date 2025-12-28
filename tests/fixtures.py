import sqlite3
import time
from pathlib import Path


def create_ftl_db(
    path: Path,
    now_ts: int | None = None,
    counters: tuple[int, int] = (5, 1),
    queries: list[tuple[int, int, int, int | None, str | None, float | None, str, str]]
    | None = None,
    clients: list[tuple[str, str]] | None = None,
    domain_count: int = 2,
) -> None:
    if now_ts is None:
        now_ts = int(time.time())

    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE counters (id INTEGER, value INTEGER);")
    cur.executemany(
        "INSERT INTO counters (id, value) VALUES (?, ?);",
        [(0, counters[0]), (1, counters[1])],
    )
    cur.execute("CREATE TABLE client_by_id (ip TEXT, name TEXT);")
    if clients is None:
        clients = [("10.0.0.1", "client-a"), ("10.0.0.2", "")]
    cur.executemany("INSERT INTO client_by_id (ip, name) VALUES (?, ?);", clients)
    cur.execute("CREATE TABLE domain_by_id (id INTEGER);")
    cur.executemany(
        "INSERT INTO domain_by_id (id) VALUES (?);", [(idx,) for idx in range(domain_count)]
    )

    cur.execute(
        """
        CREATE TABLE queries (
            timestamp INTEGER,
            status INTEGER,
            type INTEGER,
            reply_type INTEGER,
            forward TEXT,
            reply_time REAL,
            domain TEXT,
            client TEXT
        );
        """
    )
    if queries is None:
        queries = [
            (now_ts - 10, 2, 1, 3, "1.1.1.1", 0.1, "example.com", "10.0.0.1"),
            (now_ts - 20, 3, 2, 2, None, None, "cached.com", "10.0.0.2"),
            (now_ts - 30, 1, 1, 2, None, None, "ads.com", "10.0.0.1"),
        ]
    cur.executemany(
        """
        INSERT INTO queries (
            timestamp, status, type, reply_type, forward, reply_time, domain, client
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        queries,
    )
    conn.commit()
    conn.close()


def create_gravity_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE gravity (id INTEGER);")
    cur.executemany("INSERT INTO gravity (id) VALUES (?);", [(1,), (2,), (3,), (4,)])
    conn.commit()
    conn.close()


def update_counters(path: Path, total: int, blocked: int) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("UPDATE counters SET value = ? WHERE id = 0;", (total,))
    cur.execute("UPDATE counters SET value = ? WHERE id = 1;", (blocked,))
    conn.commit()
    conn.close()


def add_queries(
    path: Path,
    queries: list[tuple[int, int, int, int | None, str | None, float | None, str, str]],
) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO queries (
            timestamp, status, type, reply_type, forward, reply_time, domain, client
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        queries,
    )
    conn.commit()
    conn.close()
