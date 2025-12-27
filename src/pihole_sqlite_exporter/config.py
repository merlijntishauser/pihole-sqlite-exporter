import os
from dataclasses import dataclass

from .utils import env_truthy


@dataclass(frozen=True)
class Config:
    ftl_db_path: str
    gravity_db_path: str
    listen_addr: str
    listen_port: int
    hostname_label: str
    top_n: int
    scrape_interval: int
    exporter_tz: str
    enable_lifetime_dest_counters: bool
    request_rate_window_sec: int = 60

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            ftl_db_path=os.getenv("FTL_DB_PATH", "/etc/pihole/pihole-FTL.db"),
            gravity_db_path=os.getenv("GRAVITY_DB_PATH", "/etc/pihole/gravity.db"),
            listen_addr=os.getenv("LISTEN_ADDR", "0.0.0.0"),
            listen_port=int(os.getenv("LISTEN_PORT", "9617")),
            hostname_label=os.getenv("HOSTNAME_LABEL", "host.docker.internal"),
            top_n=int(os.getenv("TOP_N", "10")),
            scrape_interval=int(os.getenv("SCRAPE_INTERVAL", "15")),
            request_rate_window_sec=int(os.getenv("REQUEST_RATE_WINDOW_SEC", "60")),
            exporter_tz=os.getenv("EXPORTER_TZ", "Europe/Amsterdam"),
            enable_lifetime_dest_counters=env_truthy("ENABLE_LIFETIME_DEST_COUNTERS", "true"),
        )
