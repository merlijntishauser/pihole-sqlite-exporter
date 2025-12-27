from dataclasses import dataclass

from prometheus_client import Gauge


@dataclass
class Gauges:
    ads_blocked_today: Gauge
    ads_percentage_today: Gauge
    clients_ever_seen: Gauge
    dns_queries_all_types: Gauge
    dns_queries_today: Gauge
    domains_being_blocked: Gauge
    forward_destinations: Gauge
    forward_destinations_responsetime: Gauge
    forward_destinations_responsevariance: Gauge
    queries_cached: Gauge
    queries_forwarded: Gauge
    querytypes: Gauge
    reply: Gauge
    request_rate: Gauge
    status: Gauge
    top_ads: Gauge
    top_queries: Gauge
    top_sources: Gauge
    unique_clients: Gauge
    unique_domains: Gauge

    @classmethod
    def create(cls, registry) -> "Gauges":
        return cls(
            ads_blocked_today=Gauge(
                "pihole_ads_blocked_today",
                "Represents the number of ads blocked over the current day",
                ["hostname"],
                registry=registry,
            ),
            ads_percentage_today=Gauge(
                "pihole_ads_percentage_today",
                "Represents the percentage of ads blocked over the current day",
                ["hostname"],
                registry=registry,
            ),
            clients_ever_seen=Gauge(
                "pihole_clients_ever_seen",
                "Represents the number of clients ever seen",
                ["hostname"],
                registry=registry,
            ),
            dns_queries_all_types=Gauge(
                "pihole_dns_queries_all_types",
                "Represents the number of DNS queries across all types",
                ["hostname"],
                registry=registry,
            ),
            dns_queries_today=Gauge(
                "pihole_dns_queries_today",
                "Represents the number of DNS queries made over the current day",
                ["hostname"],
                registry=registry,
            ),
            domains_being_blocked=Gauge(
                "pihole_domains_being_blocked",
                "Represents the number of domains being blocked",
                ["hostname"],
                registry=registry,
            ),
            forward_destinations=Gauge(
                "pihole_forward_destinations",
                (
                    "Represents the number of forward destination requests made by Pi-hole by "
                    "destination"
                ),
                ["hostname", "destination", "destination_name"],
                registry=registry,
            ),
            forward_destinations_responsetime=Gauge(
                "pihole_forward_destinations_responsetime",
                (
                    "Represents the seconds a forward destination took to process a request made "
                    "by Pi-hole"
                ),
                ["hostname", "destination", "destination_name"],
                registry=registry,
            ),
            forward_destinations_responsevariance=Gauge(
                "pihole_forward_destinations_responsevariance",
                "Represents the variance in response time for forward destinations",
                ["hostname", "destination", "destination_name"],
                registry=registry,
            ),
            queries_cached=Gauge(
                "pihole_queries_cached",
                "Represents the number of cached queries",
                ["hostname"],
                registry=registry,
            ),
            queries_forwarded=Gauge(
                "pihole_queries_forwarded",
                "Represents the number of forwarded queries",
                ["hostname"],
                registry=registry,
            ),
            querytypes=Gauge(
                "pihole_querytypes",
                "Represents the number of queries made by Pi-hole by type",
                ["hostname", "type"],
                registry=registry,
            ),
            reply=Gauge(
                "pihole_reply",
                "Represents the number of replies by type",
                ["hostname", "type"],
                registry=registry,
            ),
            request_rate=Gauge(
                "pihole_request_rate",
                "Represents the number of requests per second",
                ["hostname"],
                registry=registry,
            ),
            status=Gauge(
                "pihole_status",
                "Whether Pi-hole is enabled",
                ["hostname"],
                registry=registry,
            ),
            top_ads=Gauge(
                "pihole_top_ads",
                "Represents the number of top ads by domain",
                ["hostname", "domain"],
                registry=registry,
            ),
            top_queries=Gauge(
                "pihole_top_queries",
                "Represents the number of top queries by domain",
                ["hostname", "domain"],
                registry=registry,
            ),
            top_sources=Gauge(
                "pihole_top_sources",
                "Represents the number of top sources by source host",
                ["hostname", "source", "source_name"],
                registry=registry,
            ),
            unique_clients=Gauge(
                "pihole_unique_clients",
                "Represents the number of unique clients seen in the last 24h",
                ["hostname"],
                registry=registry,
            ),
            unique_domains=Gauge(
                "pihole_unique_domains",
                "Represents the number of unique domains seen",
                ["hostname"],
                registry=registry,
            ),
        )

    def clear_dynamic_series(self) -> None:
        self.top_ads.clear()
        self.top_queries.clear()
        self.top_sources.clear()
        self.forward_destinations.clear()
        self.forward_destinations_responsetime.clear()
        self.forward_destinations_responsevariance.clear()


__all__ = ["Gauges"]
