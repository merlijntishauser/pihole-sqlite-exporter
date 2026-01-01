from types import SimpleNamespace

import pytest

import pihole_sqlite_exporter
from pihole_sqlite_exporter import exporter


class TestExporterMain:
    def test_main_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = {}

        monkeypatch.setattr(exporter, "parse_args", lambda: SimpleNamespace(verbose=False))
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setattr(
            exporter, "configure_logging", lambda verbose: called.setdefault("verbose", verbose)
        )
        monkeypatch.setattr(
            exporter, "scrape_and_update", lambda: called.setdefault("scrape", True)
        )
        monkeypatch.setattr(
            exporter.scraper,
            "start_background_scrape",
            lambda **_: called.setdefault("background", True),
        )
        monkeypatch.setattr(
            exporter.http_server,
            "serve",
            lambda addr, port, handler: called.setdefault("serve", (addr, port, handler)),
        )

        exporter.main()

        assert called["verbose"] is True
        assert called["scrape"] is True
        assert called["background"] is True
        assert called["serve"][0] == exporter.scraper.SETTINGS.listen_addr
        assert called["serve"][1] == exporter.scraper.SETTINGS.listen_port

    def test_main_handles_initial_scrape_failure(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        called = {}

        monkeypatch.setattr(exporter, "parse_args", lambda: SimpleNamespace(verbose=False))
        monkeypatch.setattr(exporter, "configure_logging", lambda verbose: None)

        def _boom():
            called["scrape"] = True
            raise RuntimeError("boom")

        monkeypatch.setattr(exporter, "scrape_and_update", _boom)
        monkeypatch.setattr(
            exporter.scraper,
            "start_background_scrape",
            lambda **_: called.setdefault("background", True),
        )
        monkeypatch.setattr(
            exporter.http_server,
            "serve",
            lambda addr, port, handler: called.setdefault("serve", (addr, port, handler)),
        )

        with caplog.at_level("ERROR"):
            exporter.main()

        assert called["scrape"] is True
        assert called["background"] is True
        assert called["serve"][0] == exporter.scraper.SETTINGS.listen_addr
        assert "Initial scrape failed" in caplog.text


class TestReadVersion:
    def test_read_version_from_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        fake_exporter = tmp_path / "a" / "b" / "c" / "exporter.py"
        fake_exporter.parent.mkdir(parents=True)
        (fake_exporter.parents[2] / "VERSION").write_text("9.9.9")
        monkeypatch.setattr(exporter, "__file__", str(fake_exporter))

        assert exporter._read_version() == "9.9.9"

    def test_read_version_fallbacks(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        fake_exporter = tmp_path / "a" / "b" / "c" / "exporter.py"
        fake_exporter.parent.mkdir(parents=True)
        monkeypatch.setattr(exporter, "__file__", str(fake_exporter))
        monkeypatch.setattr(pihole_sqlite_exporter, "__version__", "1.2.3", raising=False)

        assert exporter._read_version() == "1.2.3"

        monkeypatch.delattr(pihole_sqlite_exporter, "__version__", raising=False)
        assert exporter._read_version() == "unknown"


class TestReadCommit:
    def test_read_commit_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GIT_COMMIT", "a")
        monkeypatch.setenv("GIT_SHA", "b")
        monkeypatch.setenv("SOURCE_COMMIT", "c")
        assert exporter._read_commit() == "a"

        monkeypatch.delenv("GIT_COMMIT", raising=False)
        assert exporter._read_commit() == "b"

        monkeypatch.delenv("GIT_SHA", raising=False)
        assert exporter._read_commit() == "c"

    def test_read_commit_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GIT_COMMIT", raising=False)
        monkeypatch.delenv("GIT_SHA", raising=False)
        monkeypatch.delenv("SOURCE_COMMIT", raising=False)
        assert exporter._read_commit() == "unknown"
