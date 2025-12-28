# pihole-sqlite-exporter

Prometheus exporter that reads Pi-hole metrics from **pihole-FTL.db** (and optionally **gravity.db**) without using the Pi-hole API.

## Repository Overview
<!-- overview:start -->
- **Docker image:** hardened minimal runtime (non-root by default) with an HTTP healthcheck on `/metrics`.
- **Docker Hub:** https://hub.docker.com/r/merlijntishauser/pihole-sqlite-exporter
- **GitHub:** https://github.com/merlijntishauser/pihole-sqlite-exporter
- **Scan summary:** pending (generated on release tags).
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
- pihole_request_rate (delta-based)

## Config (env)
| Variable | Default | Notes |
|---|---|---|
| FTL_DB_PATH | /etc/pihole/pihole-FTL.db | Pi-hole FTL SQLite DB |
| GRAVITY_DB_PATH | /etc/pihole/gravity.db | Optional for domains_being_blocked |
| HOSTNAME_LABEL | host.docker.internal | Label in metrics |
| LISTEN_ADDR | 0.0.0.0 | bind address |
| LISTEN_PORT | 9617 | bind port |
| TOP_N | 10 | top list size |
| DEBUG | false | enable debug logging |

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

## Docker Hub
Image: https://hub.docker.com/r/merlijntishauser/pihole-sqlite-exporter

### Run (docker pull)
```bash
docker run -d \
  --name pihole_sqlite_exporter \
  -p 9617:9617 \
  -e HOSTNAME_LABEL=host.docker.internal \
  -e EXPORTER_TZ=Europe/Amsterdam \
  -e FTL_DB_PATH=/etc/pihole/pihole-FTL.db \
  -e GRAVITY_DB_PATH=/etc/pihole/gravity.db \
  -e LISTEN_ADDR=0.0.0.0 \
  -e LISTEN_PORT=9617 \
  -e TOP_N=10 \
  -v /etc/pihole:/etc/pihole:ro \
  merlijntishauser/pihole-sqlite-exporter:latest
```

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
make bump-patch   # or bump-minor / bump-major
git add VERSION
git commit -m "Bump version to $(cat VERSION)"
make tag
make push-tag
```

## Docker release
```bash
make docker-build IMAGE_NAME=youruser/pihole-sqlite-exporter
make docker-tag IMAGE_NAME=youruser/pihole-sqlite-exporter
make docker-push IMAGE_NAME=youruser/pihole-sqlite-exporter
```
For a multi-arch build/push (amd64/arm64):
```bash
make docker-buildx IMAGE_NAME=youruser/pihole-sqlite-exporter
```

## Local Docker verify
Build and scan locally with containerized tools:
```bash
make docker-verify IMAGE_NAME=merlijntishauser/pihole-sqlite-exporter
```

## Notes
- Mount /etc/pihole read-only.
- domains_being_blocked prefers gravity.db (gravity table). If missing, it falls back to domain_by_id (less precise).
- Disclaimer: AI assistance was used while writing parts of the codebase.
- Docker image base uses `dhi.io/python:3-alpine3.22` by default (override via `PYTHON_BASE_IMAGE` build arg).
- Docker Hub releases are automated on `vX.Y.Z` tags (multi-arch: amd64/arm64) and run Dockle + Trivy checks. Set `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets.
- GitHub Actions also needs `DHI_USERNAME` and `DHI_TOKEN` to pull the base image from `dhi.io`.
- If you hit `sqlite3.OperationalError: unable to open database file`, it is usually a volume path or permissions issue. On NAS systems you may need to run the container as root (`user: "0:0"`) or adjust the host file ownership/permissions so the container user can read `/etc/pihole/pihole-FTL.db`.
- The repository overview and Docker Hub description are updated automatically on release tags with the latest Dockle/Trivy scan summaries.
- Contributing guide: `CONTRIBUTING.md`.
