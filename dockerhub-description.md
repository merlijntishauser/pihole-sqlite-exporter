# pihole-sqlite-exporter

Prometheus exporter that reads Pi-hole metrics directly from `pihole-FTL.db` (and optionally `gravity.db`) without using the Pi-hole HTTP API.

## Why this exists
- Avoids API calls, auth, TLS, and timeout issues.
- Uses read-only SQLite access to keep the exporter lightweight and safe.
- Works well in constrained environments (NAS, containers, or edge devices).

## How it works
- Connects read-only to Pi-hole's SQLite databases.
- Computes daily counters, top lists, and request-rate metrics.
- Exposes Prometheus metrics on `/metrics` via a tiny HTTP server.

## Image and build choices
- Multi-arch images are published for `linux/amd64` and `linux/arm64` so the same tag runs on x86 servers, NAS devices, and ARM boards.
- Uses a hardened runtime base (`dhi.io/python:3-alpine3.22`) with a minimal footprint,
  non-root default user, and a simple healthcheck.
- Alpine keeps the image small and limits the attack surface; the hardened base emphasizes secure defaults and a trimmed runtime.

## Repository Overview
- **Docker image:** hardened minimal runtime (non-root by default) with an HTTP healthcheck on `/metrics`.
- **Docker Hub:** https://hub.docker.com/r/merlijntishauser/pihole-sqlite-exporter
- **GitHub:** https://github.com/merlijntishauser/pihole-sqlite-exporter
- **Scan summary (2025-12-28 11:46 UTC):** Dockle: INFO=2, PASS=15. Trivy: 0 vulnerabilities detected.
