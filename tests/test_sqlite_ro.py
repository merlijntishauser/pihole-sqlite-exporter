import sqlite3

from pihole_sqlite_exporter import utils


def test_sqlite_ro_handles_spaces(tmp_path) -> None:
    db_path = tmp_path / "pihole db.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE test (id INTEGER);")
    cur.execute("INSERT INTO test (id) VALUES (1);")
    conn.commit()
    conn.close()

    ro_conn = utils.sqlite_ro(str(db_path))
    ro_cur = ro_conn.cursor()
    ro_cur.execute("SELECT COUNT(*) FROM test;")
    assert ro_cur.fetchone()[0] == 1
    ro_conn.close()
