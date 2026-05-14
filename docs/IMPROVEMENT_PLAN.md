# Improvement Plan

This document lists every concrete improvement identified during a full project audit, prioritized by impact for a solo-developer SaaS scenario. Each item includes the **why**, the **what**, estimated effort, and the files involved.

---

## Priority Legend

| Priority | Meaning | When to do it |
|----------|---------|---------------|
| ?? P0 | **Must-have** before SaaS launch | This week |
| ?? P1 | **Should-have** for reliability | Before first paying user |
| ?? P2 | **Nice-to-have** for polish | When time permits |
| ? P3 | **Future** — backlog | Next quarter |

---

## ?? P0 — Must-Have for SaaS Launch

### 1. Alembic Database Migrations

**Why**: The system uses `Base.metadata.create_all()` on startup. This works for dev but is **dangerous in production** — if you change a model (add a column, rename a table), `create_all` won't alter existing tables. You'll lose data or get crashes.

**What to do**:
1. Run `alembic init alembic` in `backend/`
2. Configure `alembic/env.py` to use the async engine
3. Run `alembic revision --autogenerate -m "initial"` to capture current schema
4. Replace `create_all` in `main.py` with `alembic upgrade head`
5. Every future model change = `alembic revision --autogenerate` + `alembic upgrade head`

**Files**: `backend/alembic/`, `backend/alembic.ini`, `app/main.py`
**Effort**: 2-3 hours
**Risk if skipped**: Any schema change in production = data loss or downtime

---

### ~~2. Fix LLM Prompts~~ DONE

**What was done**: All 5 occurrences of "legacy C# codebase" in `answer_builder.py` replaced with "the codebase". LLM now gives language-appropriate answers.

**Files changed**: `app/reasoning/answer_builder.py`

---

### ~~3. Ingestion Progress Reporting~~ DONE

**What was done**:
- Added `progress_percent` (int) and `progress_message` (str) columns to `RepoSnapshot`
- `tasks.py` now reports progress at 7 stages: 0% start, 5% cloning, 15% scanning, 25% scanned N files, 50% parsed N symbols, 65% graph persisted, 90% summaries generated, 100% complete
- On failure, `progress_message` shows the error
- Both `GET /status` and `GET /snapshots/{id}` return progress fields
- 7 new tests covering all states

**Files changed**: `app/storage/models.py`, `app/storage/schemas.py`, `app/api/repos.py`, `app/core/tasks.py`, `tests/test_progress.py`

---

## ?? P1 — Should-Have for Reliability

### 4. Split `code_health.py` into Separate Rule Modules

**Why**: `code_health.py` is 1,905 lines — the largest file in the project. It contains all 66 rules, the config system, and the runner. This makes it hard to find a specific rule, hard to test one rule in isolation, and hard for two people to work on rules simultaneously.

**What to do**:
1. Create `app/analysis/health_rules/` directory
2. Move each category into its own file:
   - `solid_rules.py` (5 rules)
   - `clean_code_rules.py` (8 rules)
   - `complexity_rules.py` (5 rules)
   - `coupling_rules.py` (4 rules)
   - `design_smell_rules.py` (6 rules)
   - `naming_rules.py` (4 rules)
   - `security_rules.py` (4 rules)
   - `architecture_rules.py` (4 rules)
3. Keep `code_health.py` as the orchestrator that imports and runs all rules
4. Move tests accordingly

**Files**: `app/analysis/code_health.py` ? `app/analysis/health_rules/*.py`
**Effort**: 3-4 hours
**Risk if skipped**: Maintainability degrades as rules grow

---

### 5. External Job Queue for Ingestion (DEFERRED)

> **Deferred reason**: Requires Redis at runtime and ARQ dependency. The current `BackgroundTasks` approach works correctly for single-process SaaS. Implement when scaling to multiple API replicas.

**What to do when needed**:
1. Add `arq` (lightweight Redis-based job queue) as a dependency
2. Create `app/workers/ingestion_worker.py` that picks up jobs from Redis
3. Change `POST /ingest` to enqueue a job instead of `background.add_task()`
4. Run the worker as a separate process: `arq app.workers.WorkerSettings`

**Files**: `app/workers/`, `app/api/repos.py`, `pyproject.toml`
**Effort**: 4-6 hours
**Risk if skipped**: Ingestion is unreliable under load; no retry on failure

---

### 6. Per-User Rate Limiting (DEFERRED)

> **Deferred reason**: The in-memory rate limiter works correctly for single-process deployment. Implement Redis-backed limiter when running multiple API replicas.

**What to do when needed**:
1. Add a Redis-backed sliding window rate limiter
2. Key by `user_id` (from JWT) if authenticated, fall back to IP
3. Make limits configurable per plan (free: 10 req/min, pro: 100 req/min)

**Files**: `app/core/middleware.py`, `app/core/config.py`
**Effort**: 2-3 hours
**Risk if skipped**: Rate limits don't work correctly with multiple replicas

---

### ~~7. Resolve the 3 TODO Comments~~ DONE

**What was done**:
- `embedder.py:91` -- Replaced misleading TODO with accurate comment (hash fallback is intentional)
- `summarizer.py:108` -- Replaced misleading TODO with accurate comment (deterministic facts is intentional)
- `code_health.py:285` -- Was already correct (suggestion text to users, not a code TODO)

**Files changed**: `app/indexing/embedder.py`, `app/indexing/summarizer.py`

---

## ~~P2 — Nice-to-Have for Polish~~ (COMPLETED)

> All four P2 items were implemented and tested.

### ~~8. Extract Long Functions~~ DONE

**What was done**:
- `portable.py`: Rewrote from 735 lines to 321 lines. Extracted 6 export helpers (`_export_files`, `_export_symbols`, `_export_edges`, `_export_summaries`, `_export_docs`, `_export_evaluations`), 6 import helpers (`_import_files`, etc.), and `_validate_and_parse_upload`.
- `search.py`: Added 3 search helpers (`_search_symbols`, `_search_summaries`, `_search_docs`).
- All 25 portable tests and 35 search tests pass unchanged.

**Files changed**: `app/api/portable.py`, `app/api/search.py`

---

### ~~9. OpenAPI Description Polish~~ DONE

**What was done**:
- Added `openapi_tags` metadata with descriptions for all 14 route groups
- Swagger UI now shows organized, described tag groups

**Files changed**: `app/main.py`

---

### ~~10. API Key Authentication (for CI/CD)~~ DONE

**What was done**:
- Added `ApiKey` model (`id`, `user_id`, `name`, `key_hash`, `prefix`, `is_active`, `created_at`)
- 3 new endpoints: `POST /auth/api-keys` (create), `GET /auth/api-keys` (list), `DELETE /auth/api-keys/{id}` (revoke)
- Keys are SHA-256 hashed in DB; raw key returned only at creation
- `get_current_user` now checks `X-API-Key` header before JWT fallback
- Key format: `eidos_<random>` with stored prefix for identification
- 13 new tests covering create, list, revoke, hash verification, auth flow

**Files changed**: `app/storage/models.py`, `app/api/auth.py`, `app/auth/dependencies.py`, `tests/test_api_keys.py`

---

### ~~11. Structured Logging with JSON Output~~ DONE

**What was done**:
- Added `python-json-logger>=3.0` dependency
- `_configure_logging()` in `main.py`: JSON format in `client` edition, text in `internal`
- JSON logs include `timestamp`, `level`, `name`, `message` fields
- Graceful fallback to text if `python-json-logger` not installed
- 3 new tests verifying format, fields, and fallback behavior

**Files changed**: `app/main.py`, `pyproject.toml`, `tests/test_logging.py`

---

## ~~P3 — Future Backlog~~ (COMPLETED)

> All 5 P3 items were implemented and tested with 56 new tests.

### ~~12. Parallel File Parsing~~ DONE

**What was done**:
- `pipeline.py`: Added `ProcessPoolExecutor`-based parallel parsing for repos with >20 files
- Sequential fallback for small repos and single-worker mode
- `_parse_single_file` runs in subprocess for isolation
- Worker count: `min(EIDOS_PARSE_WORKERS or cpu_count, 8)`
- 15 new tests covering sequential, parallel, single-file parsing, edge cases

**Files changed**: `app/analysis/pipeline.py`, `tests/test_parallel_parsing.py`

---

### ~~13. PostgreSQL Full-Text Search~~ DONE

**What was done**:
- New `/fulltext` endpoint using `tsvector`/`ts_rank` on PostgreSQL
- ILIKE fallback for SQLite (tests) and other databases
- `_is_postgresql` auto-detection from engine URL
- `plainto_tsquery` for safe user input parsing
- 10 new tests covering endpoint, fallback, detection, result structure

**Files changed**: `app/api/search.py`, `tests/test_fulltext_search.py`

---

### ~~14. Prometheus Metrics Endpoint~~ DONE

**What was done**:
- New `GET /metrics` endpoint returning Prometheus text exposition format
- `MetricsMiddleware` records request count + duration per method/path/status
- `record_ingestion()` counter for completed/failed ingestions
- Path normalization collapses dynamic IDs for metric grouping
- No external dependency (generates text format directly)
- 12 new tests covering endpoint, format, counters, path normalization

**Files changed**: `app/api/metrics.py`, `app/main.py`, `app/core/tasks.py`, `tests/test_prometheus.py`

---

### ~~15. Webhook Retry with Exponential Backoff~~ DONE

**What was done**:
- New `retry_with_backoff()` utility with configurable retries, delay, backoff, max cap
- Webhooks now retry ingestion 3 times with exponential backoff on failure
- Supports custom retryable exception types
- 11 new tests covering success, retry, exhaustion, delay, non-retryable exceptions, kwargs

**Files changed**: `app/core/retry.py`, `app/api/webhooks.py`, `tests/test_retry.py`

---

### ~~16. Diff-Based Incremental Ingestion~~ DONE

**What was done**:
- New `compute_changed_files()`: compares file hashes against previous snapshot
- New `copy_unchanged_symbols()`: copies symbols/edges from unchanged files
- `tasks.py` now uses incremental parsing by default
- First snapshot: full parse. Subsequent: only changed/new files re-parsed
- 9 new tests covering first snapshot, unchanged, changed, new files, copy behavior

**Files changed**: `app/core/incremental.py`, `app/core/tasks.py`, `tests/test_incremental.py`

---

## Execution Timeline

### ~~Week 1 - Foundation~~ DONE
- [x] P0.1: Alembic migrations
- [x] P0.2: Fix LLM prompts
- [x] P0.3: Ingestion progress
- [x] P1.7: Resolve TODOs

### ~~Week 2 - Reliability~~ DONE
- [x] P1.4: Split code_health.py
- [ ] P1.5: ARQ job queue (deferred - single-process is fine for now)
- [ ] P1.6: Redis rate limiter (deferred - single-process is fine for now)

### ~~Week 3 - Polish~~ DONE
- [x] P2.8: Extract long functions
- [x] P2.9: OpenAPI descriptions
- [x] P2.10: API key auth
- [x] P2.11: JSON logging

### ~~Week 4 - Performance~~ DONE
- [x] P3.12: Parallel file parsing
- [x] P3.13: PostgreSQL full-text search
- [x] P3.14: Prometheus metrics
- [x] P3.15: Webhook retry with backoff
- [x] P3.16: Diff-based incremental ingestion

**Status: 15 of 16 items completed. 2 items deferred (require Redis).**

---

## Additional Improvements (Post-Plan)

### 17. In-Memory Database Mode

**What was done**:
- Added `EIDOS_IN_MEMORY_DB=true` flag to `Settings` in `app/core/config.py`
- When set, `database.py` overrides `database_url` to `sqlite+aiosqlite://` (in-memory)
- `main.py` lifespan detects both `in_memory_db` flag and `sqlite://` URL for `create_all`
- Enables running the full backend without any external database (demos, testing, CI)

**Files changed**: `app/core/config.py`, `app/storage/database.py`, `app/main.py`

---

### 18. Comprehensive E2E Integration Test

**What was done**:
- New `tests/test_e2e_full.py` with 54 tests covering all major endpoint groups
- Uses in-memory SQLite via ASGI transport (no server needed)
- Seeds real data: 13 symbols, 7 edges, 4 files, 3 summaries
- Tests: health (4), repos (2), snapshots (2), files (1), symbols (4), edges (1), graph (1), summaries (2), search (2), docgen (10), diagrams (1), analysis (11), exports (5), portable (1), tags (3), quality gates (2), diff (1), errors (3)

**Files changed**: `tests/test_e2e_full.py`

---

## How to Use This Plan

1. Pick the highest-priority item you haven't done
2. Read the "What to do" section
3. Create a branch: `git checkout -b improvement/alembic-migrations`
4. Implement the change
5. Run the full check suite: `ruff check app/ tests/ && mypy app/ && pytest tests/`
6. Update the relevant docs
7. Merge and move to the next item

Every improvement is **independent** — you can do them in any order within a priority tier. The P0 items should be done first because they affect data safety and user experience.
