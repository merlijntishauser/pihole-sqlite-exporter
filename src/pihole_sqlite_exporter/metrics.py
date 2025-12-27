from typing import TYPE_CHECKING

from prometheus_client.core import CounterMetricFamily

if TYPE_CHECKING:
    from .exporter import Scraper


class PiholeTotalsCollector:
    def __init__(self, scraper: "Scraper") -> None:
        self.scraper = scraper

    def collect(self):
        host = self.scraper.config.hostname_label

        m1 = CounterMetricFamily(
            "pihole_dns_queries_total",
            (
                "Total number of DNS queries (lifetime, monotonic) as reported by Pi-hole FTL "
                "counters table"
            ),
            labels=["hostname"],
        )
        m1.add_metric([host], float(self.scraper.total_queries_lifetime))
        yield m1

        m2 = CounterMetricFamily(
            "pihole_ads_blocked_total",
            (
                "Total number of blocked queries (lifetime, monotonic) as reported by Pi-hole FTL "
                "counters table"
            ),
            labels=["hostname"],
        )
        m2.add_metric([host], float(self.scraper.blocked_queries_lifetime))
        yield m2


class PiholeDestTotalsCollector:
    def __init__(self, scraper: "Scraper") -> None:
        self.scraper = scraper

    def collect(self):
        host = self.scraper.config.hostname_label
        m = CounterMetricFamily(
            "pihole_forward_destinations_total",
            (
                "Total number of forward destinations requests made by Pi-hole by destination "
                "(lifetime, derived from queries table)"
            ),
            labels=["hostname", "destination", "destination_name"],
        )

        for dest in sorted(self.scraper.forward_destinations_lifetime.keys()):
            cnt = self.scraper.forward_destinations_lifetime.get(dest, 0)
            m.add_metric([host, dest, dest], float(cnt))

        yield m


__all__ = ["PiholeTotalsCollector", "PiholeDestTotalsCollector"]
