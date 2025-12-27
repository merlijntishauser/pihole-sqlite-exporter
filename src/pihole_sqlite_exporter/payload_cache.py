import threading
from dataclasses import dataclass


@dataclass
class PayloadCache:
    payload: bytes | None = None
    timestamp: float | None = None
    last_error: str | None = None

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def get(self) -> tuple[bytes | None, str | None]:
        with self._lock:
            return self.payload, self.last_error

    def set(self, payload: bytes, timestamp: float) -> None:
        with self._lock:
            self.payload = payload
            self.timestamp = timestamp
            self.last_error = None

    def set_error(self, message: str) -> None:
        with self._lock:
            self.last_error = message
