# TODO (Refactor Proposals)

- Factor request-rate logic into a small helper module so the exporter no longer mixes HTTP concerns with rate computation.
- Introduce a tiny `metrics_state` data structure to hold `_total_queries_lifetime`, `_blocked_queries_lifetime`, and request-rate cursors in one place.
- Add a lightweight “scrape duration” gauge to expose `scrape_and_update` time without relying only on logs.
- Split long `scrape_and_update` into smaller, named helpers (counters, daily queries, top lists, gravity, rate) to improve testability.
- Make `ENABLE_LIFETIME_DEST_COUNTERS` a runtime toggle in logs and metrics (emit when disabled) to explain missing series.
- Add explicit handling for `queries` tables missing `rowid`/`id` (metric or log once) to avoid silent fallbacks.
- Split exporter into modules: `scraper.py` (scrape/update), `http_server.py` (handler + server), `metrics.py` (registry/collectors), and `db.py` (SQLite helpers).
