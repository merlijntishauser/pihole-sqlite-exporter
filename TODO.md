# TODO (Refactor Proposals)

- Add a lightweight “scrape duration” gauge to expose `scrape_and_update` time without relying only on logs.
- Split long `scrape_and_update` into smaller, named helpers (counters, daily queries, top lists, gravity, rate) to improve testability.
- Make `ENABLE_LIFETIME_DEST_COUNTERS` a runtime toggle in logs and metrics (emit when disabled) to explain missing series.
- Add explicit handling for `queries` tables missing `rowid`/`id` (metric or log once) to avoid silent fallbacks.
- Reduce global state surface: scraper.py still relies on module globals for config and metrics state. Consider a small ScrapeContext object passed to functions so
  tests and runtime are less stateful.
- Tighten module contracts: metrics.py exposes many globals; group them into a Metrics dataclass or namespace to make dependencies explicit and avoid direct global
  access.
- Improve request‑rate robustness: Add a one‑time log (or metric) when falling back from row cursor to counters, so operators know which mode is active.
- Isolate SQL: Most SQL lives inline in scraper.py. Extract into a queries.py module with named constants for readability and easier tests.
- Add scrape duration metric: A simple gauge for last_scrape_seconds and last_scrape_success will help diagnose slow scrapes without relying on logs.
- Clarify config: config.py is unused; either remove it or re‑adopt it to avoid confusion.
