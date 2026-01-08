# Changelog

## 0.3.5 (2026-01-10)
- Add Dockle FATAL gating with detailed scan output and a scan-only workflow option.
- Fix Dockle CIS-DI-0010 by moving commit info to an OCI label and suppressing the settings.py false positive.
- Add CodeQL advanced workflow v4, tighten workflow permissions, and improve CI visibility.
- Add Pyright type checking and cyclomatic complexity linting; run CI tooling from `.venv` and add a `make typecheck` target.
- Refactor HTTP handler flow, exporter startup logging, and conditional style; update AGENTS.md rules.
- Consolidate scraper tests and add module-focused tests for metrics, metrics_state, and queries.

## 0.3.4 (2026-01-06)
- added local install and testrunners to Makefile
- Bump ruff from 0.6.9 to 0.14.10
- Bump pytest from 8.3.3 to 9.0.2
- Bump pytest-cov from 5.0.0 to 7.0.0
- Update SECURITY.md to remove supported versions
- Bump prometheus-client from 0.21.1 to 0.23.1
- Bump pre-commit from 3.8.0 to 4.5.1
- Set package ecosystem to 'pip' in dependabot config

## 0.3.3 (2026-01-01)
- Add debug logging for healthz/readyz requests
- Add cached lifetime destination queries with TTL config
- document FTL DBinterval note in docs

## 0.3.2 (2026-01-01)
- added tests for health ready
- updated documentation
- Fix exporter main tests for delayed background scrape

## 0.3.1 (2026-01-01)
- Reduce log noise and avoid duplicate scrape errors
- Add healthz/readyz endpoints and use them for Docker healthcheck

## 0.3.0 (2026-01-01)
- Refactor scraping to cached snapshots; drop request rate
- make rewriting history with repushing a tag easier.
- fixed error in Makefile
- simplified versioning and Makefile
- renamed codex prompt to AGENTS.md, bumped version in __init__

## 0.2.18 (2025-12-30)
- fixed error in Makefile
- simplified versioning and Makefile
- renamed codex prompt to AGENTS.md, bumped version in __init__

## 0.2.17 (2025-12-28)
- improved logging
-  Refactor settings usage and extract constants
- introduced settings class
- updated todo list
- add test for db.py

## 0.2.16 (2025-12-28)
- made adding git commit more reliable
- updated prompt and todo

## 0.2.15 (2025-12-28)
- improved logging
- updated contributing
- added more tests
- updated todo list
- Add a lightweight scrape duration gauge
- grouped globals in metrics.py
- Add explicit handling for queries tables missing rowid/id
- split huge function in smaller named helpers
- extracted SQL queries
- updated todo
- extracted fixtures and updated todo
- introduced state object and improved naming
- refactored tests to smaller modules
- added todo
- updated readme

## 0.2.14 (2025-12-28)
- split huge function in smaller named helpers
- extracted SQL queries
- updated todo
- extracted fixtures and updated todo
- introduced state object and improved naming
- refactored tests to smaller modules
- added todo
- updated readme

## 0.2.13 (2025-12-28)
- fix qps
- improved query for actual qps

## 0.2.12 (2025-12-28)
- bum version to 0.2.11
- make qps more accurate
- fix for qps counters

## 0.2.11 (2025-12-28)
- fix for qps counters

## 0.2.10 (2025-12-28)
- added version info to logging
- added threaded scraping in background

## 0.2.9 (2025-12-28)
- added more debug logic

## 0.2.8 (2025-12-28)
- Restore v0.2.3 exporter logic
- simplified logic

## 0.2.7 (2025-12-28)
- No changes recorded.

## 0.2.6 (2025-12-28)
- Install deps into app path
- Fix PYTHONPATH in Docker image

## 0.2.5 (2025-12-28)
- Restore docker release workflow
- add description
- rollback breaking changes
- fix for workflow merging README.md
- changed behaviour on requests to report for timeframe since last request
- fix for workflow
- fixed workflow
- refactored scrape window to be less bursty
- added timers for verbose mode of scraping
- updated prompt
- added contributing guidelines
- refactored structure
- Refactor: add types for scraper helper methods
- Refactor: extract SQL strings into constants
- big refactoring to split single script into modules
- added more context to docker hub description
- added script to update repo description on docker hub

## 0.2.4 (2025-12-27)
- First public release


