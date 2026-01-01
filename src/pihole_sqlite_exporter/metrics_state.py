from dataclasses import dataclass


@dataclass
class MetricsState:
    total_queries_lifetime: int = 0
    blocked_queries_lifetime: int = 0
