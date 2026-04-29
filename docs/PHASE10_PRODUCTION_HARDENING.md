# Phase 10: Production Hardening (Middleware, Pagination, Observability)

This document describes the production-readiness improvements applied
to the Eidos backend in Phase 10.

---

## What Changed

### 1. CORS Middleware

The API now includes Starlette's `CORSMiddleware` so that the frontend
(or any browser client) can communicate with the backend without
cross-origin errors.

**Configuration** (via environment variables or `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `EIDOS_CORS_ORIGINS` | `["*"]` | Allowed origins (set to specific domains in production) |

CORS is always enabled. The `X-Request-ID` header is exposed to
clients via `expose_headers`.

---

### 2. Request ID Middleware

Every request now gets a unique `X-Request-ID` header:

- If the client sends `X-Request-ID`, it is preserved (useful for tracing).
- Otherwise a new UUID4 hex is generated.
- The ID is available via `request.state.request_id` and a `ContextVar`
  (`app.core.middleware.request_id_ctx`) for use in logging and downstream code.
- The response always includes `X-Request-ID`.

---

### 3. Access Log Middleware

Every request is logged with structured fields:

```
request_id, method, path, status, duration_ms, client
```

This enables filtering and alerting in any log aggregation system
(ELK, Grafana Loki, CloudWatch, etc.).

---

### 4. Global Exception Handler

Unhandled exceptions are caught and return a safe JSON response:

```json
{
  "detail": "Internal server error",
  "request_id": "abc123..."
}
```

- **No stack traces** are ever leaked to clients.
- The full traceback is logged server-side with the request ID for correlation.

---

### 5. Rate Limiting

An in-memory token-bucket rate limiter is applied per client IP.

**Configuration**:

| Variable | Default | Description |
|----------|---------|-------------|
| `EIDOS_RATE_LIMIT_ENABLED` | `true` | Enable/disable rate limiting |
| `EIDOS_RATE_LIMIT_PER_SECOND` | `2.0` | Sustained request rate |
| `EIDOS_RATE_LIMIT_BURST` | `120` | Maximum burst size |

**Bypassed paths**: `/health`, `/version`, `/docs`, `/openapi.json`, `/redoc`

When the limit is exceeded, the API returns `429 Too Many Requests`.

---

### 6. Deep Healthcheck

A new endpoint `GET /health/ready` performs connectivity checks:

| Check | What it does |
|-------|-------------|
| `database` | Executes `SELECT 1` against the configured database |

Returns `200` with `{"status": "ready"}` if all checks pass, or
`503` with `{"status": "degraded", "checks": {...}}` if any fail.

The existing `GET /health` remains as a shallow liveness probe.

---

### 7. Paginated API Responses

All list endpoints now return a `PaginatedResponse` envelope:

```json
{
  "items": [...],
  "total": 42,
  "limit": 100,
  "offset": 0,
  "has_more": false
}
```

**Affected endpoints**:

| Endpoint | Previous response | New response |
|----------|------------------|--------------|
| `GET /repos/{id}/snapshots/{sid}/symbols` | `[SymbolOut, ...]` | `PaginatedResponse` |
| `GET /repos/{id}/snapshots/{sid}/edges` | `[EdgeOut, ...]` | `PaginatedResponse` |
| `GET /repos/{id}/snapshots/{sid}/summaries` | `[SummaryOut, ...]` | `PaginatedResponse` |

Query parameters `limit` (1-1000, default 100) and `offset` (>= 0)
are supported on all list endpoints. The `total` field returns the
count before pagination, enabling frontend page controls.

---

### 8. Full-Text Search API

`GET /repos/{id}/snapshots/{sid}/search?q=<query>`

Searches across three entity types simultaneously:

| Entity | Fields searched |
|--------|----------------|
| **Symbols** | `name`, `fq_name`, `file_path`, `namespace` |
| **Summaries** | `scope_id`, `summary_json` (content) |
| **Documents** | `title`, `markdown`, `scope_id` |

Features:
- Relevance scoring (exact match 10, partial 5, namespace 1)
- Filter by `entity_type` (symbol, summary, doc)
- Paginated response with `PaginatedResponse` envelope
- Case-insensitive LIKE matching

---

### 9. Snapshot Comparison API

`GET /repos/{id}/snapshots/{sid}/diff/{other_sid}`

Compares two snapshots and returns symbol-level diffs:

```json
{
  "base_snapshot_id": "snap-v1",
  "head_snapshot_id": "snap-v2",
  "added": [{"fq_name": "MyApp.NewClass", "kind": "class", ...}],
  "removed": [{"fq_name": "MyApp.OldClass", "kind": "class", ...}],
  "modified": [{"fq_name": "MyApp.Service", "kind": "class", ...}],
  "summary": {"added": 3, "removed": 1, "modified": 2, "unchanged": 45}
}
```

A symbol is **modified** if its signature, line range, or file path changed.

---

### 10. Export API

`GET /repos/{id}/snapshots/{sid}/export`

Exports the complete analysis for a snapshot in a single JSON payload:
- All symbols (with full metadata)
- All edges (call graph)
- All summaries (parsed JSON)
- All generated documents
- Metadata (commit SHA, counts)

Useful for CI/CD pipelines, offline analysis, and third-party integrations.

---

### 11. Webhook Receivers

Auto-trigger ingestion when code is pushed to a registered repository.

| Endpoint | Provider | Auth |
|----------|----------|------|
| `POST /webhooks/github` | GitHub | HMAC-SHA256 (`X-Hub-Signature-256`) |
| `POST /webhooks/gitlab` | GitLab | Shared token (`X-Gitlab-Token`) |
| `POST /webhooks/push` | Any | None (body-based matching) |

Behavior:
- Only processes push events to the repo's default branch
- Matches incoming URL against registered repos (normalizes `.git` suffix)
- Creates a new snapshot and triggers background ingestion
- Returns `{accepted: true, snapshot_id: "..."}` on success

**Configuration**: Set `EIDOS_WEBHOOK_SECRET` to enable signature verification.

---

### 12. Repo DELETE and PATCH Endpoints

Complete CRUD for repositories:

- `DELETE /repos/{id}` -- Deletes a repo and all associated data (snapshots, symbols, edges, summaries, reviews, docs) via cascade.
- `PATCH /repos/{id}` -- Partial update of `name`, `default_branch`, or `git_token`. Only provided fields are changed; others remain untouched.

---

## New Files

| File | Purpose |
|------|---------|
| `backend/app/core/middleware.py` | RequestID, AccessLog, ExceptionHandler, RateLimiter, CORS installer |
| `backend/app/api/search.py` | Search, Snapshot Diff, and Export endpoints |
| `backend/app/api/webhooks.py` | GitHub, GitLab, and generic webhook receivers |
| `backend/tests/test_middleware_and_infra.py` | 36 tests for middleware and pagination |
| `backend/tests/test_search_and_compare.py` | 35 tests for search, diff, and export |
| `backend/app/api/diagrams.py` | Mermaid class and module diagram generation |
| `backend/app/api/trends.py` | Health score trend tracking across snapshots |
| `backend/app/api/dependencies.py` | Shared verify_snapshot FastAPI dependency |
| `backend/tests/test_repo_crud.py` | 12 tests for DELETE/PATCH repo endpoints |
| `backend/tests/test_diagrams_and_trends.py` | 23 tests for diagrams and trends |

## Modified Files

| File | Changes |
|------|---------|
| `backend/app/main.py` | Added middleware, deep healthcheck, search/webhook routers |
| `backend/app/core/config.py` | Added CORS, rate limit, webhook settings |
| `backend/app/api/analysis.py` | `list_symbols` and `list_edges` return `PaginatedResponse` |
| `backend/app/api/indexing.py` | `list_summaries` returns `PaginatedResponse` |
| `backend/app/storage/schemas.py` | Added `PaginatedResponse` generic schema |
| `backend/tests/test_analysis_api.py` | Updated for paginated envelope |
| `backend/tests/test_indexing_api.py` | Updated for paginated envelope |
| `backend/tests/test_integration_e2e.py` | Updated for paginated envelope |
| `backend/tests/test_edge_cases.py` | Updated for paginated envelope |

## Test Coverage

89 new tests across 3 files:

| File | Tests | What's covered |
|------|-------|---------------|
| `test_middleware_and_infra.py` | 36 | Request ID, CORS, exception handler, rate limiting, healthcheck, pagination, token bucket, schema |
| `test_search_and_compare.py` | 35 | Search (symbols/summaries/docs, filtering, pagination, scoring), snapshot diff (add/remove/modify/reverse), export (all entities, metadata) |
| `test_webhooks.py` | 18 | GitHub/GitLab/generic webhooks, HMAC verification, branch matching, event filtering |

**Total test count: 2,119** (all phases combined) -- 100% pass rate

---

## Migration Notes

### Frontend Impact

If you consume `GET .../symbols`, `GET .../edges`, or `GET .../summaries`,
update your code to read `response.items` instead of treating the response
as a direct array. The `total` and `has_more` fields enable proper
pagination UI.

### Environment Variables

No new **required** variables. All new settings have sensible defaults.
For production, consider setting:

```env
EIDOS_CORS_ORIGINS=["https://your-frontend.com"]
EIDOS_RATE_LIMIT_PER_SECOND=5.0
EIDOS_RATE_LIMIT_BURST=200
EIDOS_WEBHOOK_SECRET=your-github-webhook-secret
```
