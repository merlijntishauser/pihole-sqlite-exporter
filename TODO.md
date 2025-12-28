# TODO (Refactor Proposals)

- Introduce a tiny `metrics_state` data structure to hold `_total_queries_lifetime`, `_blocked_queries_lifetime`, and request-rate cursors in one place.
- Add a lightweight “scrape duration” gauge to expose `scrape_and_update` time without relying only on logs.
- Split long `scrape_and_update` into smaller, named helpers (counters, daily queries, top lists, gravity, rate) to improve testability.
- Make `ENABLE_LIFETIME_DEST_COUNTERS` a runtime toggle in logs and metrics (emit when disabled) to explain missing series.
- Add explicit handling for `queries` tables missing `rowid`/`id` (metric or log once) to avoid silent fallbacks.
