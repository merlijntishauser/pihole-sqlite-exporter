import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass
class Settings:
    ftl_db_path: str
    gravity_db_path: str
    listen_addr: str
    listen_port: int
    hostname_label: str
    top_n: int
    scrape_interval: int
    exporter_tz: str
    enable_lifetime_dest_counters: bool
    lifetime_dest_cache_seconds: int
    lifetime_dest_scan_interval: int
    lifetime_dest_max_entries: int
    summary_only: bool

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        environment = os.environ
        if env is not None:
            environment = env

        def _get(name: str, default: str) -> str:
            return environment.get(name, default)

        def _get_int(name: str, default: int) -> int:
            value = _get(name, str(default))
            parsed = int(value)
            if parsed < 1:
                raise ValueError(f"{name} must be >= 1 (got {value!r})")
            return parsed

        def _get_nonneg_int(name: str, default: int) -> int:
            value = _get(name, str(default))
            parsed = int(value)
            if parsed < 0:
                raise ValueError(f"{name} must be >= 0 (got {value!r})")
            return parsed

        listen_port = _get_int("LISTEN_PORT", 9617)
        if listen_port > 65535:
            raise ValueError(f"LISTEN_PORT must be <= 65535 (got {listen_port!r})")

        return cls(
            ftl_db_path=_get("FTL_DB_PATH", "/etc/pihole/pihole-FTL.db"),
            gravity_db_path=_get("GRAVITY_DB_PATH", "/etc/pihole/gravity.db"),
            listen_addr=_get("LISTEN_ADDR", "0.0.0.0"),
            listen_port=listen_port,
            hostname_label=_get("HOSTNAME_LABEL", "host.docker.internal"),
            top_n=_get_int("TOP_N", 10),
            scrape_interval=_get_int("SCRAPE_INTERVAL", 60),
            exporter_tz=_get("EXPORTER_TZ", "Europe/Amsterdam"),
            enable_lifetime_dest_counters=env_truthy(
                "ENABLE_LIFETIME_DEST_COUNTERS",
                "true",
                environment,
            ),
            lifetime_dest_cache_seconds=_get_nonneg_int("LIFETIME_DEST_CACHE_SECONDS", 900),
            lifetime_dest_scan_interval=_get_int("LIFETIME_DEST_SCAN_INTERVAL", 60),
            lifetime_dest_max_entries=_get_nonneg_int("LIFETIME_DEST_MAX_ENTRIES", 2000),
            summary_only=env_truthy("SUMMARY_ONLY", "false", environment),
        )


def env_truthy(name: str, default: str = "false", env: Mapping[str, str] | None = None) -> bool:
    environment = os.environ
    if env is not None:
        environment = env
    value = environment.get(name, default)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}
