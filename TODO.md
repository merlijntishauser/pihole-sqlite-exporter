# TODO (Refactor Proposals)

- Add a lightweight “scrape duration” gauge to expose `scrape_and_update` time without relying only on logs.
- Make `ENABLE_LIFETIME_DEST_COUNTERS` a runtime toggle in logs and metrics (emit when disabled) to explain missing series.
- Reduce global state: scraper.py still relies on module globals for config and metrics state. Consider a small ScrapeContext passed to functions so
  tests and runtime are less stateful.
- Add scrape duration metric: A simple gauge for last_scrape_seconds and last_scrape_success will help diagnose slow scrapes without relying on logs.
