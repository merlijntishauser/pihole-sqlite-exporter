# pihole-sqlite-exporter
[![CI](https://github.com/merlijntishauser/pihole-sqlite-exporter/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/merlijntishauser/pihole-sqlite-exporter/actions/workflows/ci.yml) [![Docker Release](https://github.com/merlijntishauser/pihole-sqlite-exporter/actions/workflows/docker-release.yml/badge.svg?branch=main)](https://github.com/merlijntishauser/pihole-sqlite-exporter/actions/workflows/docker-release.yml) [![CodeQL](https://github.com/merlijntishauser/pihole-sqlite-exporter/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/merlijntishauser/pihole-sqlite-exporter/actions/workflows/codeql.yml)

Prometheus exporter that reads Pi-hole metrics from **pihole-FTL.db** (and optionally **gravity.db**) without using the Pi-hole API.

## Repository Overview
<!-- overview:start -->
- **Docker image:** hardened minimal runtime (non-root by default) with an HTTP healthcheck on `/healthz`.
- **Docker Hub:** https://hub.docker.com/r/merlijntishauser/pihole-sqlite-exporter
- **GitHub:** https://github.com/merlijntishauser/pihole-sqlite-exporter
- **Scan summary (2026-01-08 09:20 UTC):** Dockle: INFO=2, PASS=15. Trivy: 0 vulnerabilities detected.
<!-- overview:end -->

## Why
- No HTTP API calls to Pi-hole
- No auth / TLS / timeouts / hanging requests
- Read-only SQLite

## Metrics
All collected metrics (example values shown):
| Metric | Type | Example |
|---|---|---|
| pihole_dns_queries_total | counter | `pihole_dns_queries_total{hostname="pi"} 123456` |
| pihole_dns_queries_blocked_total | counter | `pihole_dns_queries_blocked_total{hostname="pi"} 1234` |
| pihole_forward_destinations_total | counter | `pihole_forward_destinations_total{hostname="pi",destination="cache",destination_name="cache"} 321` |
| pihole_ads_blocked_today | gauge | `pihole_ads_blocked_today{hostname="pi"} 123` |
| pihole_ads_percentage_today | gauge | `pihole_ads_percentage_today{hostname="pi"} 12.3` |
| pihole_clients_ever_seen | gauge | `pihole_clients_ever_seen{hostname="pi"} 42` |
| pihole_dns_queries_all_types | gauge | `pihole_dns_queries_all_types{hostname="pi"} 4567` |
| pihole_dns_queries_today | gauge | `pihole_dns_queries_today{hostname="pi"} 3456` |
| pihole_domains_being_blocked | gauge | `pihole_domains_being_blocked{hostname="pi"} 125000` |
| pihole_forward_destinations | gauge | `pihole_forward_destinations{hostname="pi",destination="cache",destination_name="cache"} 321` |
| pihole_forward_destinations_responsetime | gauge | `pihole_forward_destinations_responsetime{hostname="pi",destination="1.1.1.1",destination_name="cloudflare"} 0.032` |
| pihole_forward_destinations_responsevariance | gauge | `pihole_forward_destinations_responsevariance{hostname="pi",destination="1.1.1.1",destination_name="cloudflare"} 0.004` |
| pihole_queries_cached | gauge | `pihole_queries_cached{hostname="pi"} 1200` |
| pihole_queries_forwarded | gauge | `pihole_queries_forwarded{hostname="pi"} 2300` |
| pihole_querytypes | gauge | `pihole_querytypes{hostname="pi",type="A"} 2400` |
| pihole_reply | gauge | `pihole_reply{hostname="pi",type="NODATA"} 120` |
| pihole_scrape_duration_seconds | gauge | `pihole_scrape_duration_seconds{hostname="pi"} 0.145` |
| pihole_scrape_success | gauge | `pihole_scrape_success{hostname="pi"} 1` |
| pihole_status | gauge | `pihole_status{hostname="pi"} 1` |
| pihole_top_ads | gauge | `pihole_top_ads{hostname="pi",domain="ads.example"} 42` |
| pihole_top_queries | gauge | `pihole_top_queries{hostname="pi",domain="example.com"} 120` |
| pihole_top_sources | gauge | `pihole_top_sources{hostname="pi",source="192.168.1.10",source_name="laptop"} 80` |
| pihole_unique_clients | gauge | `pihole_unique_clients{hostname="pi"} 12` |
| pihole_unique_domains | gauge | `pihole_unique_domains{hostname="pi"} 987` |

## How it works
- A background loop scrapes SQLite on an interval (`SCRAPE_INTERVAL`) and updates the in-memory registry.
- The exporter performs a warm scrape at startup, then waits one full `SCRAPE_INTERVAL` before the next scheduled scrape.
- The scrape loop renders a metrics snapshot into memory.
- `/metrics` serves the latest cached snapshot (no SQLite access in the request path).
- `/healthz` returns 200 when the last scrape succeeded and the snapshot is fresh.
- `/readyz` returns 200 after the first successful scrape.
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
| SCRAPE_INTERVAL | 60 | background scrape interval (seconds) |
| ENABLE_LIFETIME_DEST_COUNTERS | true | scan full queries table for lifetime destinations |
| LIFETIME_DEST_CACHE_SECONDS | 900 | cache lifetime destinations (seconds); 0 disables cache |
| DEBUG | false | enable debug logging |
| GIT_COMMIT | (unset) | git commit string for startup log (optional) |
| GIT_SHA | (unset) | alternate commit string for startup log (optional) |
| SOURCE_COMMIT | (unset) | alternate commit string for startup log (optional) |

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
Health endpoints:
```bash
wget -qO- http://127.0.0.1:9617/healthz
wget -qO- http://127.0.0.1:9617/readyz
```






## Docker release
For a multi-arch build/push (amd64/arm64):
```bash
make docker-buildx IMAGE_NAME=youruser/pihole-sqlite-exporter
```

## Notes
- Mount /etc/pihole read-only.
- domains_being_blocked prefers gravity.db (gravity table). If missing, it falls back to domain_by_id (less precise).
- Pi-hole controls how often queries are flushed to the FTL database via `DBinterval` (default 60s). This exporter reads whatever is persisted.
- Disclaimer: AI assistance was used while writing parts of the codebase.
- Docker image base uses `dhi.io/python:3-alpine3.22` by default (override via `PYTHON_BASE_IMAGE` build arg).
- Docker Hub releases are automated on `vX.Y.Z` tags (multi-arch: amd64/arm64). Set `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets.
- GitHub Actions also needs `DHI_USERNAME` and `DHI_TOKEN` to pull the base image from `dhi.io`.
- If you hit `sqlite3.OperationalError: unable to open database file`, it is usually a volume path or permissions issue. On NAS systems you may need to run the container as root (`user: "0:0"`) or adjust the host file ownership/permissions so the container user can read `/etc/pihole/pihole-FTL.db`.

## I really fancy coffee! and stars! and... oh wait... 

[![Buy me a coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/merlijntishauser)
