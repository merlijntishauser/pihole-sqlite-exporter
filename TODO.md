# TODO (Refactor Proposals)

## Short-term (next)

- Make `ENABLE_LIFETIME_DEST_COUNTERS` a runtime toggle in logs and metrics (emit when disabled) to explain missing series.
- Consolidate exporter-related tests into a single module (merge `test_exporter_main.py` and `test_health_ready.py`).

## Medium-term

- Reduce global state: scraper.py still relies on module globals for config and metrics state. Consider a small ScrapeContext passed to functions so
  tests and runtime are less stateful.
- Add a tiny metrics registry factory for tests to reduce reliance on module globals.

## Later

