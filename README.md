# pihole-sqlite-exporter

Prometheus exporter that reads Pi-hole metrics from **pihole-FTL.db** (and optionally **gravity.db**) without using the Pi-hole API.

## Repository Overview
<!-- overview:start -->
- **Docker image:** hardened minimal runtime (non-root by default) with an HTTP healthcheck on `/metrics`.
- **Docker Hub:** https://hub.docker.com/r/merlijntishauser/pihole-sqlite-exporter
- **GitHub:** https://github.com/merlijntishauser/pihole-sqlite-exporter
- **Scan summary (2025-12-30 09:09 UTC):** Dockle: FATAL=2, INFO=2, PASS=14. Trivy: 0 vulnerabilities detected.
<!-- overview:end -->

## Why
- No HTTP API calls to Pi-hole
- No auth / TLS / timeouts / hanging requests
- Read-only SQLite

## Metrics
Exposes, among others:
- pihole_ads_blocked_today
- pihole_ads_percentage_today
- pihole_dns_queries_today / all_types
- pihole_querytypes (A/AAAA/...)
- pihole_reply (cname/nx_domain/...)
- pihole_forward_destinations (+ response time/variance)
- pihole_top_ads / top_queries / top_sources
- pihole_unique_clients / unique_domains
- pihole_request_rate (per-request delta)

## How it works
- A background loop scrapes SQLite on an interval (`SCRAPE_INTERVAL`) and updates the in-memory registry.
- `/metrics` serves the latest registry values and computes request rate on-demand.
- Request rate is calculated from the number of new rows since the previous client request. It uses a row cursor (`rowid` or `id`) when available and falls back to counters if no cursor is available.
- The exporter logs its version at startup and includes commit when `GIT_COMMIT` is set.

## Config (env)
| Variable | Default | Notes |
|---|---|---|
| FTL_DB_PATH | /etc/pihole/pihole-FTL.db | Pi-hole FTL SQLite DB |
| GRAVITY_DB_PATH | /etc/pihole/gravity.db | Optional for domains_being_blocked |
| HOSTNAME_LABEL | host.docker.internal | Label in metrics |
| LISTEN_ADDR | 0.0.0.0 | bind address |
| LISTEN_PORT | 9617 | bind port |
| TOP_N | 10 | top list size |
| SCRAPE_INTERVAL | 15 | background scrape interval (seconds) |
| ENABLE_LIFETIME_DEST_COUNTERS | true | scan full queries table for lifetime destinations |
| DEBUG | false | enable debug logging |
| GIT_COMMIT | (unset) | git commit string for startup log (optional) |

## CLI
- `--verbose` enables debug logging.

## Run (docker compose)
Pull from Docker Hub:
```bash
cd docker
docker compose -f docker-compose.example.yml up -d
```

Build locally:
```bash
cd docker
docker compose -f docker-compose.build.yml up -d --build
```
To include the commit in startup logs, set `GIT_COMMIT` before building (for example: `export GIT_COMMIT=$(git rev-parse --short HEAD)`).

## Test
```bash
wget -qO- http://127.0.0.1:9617/metrics
```

## Coverage
```bash
pytest --cov=src --cov-report=term-missing
```

## Lint
```bash
ruff check .
```

## Format
```bash
ruff format .
```

## Versioning
SemVer is tracked in `VERSION`.

```bash
make version-bump   # interactive: bumps patch by default, updates VERSION + __init__.py, commits, tags, pushes
```

## Docker release
For a multi-arch build/push (amd64/arm64):
```bash
make docker-buildx IMAGE_NAME=youruser/pihole-sqlite-exporter
```

## Docker verification
```bash
make docker-verify IMAGE_NAME=youruser/pihole-sqlite-exporter
```

## Notes
- Mount /etc/pihole read-only.
- domains_being_blocked prefers gravity.db (gravity table). If missing, it falls back to domain_by_id (less precise).
- If request rate looks lower than the Pi-hole UI, reduce Pi-hole's DB flush interval so SQLite updates more frequently.
- Disclaimer: AI assistance was used while writing parts of the codebase.
- Docker image base uses `dhi.io/python:3-alpine3.22` by default (override via `PYTHON_BASE_IMAGE` build arg).
- Docker Hub releases are automated on `vX.Y.Z` tags (multi-arch: amd64/arm64). Set `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets.
- GitHub Actions also needs `DHI_USERNAME` and `DHI_TOKEN` to pull the base image from `dhi.io`.
- If you hit `sqlite3.OperationalError: unable to open database file`, it is usually a volume path or permissions issue. On NAS systems you may need to run the container as root (`user: "0:0"`) or adjust the host file ownership/permissions so the container user can read `/etc/pihole/pihole-FTL.db`.
