from pihole_sqlite_exporter import db


class TestSqliteRo:
    def test_sqlite_ro_quotes_path(self, monkeypatch) -> None:
        captured = {}

        def _fake_connect(dsn, uri=True):
            captured["dsn"] = dsn
            captured["uri"] = uri
            return object()

        monkeypatch.setattr(db.sqlite3, "connect", _fake_connect)
        db.sqlite_ro("/tmp/my db.sqlite")

        assert captured["dsn"] == "file:/tmp/my%20db.sqlite?mode=ro"
        assert captured["uri"] is True

    def test_sqlite_ro_keeps_file_dsn(self, monkeypatch) -> None:
        captured = {}
        dsn = "file:/tmp/test.db?mode=ro"

        def _fake_connect(value, uri=True):
            captured["dsn"] = value
            captured["uri"] = uri
            return object()

        monkeypatch.setattr(db.sqlite3, "connect", _fake_connect)
        db.sqlite_ro(dsn)

        assert captured["dsn"] == dsn
        assert captured["uri"] is True
