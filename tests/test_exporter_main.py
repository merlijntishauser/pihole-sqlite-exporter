import sys
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

    def test_main_logs_startup_when_commit_unknown(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        called = {}

        monkeypatch.setattr(exporter, "parse_args", lambda: SimpleNamespace(verbose=False))
        monkeypatch.setattr(exporter, "configure_logging", lambda verbose: None)
        monkeypatch.setattr(exporter, "_read_version", lambda: "1.2.3")
        monkeypatch.setattr(exporter, "_read_commit", lambda: "unknown")
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

        with caplog.at_level("INFO"):
            exporter.main()

        assert "Exporter version=1.2.3" in caplog.text
        assert "Starting exporter (listen=" in caplog.text


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

    def test_read_commit_strips_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GIT_COMMIT", "  abc123  ")
        assert exporter._read_commit() == "abc123"


class TestExporterHelpers:
    def test_env_truthy_delegates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = {}

        def _fake(name: str, default: str) -> bool:
            called["name"] = name
            called["default"] = default
            return True

        monkeypatch.setattr(exporter, "env_truthy", _fake)

        assert exporter._env_truthy("DEBUG", "false") is True
        assert called == {"name": "DEBUG", "default": "false"}

    def test_get_tz_delegates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(exporter.scraper, "get_tz", lambda: "UTC")
        assert exporter._get_tz() == "UTC"

    def test_variance_delegates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = {}

        def _fake(values):
            called["values"] = values
            return 1.5

        monkeypatch.setattr(exporter.scraper, "variance", _fake)

        assert exporter.variance([1, 2, 3]) == 1.5
        assert called["values"] == [1, 2, 3]

    def test_configure_logging_sets_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = {}

        def _basic_config(**kwargs):
            called.update(kwargs)

        monkeypatch.setattr(exporter.logging, "basicConfig", _basic_config)

        exporter.configure_logging(verbose=True)

        assert called["level"] == exporter.logging.DEBUG
        assert "format" in called

    def test_parse_args_verbose(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["prog", "--verbose"])

        args = exporter.parse_args()

        assert args.verbose is True

    def test_parse_args_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["prog"])

        args = exporter.parse_args()

        assert args.verbose is False
