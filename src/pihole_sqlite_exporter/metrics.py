import os

from prometheus_client import CollectorRegistry, Gauge
from prometheus_client.core import CounterMetricFamily

HOSTNAME_LABEL = os.getenv("HOSTNAME_LABEL", "host.docker.internal")

REGISTRY = CollectorRegistry()

_total_queries_lifetime = 0
_blocked_queries_lifetime = 0
_forward_destinations_lifetime: dict[str, int] = {}


def set_hostname_label(label: str) -> None:
    global HOSTNAME_LABEL
    HOSTNAME_LABEL = label


def set_lifetime_totals(total: int, blocked: int) -> None:
    global _total_queries_lifetime, _blocked_queries_lifetime
    _total_queries_lifetime = total
    _blocked_queries_lifetime = blocked


def set_forward_destinations_lifetime(lifetime: dict[str, int]) -> None:
    global _forward_destinations_lifetime
    _forward_destinations_lifetime = lifetime


class PiholeTotalsCollector:
    def collect(self):
        host = HOSTNAME_LABEL

        m1 = CounterMetricFamily(
            "pihole_dns_queries_total",
            (
                "Total number of DNS queries (lifetime, monotonic) as reported by Pi-hole FTL "
                "counters table"
            ),
            labels=["hostname"],
        )
        m1.add_metric([host], float(_total_queries_lifetime))
        yield m1

        m2 = CounterMetricFamily(
            "pihole_ads_blocked_total",
            (
                "Total number of blocked queries (lifetime, monotonic) as reported by Pi-hole FTL "
                "counters table"
            ),
            labels=["hostname"],
        )
        m2.add_metric([host], float(_blocked_queries_lifetime))
        yield m2


class PiholeDestTotalsCollector:
    def collect(self):
        host = HOSTNAME_LABEL
        m = CounterMetricFamily(
            "pihole_forward_destinations_total",
            (
                "Total number of forward destinations requests made by Pi-hole by destination "
                "(lifetime, derived from queries table)"
            ),
            labels=["hostname", "destination", "destination_name"],
        )

        for dest in sorted(_forward_destinations_lifetime.keys()):
            cnt = _forward_destinations_lifetime.get(dest, 0)
            m.add_metric([host, dest, dest], float(cnt))

        yield m


REGISTRY.register(PiholeTotalsCollector())
REGISTRY.register(PiholeDestTotalsCollector())

pihole_ads_blocked_today = Gauge(
    "pihole_ads_blocked_today",
    "Represents the number of ads blocked over the current day",
    ["hostname"],
    registry=REGISTRY,
)

pihole_ads_percentage_today = Gauge(
    "pihole_ads_percentage_today",
    "Represents the percentage of ads blocked over the current day",
    ["hostname"],
    registry=REGISTRY,
)

pihole_clients_ever_seen = Gauge(
    "pihole_clients_ever_seen",
    "Represents the number of clients ever seen",
    ["hostname"],
    registry=REGISTRY,
)

pihole_dns_queries_all_types = Gauge(
    "pihole_dns_queries_all_types",
    "Represents the number of DNS queries across all types",
    ["hostname"],
    registry=REGISTRY,
)

pihole_dns_queries_today = Gauge(
    "pihole_dns_queries_today",
    "Represents the number of DNS queries made over the current day",
    ["hostname"],
    registry=REGISTRY,
)

pihole_domains_being_blocked = Gauge(
    "pihole_domains_being_blocked",
    "Represents the number of domains being blocked",
    ["hostname"],
    registry=REGISTRY,
)

pihole_forward_destinations = Gauge(
    "pihole_forward_destinations",
    "Represents the number of forward destination requests made by Pi-hole by destination",
    ["hostname", "destination", "destination_name"],
    registry=REGISTRY,
)

pihole_forward_destinations_responsetime = Gauge(
    "pihole_forward_destinations_responsetime",
    "Represents the average response time of a destination in seconds",
    ["hostname", "destination", "destination_name"],
    registry=REGISTRY,
)

pihole_forward_destinations_responsevariance = Gauge(
    "pihole_forward_destinations_responsevariance",
    "Represents the response time variance of a destination in seconds",
    ["hostname", "destination", "destination_name"],
    registry=REGISTRY,
)

pihole_queries_cached = Gauge(
    "pihole_queries_cached",
    "Represents the number of cached queries",
    ["hostname"],
    registry=REGISTRY,
)

pihole_queries_forwarded = Gauge(
    "pihole_queries_forwarded",
    "Represents the number of forwarded queries",
    ["hostname"],
    registry=REGISTRY,
)

pihole_querytypes = Gauge(
    "pihole_querytypes",
    "Represents the number of queries made by Pi-hole by type",
    ["hostname", "type"],
    registry=REGISTRY,
)

pihole_reply = Gauge(
    "pihole_reply",
    "Represents the number of replies by type",
    ["hostname", "type"],
    registry=REGISTRY,
)

pihole_request_rate = Gauge(
    "pihole_request_rate",
    "Represents the number of requests per second",
    ["hostname"],
    registry=REGISTRY,
)

pihole_status = Gauge(
    "pihole_status",
    "Whether Pi-hole is enabled",
    ["hostname"],
    registry=REGISTRY,
)

pihole_top_ads = Gauge(
    "pihole_top_ads",
    "Represents the number of top ads by domain",
    ["hostname", "domain"],
    registry=REGISTRY,
)

pihole_top_queries = Gauge(
    "pihole_top_queries",
    "Represents the number of top queries by domain",
    ["hostname", "domain"],
    registry=REGISTRY,
)

pihole_top_sources = Gauge(
    "pihole_top_sources",
    "Represents the number of top sources by source host",
    ["hostname", "source", "source_name"],
    registry=REGISTRY,
)

pihole_unique_clients = Gauge(
    "pihole_unique_clients",
    "Represents the number of unique clients seen in the last 24h",
    ["hostname"],
    registry=REGISTRY,
)

pihole_unique_domains = Gauge(
    "pihole_unique_domains",
    "Represents the number of unique domains seen",
    ["hostname"],
    registry=REGISTRY,
)


def clear_dynamic_series() -> None:
    pihole_top_ads.clear()
    pihole_top_queries.clear()
    pihole_top_sources.clear()
    pihole_forward_destinations.clear()
    pihole_forward_destinations_responsetime.clear()
    pihole_forward_destinations_responsevariance.clear()
