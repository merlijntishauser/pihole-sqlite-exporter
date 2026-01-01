# Contributing

Thanks for contributing! This project values XP practices: clear naming, readable code, small refactors, and frequent commits.

## How the exporter works
- **Data source:** The exporter reads Pi-hole metrics directly from the SQLite databases (`pihole-FTL.db`, optionally `gravity.db`). It does not use the Pi-hole HTTP API.
- **Scraping model:** A background loop periodically refreshes metrics (`SCRAPE_INTERVAL`). HTTP requests serve the latest snapshot from memory.
- **Health endpoints:** `/healthz` returns 200 when the last scrape succeeded and the snapshot is fresh; `/readyz` returns 200 after the first successful scrape.
- **Scrape timing:** `scrape_and_update` records duration and success with gauges; overlapping scrapes are skipped via a non-blocking lock.
- **Metrics:** Prometheus metrics are emitted from a dedicated registry. Counters for lifetime totals are served via custom collectors; gauges represent daily and top‑list metrics.
- **Concurrency:** The HTTP server is single-threaded; background scraping runs in a daemon thread.

## Code structure
- `src/pihole_sqlite_exporter/exporter.py`: CLI entrypoint and orchestration.
- `src/pihole_sqlite_exporter/scraper.py`: Scrape/update logic and background loop.
- `src/pihole_sqlite_exporter/http_server.py`: HTTP handler and server wiring.
- `src/pihole_sqlite_exporter/metrics.py`: Registry, gauges, and collectors.
- `src/pihole_sqlite_exporter/db.py`: SQLite helpers.
- `tests/`: Unit tests for scrape logic and request rate behavior.

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
- Remember that Pi-hole controls FTL DB flush cadence via `DBinterval` (default 60s); the exporter reads persisted data.
