from prometheus_client import CollectorRegistry, Gauge
from prometheus_client.core import CounterMetricFamily

from .metrics_state import MetricsState


class Metrics:
    def __init__(self, hostname_label: str) -> None:
        self.hostname_label = hostname_label
        self.registry = CollectorRegistry()
        self.state = MetricsState()
        self._forward_destinations_lifetime: dict[str, int] = {}

        metrics_ref = self

        class PiholeTotalsCollector:
            def collect(inner_self):
                host = metrics_ref.hostname_label

                total_queries_metric = CounterMetricFamily(
                    "pihole_dns_queries_total",
                    (
                        "Total number of DNS queries (lifetime, monotonic) as reported by "
                        "Pi-hole FTL counters table"
                    ),
                    labels=["hostname"],
                )
                total_queries_metric.add_metric(
                    [host], float(metrics_ref.state.total_queries_lifetime)
                )
                yield total_queries_metric

                blocked_queries_metric = CounterMetricFamily(
                    "pihole_ads_blocked_total",
                    (
                        "Total number of blocked queries (lifetime, monotonic) as reported by "
                        "Pi-hole FTL counters table"
                    ),
                    labels=["hostname"],
                )
                blocked_queries_metric.add_metric(
                    [host], float(metrics_ref.state.blocked_queries_lifetime)
                )
                yield blocked_queries_metric

        class PiholeDestTotalsCollector:
            def collect(inner_self):
                host = metrics_ref.hostname_label
                forward_destinations_metric = CounterMetricFamily(
                    "pihole_forward_destinations_total",
                    (
                        "Total number of forward destinations requests made by Pi-hole by "
                        "destination (lifetime, derived from queries table)"
                    ),
                    labels=["hostname", "destination", "destination_name"],
                )

                for dest in sorted(metrics_ref._forward_destinations_lifetime.keys()):
                    cnt = metrics_ref._forward_destinations_lifetime.get(dest, 0)
                    forward_destinations_metric.add_metric([host, dest, dest], float(cnt))

                yield forward_destinations_metric

        self.registry.register(PiholeTotalsCollector())
        self.registry.register(PiholeDestTotalsCollector())

        self.pihole_ads_blocked_today = Gauge(
            "pihole_ads_blocked_today",
            "Represents the number of ads blocked over the current day",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_ads_percentage_today = Gauge(
            "pihole_ads_percentage_today",
            "Represents the percentage of ads blocked over the current day",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_clients_ever_seen = Gauge(
            "pihole_clients_ever_seen",
            "Represents the number of clients ever seen",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_dns_queries_all_types = Gauge(
            "pihole_dns_queries_all_types",
            "Represents the number of DNS queries across all types",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_dns_queries_today = Gauge(
            "pihole_dns_queries_today",
            "Represents the number of DNS queries made over the current day",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_domains_being_blocked = Gauge(
            "pihole_domains_being_blocked",
            "Represents the number of domains being blocked",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_forward_destinations = Gauge(
            "pihole_forward_destinations",
            "Represents the number of forward destination requests made by Pi-hole by destination",
            ["hostname", "destination", "destination_name"],
            registry=self.registry,
        )

        self.pihole_forward_destinations_responsetime = Gauge(
            "pihole_forward_destinations_responsetime",
            "Represents the average response time of a destination in seconds",
            ["hostname", "destination", "destination_name"],
            registry=self.registry,
        )

        self.pihole_forward_destinations_responsevariance = Gauge(
            "pihole_forward_destinations_responsevariance",
            "Represents the response time variance of a destination in seconds",
            ["hostname", "destination", "destination_name"],
            registry=self.registry,
        )

        self.pihole_queries_cached = Gauge(
            "pihole_queries_cached",
            "Represents the number of cached queries",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_queries_forwarded = Gauge(
            "pihole_queries_forwarded",
            "Represents the number of forwarded queries",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_querytypes = Gauge(
            "pihole_querytypes",
            "Represents the number of queries made by Pi-hole by type",
            ["hostname", "type"],
            registry=self.registry,
        )

        self.pihole_reply = Gauge(
            "pihole_reply",
            "Represents the number of replies by type",
            ["hostname", "type"],
            registry=self.registry,
        )

        self.pihole_request_rate = Gauge(
            "pihole_request_rate",
            "Represents the number of requests per second",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_scrape_duration_seconds = Gauge(
            "pihole_scrape_duration_seconds",
            "Time spent in scrape_and_update in seconds",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_scrape_success = Gauge(
            "pihole_scrape_success",
            "Whether the last scrape succeeded (1 for success, 0 for failure)",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_status = Gauge(
            "pihole_status",
            "Whether Pi-hole is enabled",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_top_ads = Gauge(
            "pihole_top_ads",
            "Represents the number of top ads by domain",
            ["hostname", "domain"],
            registry=self.registry,
        )

        self.pihole_top_queries = Gauge(
            "pihole_top_queries",
            "Represents the number of top queries by domain",
            ["hostname", "domain"],
            registry=self.registry,
        )

        self.pihole_top_sources = Gauge(
            "pihole_top_sources",
            "Represents the number of top sources by source host",
            ["hostname", "source", "source_name"],
            registry=self.registry,
        )

        self.pihole_unique_clients = Gauge(
            "pihole_unique_clients",
            "Represents the number of unique clients seen in the last 24h",
            ["hostname"],
            registry=self.registry,
        )

        self.pihole_unique_domains = Gauge(
            "pihole_unique_domains",
            "Represents the number of unique domains seen",
            ["hostname"],
            registry=self.registry,
        )

    def set_hostname_label(self, label: str) -> None:
        self.hostname_label = label

    def set_lifetime_totals(self, total: int, blocked: int) -> None:
        self.state.total_queries_lifetime = total
        self.state.blocked_queries_lifetime = blocked

    def set_forward_destinations_lifetime(self, lifetime: dict[str, int]) -> None:
        self._forward_destinations_lifetime = lifetime

    def clear_dynamic_series(self) -> None:
        self.pihole_top_ads.clear()
        self.pihole_top_queries.clear()
        self.pihole_top_sources.clear()
        self.pihole_forward_destinations.clear()
        self.pihole_forward_destinations_responsetime.clear()
        self.pihole_forward_destinations_responsevariance.clear()


METRICS = Metrics("host.docker.internal")
