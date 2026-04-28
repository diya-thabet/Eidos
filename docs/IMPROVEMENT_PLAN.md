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

### 5. External Job Queue for Ingestion

**Why**: `BackgroundTasks` runs ingestion inside the API process. If the process crashes mid-ingestion, the job is lost. If you run multiple API replicas, only the one that received the request does the work — no load distribution.

**What to do**:
1. Add `arq` (lightweight Redis-based job queue) as a dependency
2. Create `app/workers/ingestion_worker.py` that picks up jobs from Redis
3. Change `POST /ingest` to enqueue a job instead of `background.add_task()`
4. Run the worker as a separate process: `arq app.workers.WorkerSettings`

**Files**: `app/workers/`, `app/api/repos.py`, `pyproject.toml`
**Effort**: 4-6 hours
**Risk if skipped**: Ingestion is unreliable under load; no retry on failure

---

### 6. Per-User Rate Limiting (Replace In-Memory)

**Why**: The current rate limiter uses an in-memory `_TokenBucket` per IP. If you run 2 API replicas, each has its own bucket — a user gets 2x the rate. Also, IP-based limiting doesn't work when users are behind a shared proxy.

**What to do**:
1. Add a Redis-backed sliding window rate limiter
2. Key by `user_id` (from JWT) if authenticated, fall back to IP
3. Make limits configurable per plan (free: 10 req/min, pro: 100 req/min)

**Files**: `app/core/middleware.py`, `app/core/config.py`
**Effort**: 2-3 hours
**Risk if skipped**: Rate limits don't work correctly with multiple replicas

---

### 7. Resolve the 3 TODO Comments

**Why**: These represent known incomplete features that someone flagged during development.

| Location | TODO | What to do |
|----------|------|------------|
| `code_health.py:285` | TODO in rule logic | Review and complete the rule or remove it |
| `embedder.py:91` | TODO for embedding batch size | Set a proper batch size based on model limits |
| `summarizer.py:108` | TODO for LLM prompt | Finalize the summarizer prompt |

**Effort**: 1 hour total
**Risk if skipped**: Low, but creates confusion for future developers

---

## ?? P2 — Nice-to-Have for Polish

### 8. Extract Long Functions

**Why**: 45 functions exceed 60 lines. Long functions are harder to understand, test, and debug. The worst offenders are in `portable.py` (3 functions >100 lines), `search.py` (3 functions >90 lines), and `code_health.py` (3 functions >67 lines).

**What to do for each long function**:
1. Identify logical sections within the function
2. Extract each section into a named helper function
3. The original function becomes a short orchestrator

**Top 10 targets**:

| Function | File | Lines | Action |
|----------|------|-------|--------|
| `_build_export_payload` | `portable.py` | 216 | Split into `_export_symbols()`, `_export_edges()`, etc. |
| `_restore_snapshot` | `portable.py` | 190 | Split into `_import_symbols()`, `_import_edges()`, etc. |
| `import_portable` | `portable.py` | 144 | Extract validation into `_validate_eidos_file()` |
| `parse_unified_diff` | `diff_parser.py` | 135 | Extract hunk parsing into helper |
| `search` | `search.py` | 135 | Already uses 3 separate query blocks — extract each |
| `review_diff` | `reviewer.py` | 134 | Extract finding aggregation |
| `_build_section` | `generator.py` | 131 | Extract per-section-type builders |
| `run_indexing` | `indexer.py` | 126 | Extract embedding batch loop |
| `export_snapshot` | `search.py` | 104 | Extract per-entity serialization |
| `_build_deterministic_answer` | `answer_builder.py` | 97 | Extract evidence building |

**Effort**: 4-6 hours for all 10
**Risk if skipped**: Low — code works fine, just harder to maintain

---

### 9. OpenAPI Description Polish

**Why**: The auto-generated Swagger UI at `/docs` is the first thing a user sees. Adding `description=` to every parameter makes it professional and self-documenting.

**What to do**:
1. Add `description=` to every `Query()` parameter
2. Add `summary=` and `description=` to every route decorator
3. Add `tags_metadata` to the FastAPI app for tag descriptions

**Files**: All `app/api/*.py` files
**Effort**: 1-2 hours
**Risk if skipped**: Users have to guess what parameters do

---

### 10. API Key Authentication (for CI/CD)

**Why**: OAuth is great for browser users but terrible for CI/CD pipelines. A GitHub Action can't do an OAuth dance. API keys let machines authenticate with a simple header.

**What to do**:
1. Add `ApiKey` model in `storage/models.py`
2. Add `POST /auth/api-keys` to create a key (returns once, hashed in DB)
3. Add `X-API-Key` header support in `auth/dependencies.py`
4. Check API key before OAuth in `get_current_user()`

**Files**: `app/storage/models.py`, `app/auth/dependencies.py`, `app/api/auth.py`
**Effort**: 2-3 hours
**Risk if skipped**: Can't use Eidos from CI/CD pipelines

---

### 11. Structured Logging with JSON Output

**Why**: The current logging uses Python's default text format. In production (Docker/K8s), structured JSON logs are parseable by log aggregation tools (Datadog, Loki, CloudWatch).

**What to do**:
1. Add `structlog` or `python-json-logger` as a dependency
2. Configure in `main.py` to output JSON in production mode
3. Keep text format for `EIDOS_EDITION=internal`

**Files**: `app/main.py`, `pyproject.toml`
**Effort**: 1 hour
**Risk if skipped**: Hard to search logs in production

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

For a solo developer working part-time on improvements:

### Week 1 — Foundation
- [ ] P0.1: Alembic migrations (2-3h)
- [ ] P0.2: Fix LLM prompts (15min)
- [ ] P0.3: Ingestion progress (1-2h)
- [ ] P1.7: Resolve TODOs (1h)

### Week 2 — Reliability
- [ ] P1.5: ARQ job queue (4-6h)
- [ ] P1.6: Redis rate limiter (2-3h)

### Week 3 — Code Quality
- [ ] P1.4: Split code_health.py (3-4h)
- [ ] P2.8: Extract long functions (4-6h)

### Week 4 — Polish
- [ ] P2.9: OpenAPI descriptions (1-2h)
- [ ] P2.10: API key auth (2-3h)
- [ ] P2.11: JSON logging (1h)

**Total estimated effort: ~25-35 hours over 4 weeks**

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
