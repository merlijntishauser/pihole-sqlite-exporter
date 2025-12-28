# pihole-sqlite-exporter


## Why this exists
- Avoids API calls, auth, TLS, and timeout issues.
- Uses read-only SQLite access to keep the exporter lightweight and safe.
- Works well in constrained environments (NAS, containers, or edge devices).

## How it works
- Connects read-only to Pi-hole's SQLite databases.
- Computes daily counters, top lists, and request-rate metrics.
- Exposes Prometheus metrics on `/metrics` via a tiny HTTP server.

## Image and build choices
- Uses a hardened runtime base (`dhi.io/python:3-alpine3.22`) with a minimal footprint,
  non-root default user, and a simple healthcheck.

## Repository Overview
- **Docker image:** hardened minimal runtime (non-root by default) with an HTTP healthcheck on `/metrics`.
- **Docker Hub:** https://hub.docker.com/r/merlijntishauser/pihole-sqlite-exporter
- **GitHub:** https://github.com/merlijntishauser/pihole-sqlite-exporter
