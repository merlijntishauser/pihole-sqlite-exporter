import pytest

from pihole_sqlite_exporter.settings import Settings, env_truthy


class TestSettings:
    def test_settings_from_env_success(self) -> None:
        env = {
            "FTL_DB_PATH": "/tmp/ftl.db",
            "GRAVITY_DB_PATH": "/tmp/gravity.db",
            "LISTEN_ADDR": "127.0.0.1",
            "LISTEN_PORT": "1234",
            "HOSTNAME_LABEL": "test-host",
            "TOP_N": "5",
            "SCRAPE_INTERVAL": "10",
            "EXPORTER_TZ": "UTC",
            "ENABLE_LIFETIME_DEST_COUNTERS": "false",
        }

        settings = Settings.from_env(env)

        assert settings.ftl_db_path == "/tmp/ftl.db"
        assert settings.gravity_db_path == "/tmp/gravity.db"
        assert settings.listen_addr == "127.0.0.1"
        assert settings.listen_port == 1234
        assert settings.hostname_label == "test-host"
        assert settings.top_n == 5
        assert settings.scrape_interval == 10
        assert settings.exporter_tz == "UTC"
        assert settings.enable_lifetime_dest_counters is False

    @pytest.mark.parametrize(
        ("env", "error"),
        [
            ({"LISTEN_PORT": "0"}, "LISTEN_PORT must be >= 1"),
            ({"LISTEN_PORT": "70000"}, "LISTEN_PORT must be <="),
            ({"TOP_N": "0"}, "TOP_N must be >= 1"),
            ({"SCRAPE_INTERVAL": "0"}, "SCRAPE_INTERVAL must be >= 1"),
        ],
    )
    def test_settings_from_env_invalid(self, env, error: str) -> None:
        with pytest.raises(ValueError, match=error):
            Settings.from_env(env)


class TestEnvTruthy:
    def test_env_truthy_reads_yes(self) -> None:
        assert env_truthy("TEST_TRUTHY", env={"TEST_TRUTHY": "yes"}) is True

    def test_env_truthy_reads_zero(self) -> None:
        assert env_truthy("TEST_FALSY", env={"TEST_FALSY": "0"}) is False

    def test_env_truthy_default_true(self) -> None:
        assert env_truthy("MISSING", "true", env={}) is True


class TestVersionSync:
    def test_init_version_matches_file(self) -> None:
        from pathlib import Path

        from pihole_sqlite_exporter import __version__

        version_path = Path(__file__).resolve().parents[1] / "VERSION"
        assert version_path.read_text().strip() == __version__
