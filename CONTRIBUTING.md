# Contributing

Thanks for contributing! This project values XP practices: clear naming, readable code, small refactors, and frequent commits.

## How the exporter works
- **Data source:** The exporter reads Pi-hole metrics directly from the SQLite databases (`pihole-FTL.db`, optionally `gravity.db`). It does not use the Pi-hole HTTP API.
- **Scraping model:** A background loop periodically refreshes metrics (`SCRAPE_INTERVAL`). HTTP requests serve the latest registry values and only compute request rate.
- **Request rate:** Computed per client request using a row cursor (`rowid` or `id`) from the `queries` table. If no cursor exists, it falls back to counters deltas.
- **Metrics:** Prometheus metrics are emitted from a dedicated registry. Counters for lifetime totals are served via custom collectors; gauges represent daily and top‑list metrics.
- **Concurrency:** The HTTP server is single-threaded; background scraping runs in a daemon thread.

## Code structure
- `src/pihole_sqlite_exporter/exporter.py`: Scraper + HTTP server orchestration, metrics registry, and request-rate logic.
- `src/pihole_sqlite_exporter/config.py`: Legacy config helper (not used by the current exporter).
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
