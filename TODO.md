# TODO (Refactor Proposals)

## Short-term

- Add a lightweight “scrape duration” gauge to expose `scrape_and_update` timing (duration + success).
- Make `ENABLE_LIFETIME_DEST_COUNTERS` a runtime toggle in logs and metrics (emit when disabled) to explain missing series.
- Guard against overlapping scrapes by using a non-blocking lock and logging when a scrape is skipped.
- Consolidate log context (hostname, tz, sod, now) into a helper so scrape logs stay consistent and easy to search.

## Later

- Reduce global state: scraper.py still relies on module globals for config and metrics state. Consider a small ScrapeContext passed to functions so
  tests and runtime are less stateful.
- Add a simple config/settings dataclass to validate env overrides and defaults in one place (scraper + HTTP server).
- Add a tiny metrics registry factory for tests to reduce reliance on module globals.
