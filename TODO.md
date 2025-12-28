# TODO (Refactor Proposals)

## Short-term (next)

- Make `ENABLE_LIFETIME_DEST_COUNTERS` a runtime toggle in logs and metrics (emit when disabled) to explain missing series.
- Consolidate log context (hostname, tz, sod, now) into a helper so scrape logs stay consistent and easy to search.

## Medium-term

- Add a simple config/settings dataclass to validate env overrides and defaults in one place (scraper + HTTP server).
- Reduce global state: scraper.py still relies on module globals for config and metrics state. Consider a small ScrapeContext passed to functions so
  tests and runtime are less stateful.
- Add a tiny metrics registry factory for tests to reduce reliance on module globals.

## Later

- Move QUERY/REPLY maps and blocked status set into a constants module to declutter scraper.py.
- Consider a scrape-skipped counter metric to quantify contention between HTTP requests and background scrape loop.
