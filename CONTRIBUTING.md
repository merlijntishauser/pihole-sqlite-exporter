# Contributing

Thanks for contributing! This project values XP practices: clear naming, readable code, small refactors, and frequent commits.

## How the exporter works
- **Data source:** The exporter reads Pi-hole metrics directly from the SQLite databases (`pihole-FTL.db`, optionally `gravity.db`). It does not use the Pi-hole HTTP API.
- **Scraping model:** A background loop periodically refreshes metrics (`SCRAPE_INTERVAL`). HTTP requests serve cached metrics; if no cache exists yet, the handler triggers a one-time refresh.
- **Metrics:** Prometheus metrics are emitted from a dedicated registry. Counters for lifetime totals are served via custom collectors; gauges represent daily and top‑list metrics.
- **Concurrency:** The HTTP server uses a threading model, while scraping is guarded by a lock to prevent overlapping DB access.

## Code structure
- `src/pihole_sqlite_exporter/config.py`: Environment‑driven configuration (`Config`).
- `src/pihole_sqlite_exporter/utils.py`: Helpers (SQLite read-only connection, time helpers, variance).
- `src/pihole_sqlite_exporter/queries.py`: SQL query strings.
- `src/pihole_sqlite_exporter/gauges.py`: Gauge definitions and clearing of dynamic series.
- `src/pihole_sqlite_exporter/metrics.py`: Custom collectors for lifetime totals.
- `src/pihole_sqlite_exporter/exporter.py`: Scraper + HTTP server orchestration.

## Tests and linting
- **Lint:** `ruff check .`
- **Format:** `ruff format .`
- **Tests:** `pytest`

## Docker verification (optional)
- **Local scan:** `make docker-verify` (Dockle + Trivy in containers)

## Development tips
- Keep functions small and intention‑revealing.
- Prefer data‑returning helpers and explicit types when it improves clarity.
- Update tests with any functional changes, especially around scraping and caching.
