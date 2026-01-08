# Changelog

## 0.3.6 (unreleased)
- Consolidated exporter tests into a single module.
- Refined changelog wording and ensured dated entries.

## 0.3.5 (2026-01-08)
- Added Dockle FATAL gating with detailed scan output and a scan-only workflow option.
- Fixed Dockle CIS-DI-0010 by moving commit info to an OCI label and suppressing the settings.py false positive.
- Added CodeQL advanced workflow v4, tightened workflow permissions, and improved CI visibility.
- Refined Pyright typing for fetch_scalar overloads.
- Added Pyright type checking and cyclomatic complexity linting; run CI tooling from `.venv` and added `make typecheck`.
- Refactored HTTP handler flow, exporter startup logging, and conditional style; updated AGENTS.md rules.
- Consolidated scraper tests and added module-focused tests for metrics, metrics_state, and queries.

## 0.3.4 (2026-01-06)
- Added local install and testrunners to Makefile.
- Bumped ruff from 0.6.9 to 0.14.10.
- Bumped pytest from 8.3.3 to 9.0.2.
- Bumped pytest-cov from 5.0.0 to 7.0.0.
- Updated SECURITY.md to remove supported versions.
- Bumped prometheus-client from 0.21.1 to 0.23.1.
- Bumped pre-commit from 3.8.0 to 4.5.1.
- Set package ecosystem to pip in dependabot config.

## 0.3.3 (2026-01-01)
- Added debug logging for healthz/readyz requests.
- Added cached lifetime destination queries with TTL config.
- Documented FTL DB interval note in docs.

## 0.3.2 (2026-01-01)
- Added tests for health/ready.
- Updated documentation.
- Fixed exporter main tests for delayed background scrape.

## 0.3.1 (2026-01-01)
- Reduced log noise and avoided duplicate scrape errors.
- Added healthz/readyz endpoints and used them for Docker healthcheck.

## 0.3.0 (2026-01-01)
- Refactored scraping to cached snapshots and reduced request rate.
- Made repushing a tag for history rewrites easier.
- Simplified versioning and Makefile.

## 0.2.18 (2025-12-30)
- Fixed a Makefile error.
- Simplified versioning and Makefile.

## 0.2.17 (2025-12-28)
- Improved logging.
- Refactored settings usage and extracted constants.
- Introduced settings class.
- Added tests for db.py.

## 0.2.16 (2025-12-28)
- No notable changes recorded.

## 0.2.15 (2025-12-28)
- Improved logging.
- Updated contributing.
- Added a lightweight scrape duration gauge.
- Grouped globals in metrics.py.
- Added explicit handling for queries tables missing rowid/id.
- Split huge function into smaller named helpers.
- Extracted SQL queries.
- Extracted fixtures and updated todo.
- Introduced state object and improved naming.
- Refactored tests into smaller modules.

## 0.2.14 (2025-12-28)
- Split huge function into smaller named helpers.
- Extracted SQL queries.
- Extracted fixtures and updated todo.
- Introduced state object and improved naming.
- Refactored tests into smaller modules.

## 0.2.13 (2025-12-28)
- Improved query for actual qps.

## 0.2.12 (2025-12-28)
- Made qps more accurate.

## 0.2.11 (2025-12-28)
- Fixed qps counters.

## 0.2.10 (2025-12-28)
- Added version info to logging.
- Added threaded scraping in background.

## 0.2.9 (2025-12-28)
- Added more debug logic.

## 0.2.8 (2025-12-28)
- Restored v0.2.3 exporter logic.

## 0.2.7 (2025-12-28)
- No notable changes recorded.

## 0.2.6 (2025-12-28)
- Installed deps into app path.
- Fixed PYTHONPATH in Docker image.

## 0.2.5 (2025-12-28)
- Restored docker release workflow.
- Changed request behavior to report for timeframe since last request.
- Refactored scrape window to be less bursty.
- Added timers for verbose mode of scraping.
- Added contributing guidelines.
- Refactored structure.
- Added types for scraper helper methods.
- Extracted SQL strings into constants.
- Split single script into modules.
- Added more context to docker hub description.
- Added script to update repo description on Docker Hub.

## 0.2.4 (2025-12-27)
- Added Trivy and Dockle to GitHub Actions.
- Added Docker Hub repo and build steps.

## 0.2.3 (2025-12-26)
- No notable changes recorded.

## 0.2.2 (2025-12-26)
- Updated README and Makefile for multi-arch build.
- Added multi-arch builds.

## 0.2.1 (2025-12-26)
- Added login step for dhi.io.

## 0.2.0 (2025-12-26)
- Added docker tagging.
- Added versioning.

## 0.1.1 (2025-12-26)
- No notable changes recorded.

## 0.1.0 (2025-12-26)
- Added DHI.io as base image.
- Extended pre-commit hook to include formatting.
- Added pre-commit hook and fixed linter warnings.
- Added more tests and coverage tool.
- Added GitHub Actions.
- Added Ruff as linter and formatter.
- Refactored test structure.
- Initial commit.
