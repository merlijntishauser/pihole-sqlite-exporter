from dataclasses import dataclass, field

from .request_rate import RequestRateTracker


@dataclass
class MetricsState:
    total_queries_lifetime: int = 0
    blocked_queries_lifetime: int = 0
    request_rate: RequestRateTracker = field(default_factory=RequestRateTracker)
