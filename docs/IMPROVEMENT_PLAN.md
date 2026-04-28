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

**Why**: `code_health.py` is 1,905 lines — the largest file in the project. It contains all 40 rules, the config system, and the runner. This makes it hard to find a specific rule, hard to test one rule in isolation, and hard for two people to work on rules simultaneously.

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

## ? P3 — Future Backlog

### 12. Parallel File Parsing

**Why**: Currently, files are parsed sequentially. For a 10K-file repo, this takes minutes. Using `asyncio.gather` or a process pool could cut this by 4-8x.

**Effort**: 3-4 hours

### 13. PostgreSQL Full-Text Search

**Why**: The current `ILIKE` search doesn't rank results or handle stemming. `tsvector` gives proper full-text search with ranking.

**Effort**: 4-6 hours

### 14. Prometheus Metrics Endpoint

**Why**: SaaS needs observability — request latency, error rates, ingestion times.

**Effort**: 1-2 hours

### 15. Webhook Retry with Exponential Backoff

**Why**: If ingestion fails after a webhook push, there's no retry. Adding dead-letter queue with retries makes it reliable.

**Effort**: 2-3 hours

### 16. Diff-Based Incremental Ingestion

**Why**: Currently, every ingestion re-parses the entire repo. If only 3 files changed, re-parsing 10K files is wasteful. Compare file hashes and only re-parse changed files.

**Effort**: 6-8 hours

---

## Execution Timeline

### ~~Week 1 — Foundation~~ DONE
- [x] P0.1: Alembic migrations
- [x] P0.2: Fix LLM prompts
- [x] P0.3: Ingestion progress
- [x] P1.7: Resolve TODOs

### ~~Week 2 — Reliability~~ DONE
- [x] P1.4: Split code_health.py
- [ ] P1.5: ARQ job queue (deferred — single-process is fine for now)
- [ ] P1.6: Redis rate limiter (deferred — single-process is fine for now)

### ~~Week 3 — Polish~~ DONE
- [x] P2.8: Extract long functions
- [x] P2.9: OpenAPI descriptions
- [x] P2.10: API key auth
- [x] P2.11: JSON logging

### Week 4+ — Future (P3)
- [ ] P3.12: Parallel file parsing
- [ ] P3.13: PostgreSQL full-text search
- [ ] P3.14: Prometheus metrics
- [ ] P3.15: Webhook retry with backoff
- [ ] P3.16: Diff-based incremental ingestion

**Status: 12 of 14 items completed. 2 items deferred (require Redis).**

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
