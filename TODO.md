# TODO (Refactor Proposals)

## Short-term (next)

- Make `ENABLE_LIFETIME_DEST_COUNTERS` a runtime toggle in logs and metrics (emit when disabled) to explain missing series.
- Consolidate exporter-related tests into a single module (merge `test_exporter_main.py` and `test_health_ready.py`).
- Add exporter self-metrics (scrape loop lag, last error, cache hit/miss, per-query timings).
- Add a high-cardinality-safe `/metrics?summary=1` mode that omits top_* and forward destination series.
- Add `pihole_gravity_available` and continue scraping when gravity.db is unavailable.
- Add histogram metrics for forward destination response times (instead of only averages/variance).

## Medium-term

- Reduce global state: scraper.py still relies on module globals for config and metrics state. Consider a small ScrapeContext passed to functions so
  tests and runtime are less stateful.
- Add a tiny metrics registry factory for tests to reduce reliance on module globals.
- Support multiple Pi-hole instances (config list of DBs + hostname labels).
- Add ruleset metrics (regex/wildcard/whitelist/blacklist counts by type).
- Add jitter to scrape interval to avoid synchronized DB load.
- Add DB health metrics (db size, sqlite pragma values, last gravity update timestamp).

## Later

- Add a lightweight `/config` endpoint (redacted) with active settings + version/commit.
