# pihole-sqlite-exporter

Prometheus exporter that reads Pi-hole metrics from **pihole-FTL.db** (and optionally **gravity.db**) without using the Pi-hole API.

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
```bash
cd docker
docker compose -f docker-compose.example.yml up -d --build
```

## Test
```bash
wget -qO- http://127.0.0.1:9617/metrics
```

## Lint
```bash
ruff check .
```

## Format
```bash
ruff format .
```

## Notes
- Mount /etc/pihole read-only.
- domains_being_blocked prefers gravity.db (gravity table). If missing, it falls back to domain_by_id (less precise).
- Disclaimer: AI assistance was used while writing parts of the codebase.
