# LLM Handoff Guide - Lessons Learned and Tips

This document is written for the next LLM (or human) who works on the Eidos codebase. It contains hard-won lessons, gotchas, patterns, and tricks that will save you hours of debugging.

---

## 1. Architecture Overview (Quick Mental Model)

```
FastAPI app (app/main.py)
  |
  +-- API routes (app/api/*.py) -- thin HTTP layer
  |     Each route calls a service function and returns a response
  |
  +-- Analysis engine (app/analysis/) -- tree-sitter parsers + graph builder
  |     Parses 9 languages into SymbolInfo + EdgeInfo
  |     code_health.py orchestrates 66 rules from health_rules/
  |
  +-- Indexing pipeline (app/indexing/) -- summaries + vector embeddings
  |
  +-- Reasoning engine (app/reasoning/) -- Q&A with graph + vector retrieval
  |
  +-- Review engine (app/reviews/) -- diff parser + heuristics
  |
  +-- Doc generator (app/docgen/) -- templates + markdown renderer
  |
  +-- Auth (app/auth/) -- JWT + OAuth + API keys
  |
  +-- Storage (app/storage/) -- SQLAlchemy models + Pydantic schemas
  |
  +-- Core (app/core/) -- config, ingestion, tasks, retry, incremental
```

---

## 2. Critical Gotchas

### 2.1 SQLite In-Memory Isolation in Tests

**Problem**: `sqlite+aiosqlite://` creates a separate database per connection. If test fixture A inserts data and fixture B opens a new session, B cannot see A's data.

**Solution**: The test conftest uses a single `test_engine` and `test_sessionmaker`. When seeding data in Phase 4 E2E tests, you MUST use `override_get_db()` (same session factory the API uses), NOT `test_sessionmaker()` directly. Both use the same engine but the connection pool routing matters.

**Pattern that works**:
```python
async for db in override_get_db():
    db.add(MyModel(...))
    await db.commit()
```

### 2.2 File Encoding (Windows cp1252 vs UTF-8)

**Problem**: When creating files with the `create_file` tool, certain characters (em-dashes, smart quotes, ellipses) get encoded as cp1252 bytes instead of UTF-8. This causes `ruff` to fail with "E902 stream did not contain valid UTF-8".

**Fix**: After creating any file, run this check:
```python
p = pathlib.Path('the_file.py')
b = p.read_bytes()
bad = [i for i in range(len(b)) if b[i] > 127]
if bad:
    b = b.replace(b'\x97', b'-')  # em-dash
    b = b.replace(b'\x93', b'"').replace(b'\x94', b'"')  # smart quotes
    b = b.replace(b'\x85', b'...')  # ellipsis
    p.write_bytes(b)
```

**Prevention**: Use plain ASCII in all Python files. Use `-` instead of em-dashes, `"` instead of smart quotes.

### 2.3 Trailing Slash Redirects

**Problem**: FastAPI routes defined as `@router.post("")` will 307 redirect `POST /repos/` to `POST /repos`. This breaks test clients.

**Solution**: In tests, always use the path WITHOUT trailing slash, or add `follow_redirects=True` to httpx calls.

### 2.4 PowerShell Multi-Line Python

**Problem**: `run_command_in_terminal` with multi-line Python code often fails because PowerShell interprets Python syntax as PS commands.

**Solution**: For anything beyond 3 lines, write a temporary `.py` script file, run it, then delete it. ALWAYS delete temp scripts after -- `_rewrite_health.py` got committed to CI and broke the pipeline.

### 2.5 Ruff Auto-Removes "Unused" Imports

**Problem**: Running `ruff check --fix` removes imports that appear unused but are actually needed later in the file (e.g., `Symbol` imported at top but used in an inline fixture).

**Solution**: Always verify imports are still present after `ruff --fix`. If ruff removes something you need, either:
- Use it explicitly at the top level, or
- Import it locally where used

---

## 3. API Response Shapes (Reference)

These are the actual response shapes -- NOT what you might guess:

| Endpoint | Method | Response Shape |
|----------|--------|---------------|
| `/repos` | POST | `{id, name, url, ...}` |
| `/repos/{id}/status` | GET | `{repo_id, status, snapshots: [...]}` |
| `/repos/{id}/snapshots/{sid}/symbols` | GET | `{items: [...], total, limit, offset, has_more}` |
| `/repos/{id}/snapshots/{sid}/edges` | GET | `{items: [...], total, limit, offset, has_more}` |
| `/repos/{id}/snapshots/{sid}/overview` | GET | `{snapshot_id, total_symbols, total_edges, total_modules, symbols_by_kind, entry_points, hotspots}` |
| `/repos/{id}/snapshots/{sid}/health` | **POST** | `{overall_score, findings: [...], ...}` |
| `/repos/{id}/snapshots/{sid}/search` | GET | `{items: [...], total, limit, offset, has_more}` |
| `/repos/{id}/snapshots/{sid}/diagram` | GET (with `?diagram_type=class|module`) | `{mermaid: "...", ...}` |
| `/repos/{id}/snapshots/{sid}/ask` | POST | `{question, question_type, answer_text, evidence, confidence, ...}` |
| `/repos/{id}/snapshots/{sid}/review` | POST | `{risk_score, risk_level, findings, ...}` |
| `/repos/{id}/snapshots/{sid}/docs` | POST | `{docs: [...], total_docs}` |
| `/repos/{id}/snapshots/{sid}/evaluate` | POST | `{overall_score, checks, ...}` |

**Key trap**: Health is POST (not GET). Diagram is singular `/diagram` with a query param (not `/diagrams/class`). There is NO `GET /repos/` list endpoint.

---

## 4. Testing Patterns

### Running Tests
```bash
cd backend
python -m ruff check alembic/ app/ tests/    # Lint (must pass)
python -m mypy app/ --ignore-missing-imports  # Type check (must pass)
python -m pytest tests/ -q --tb=short         # Full suite
python -m pytest tests/test_X.py -v -s        # Single file with output
```

### Test Database Pattern
Every test file that hits the API follows this pattern:
```python
app.dependency_overrides[get_db] = override_get_db

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    # seed data here if needed
    yield
    await drop_tables()

@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
```

### Why `run_ingestion` is always mocked
The `POST /repos/{id}/ingest` endpoint triggers `run_ingestion` as a background task that clones a repo from GitHub. In tests, we mock it to avoid network calls. When you need real parsing (like the E2E test), clone the repo in a fixture and parse offline.

---

## 5. Adding Features (Checklist)

1. Add the route in `app/api/your_module.py`
2. Add a Pydantic response model
3. Register the router in `app/main.py`
4. Write tests in `tests/test_your_feature.py`
5. Run: `ruff check`, `mypy`, `pytest`
6. Update docs: TESTING.md, PROJECT_STATUS.md, IMPROVEMENT_PLAN.md, SYSTEM_OVERVIEW.md

---

## 6. Health Rules Architecture

The 40 health rules live in `app/analysis/health_rules/` across 8 modules:
- `clean_code.py`, `solid.py`, `complexity.py`, `design.py`
- `naming.py`, `security.py`, `best_practices.py`, `documentation.py`

Each module exports a list of `HealthRule` objects. The orchestrator `code_health.py` collects them all and runs them against the code graph.

To add a new rule: add a function in the appropriate module, wrap it in `HealthRule(name, severity, check_fn)`, and add it to the module's `RULES` list. No registration needed -- the orchestrator auto-discovers.

---

## 7. Incremental Ingestion Flow

```
POST /repos/{id}/ingest
  |
  tasks.py: run_ingestion()
  |
  1. Clone repo
  2. Scan files (get hashes)
  3. compute_changed_files() -- compare hashes vs previous snapshot
  4. analyze_snapshot_files() -- parse ONLY changed files (parallel if >20)
  5. persist_graph() -- save new symbols/edges
  6. copy_unchanged_symbols() -- copy from previous snapshot
  7. run_indexing() -- generate summaries
  8. Done
```

---

## 8. Common Mistakes I Made (Learn From These)

1. **Leaving temp scripts in the repo** (`_rewrite_health.py`, `_strip_blanks.py`). CI runs ruff on everything and these fail. ALWAYS delete temp files.

2. **Assuming API response shapes without checking**. The symbols endpoint returns paginated `{items, total}`, NOT a raw list. Always check the actual Pydantic response model.

3. **Using `GET` for health check**. It's `POST` because it accepts an optional config body.

4. **Not adding `python-multipart` to pyproject.toml**. Any endpoint with `UploadFile` requires this package. It was installed locally (bundled with newer FastAPI) but CI had an older version.

5. **Double-spaced files from encoding fixes**. When re-encoding files, blank lines get doubled. Check line counts after any encoding fix.

6. **Not running `ruff check` on `alembic/` directory**. CI checks ALL Python files including alembic migrations.

---

## 9. Key File Locations

| What | Where |
|------|-------|
| FastAPI app creation + routes | `app/main.py` |
| All DB models | `app/storage/models.py` |
| Auth dependencies (get_current_user) | `app/auth/dependencies.py` |
| Config (env vars) | `app/core/config.py` |
| Ingestion pipeline | `app/core/tasks.py` |
| Code parsers | `app/analysis/*_parser.py` |
| Health rules | `app/analysis/health_rules/*.py` |
| Test DB setup | `tests/conftest.py` |
| CI workflow | `.github/workflows/ci.yml` |

---

## 10. Performance Notes

- **Parallel parsing** kicks in at >20 files, using `ProcessPoolExecutor` (max 8 workers)
- **Incremental ingestion** skips unchanged files (hash comparison)
- **Prometheus metrics** at `/metrics` -- no external dependency, generates text format directly
- **Retry with backoff** on webhook ingestion failures (3 attempts, exponential delay)
- SQLite for dev/test, PostgreSQL for production (fulltext search uses `tsvector` on PG, falls back to `ILIKE` on SQLite)

---

## 11. What the Real Repo Test Proved

The E2E test against `diya-thabet/Neon-Defenders` (Java game) showed:
- **23 classes** found: GameEngine, PlayerEntity, EnemyEntity, BulletEntity, WeaponDecorator, etc.
- **99 methods** found with signatures
- **10 inheritance edges**: PlayerEntity extends GameEntity, DoubleShotDecorator extends WeaponDecorator, etc.
- **450 call edges**: method-to-method calls across the codebase
- **Search works**: querying "Game" returns matching symbols
- **Health analysis works**: scores and findings generated
- **Diagrams work**: Mermaid class diagrams generated
- **Portable export/import**: full round-trip (export -> import -> verify identical data)
- **API keys**: full lifecycle (create -> use -> revoke)
- **Metrics**: Prometheus counters track all API calls

This proves Eidos works correctly on real-world Java code, not just test fixtures.

---

## 12. Multi-Language Validation Results

Every parser was validated against a real open-source GitHub repository:

| Language | Repo | Symbols | Edges | Health Score | Portable Round-Trip |
|----------|------|---------|-------|-------------|-------------------|
| **Java** | diya-thabet/Neon-Defenders | 123 | 461 | Pass | Pass |
| **Python** | pallets/markupsafe | 106 | 458 | Pass | Pass |
| **C#** | ardalis/GuardClauses | 750 | 2,969 | 77.5/100 | Pass |
| **TypeScript** | sindresorhus/p-map | 8 | 3 | Pass | Pass |
| **TSX** | pmndrs/zustand | 147 | 359 | Pass | Pass |
| **Go** | tmrts/go-patterns | 43 | 114 | Pass | Pass |
| **Rust** | dtolnay/thiserror | 472 | 1,347 | Pass | Pass |
| **C** | antirez/sds | 43 | 191 | Pass | Pass |
| **C++** | gabime/spdlog | 139 | 1,157 | Pass | Pass |

All 9 languages produce correct symbols, edges, health scores, search results,
diagrams, and portable export/import. Total: 177 E2E tests across 9 real repos.

---

## 13. Deep Language Validation (Challenging Repos)

A second round of testing used larger, harder repos to stress each parser:

| Language | Repo | Symbols | Edges | Health | Key Findings |
|----------|------|---------|-------|--------|-------------|
| **Python** | pallets/click | 1,086 | 5,550 | 77.4/100 | 91 classes, 296 methods, 61 inheritance edges, deep decorator chains |
| **C#** | ardalis/GuardClauses | 750 | 2,969 | 77.5/100 | Interfaces found, generic signatures parsed, extension methods |
| **Java** | iluwatar/java-design-patterns | 5,553 | 18,792 | varies | Factory/Builder/Singleton/Observer/Strategy classes found, deep inheritance |
| **TypeScript** | sindresorhus/ky | 48 | 75 | Pass | Async functions, generics, union types parsed |
| **TSX** | pacocoursey/cmdk | 119 | 251 | Pass | React components (PascalCase), hooks, JSX composition |
| **Go** | charmbracelet/bubbletea | 761 | 4,457 | 80.6/100 | Interfaces, struct embedding, method receivers detected |
| **Rust** | hyperium/http | 946 | 3,555 | 74.5/100 | Traits, impl blocks grouped by parent, struct/enum parsing |
| **C** | DaveGamble/cJSON | 1,026 | 4,354 | 78.9/100 | Structs, function pointers, 152-call test functions |
| **C++** | fmtlib/fmt | 1,172 | 10,084 | 70.8/100 | Templates, virtual methods, 33 inheritance edges, namespaces |

Total across deep validation: **38 tests, all passing.**

---

## 14. Cyclomatic & Cognitive Complexity (Phase 16)

Every function/method now has computed complexity metrics:
- **Cyclomatic complexity** (McCabe): counts decision points via tree-sitter AST
- **Cognitive complexity** (Sonar-style): penalizes nesting depth and recursion
- Works across all 9 languages
- 5 new health rules: CX004-CX008
- New endpoint: `GET /complexity` with per-function metrics, averages, and filtering
- 57 new tests covering all languages, health rules, API, and edge cases

## 15. Dependency File Parsing (Phase 17)

Every manifest file in a repo is now parsed during ingestion:
- **11 parsers**: requirements.txt, pyproject.toml, setup.cfg, package.json, pom.xml, build.gradle, go.mod, Cargo.toml, .csproj, vcpkg.json, CMakeLists.txt
- **7 ecosystems**: PyPI, npm, Maven, Crates, Go, NuGet, CMake/vcpkg
- **5 new health rules**: DEP001-DEP005 (unpinned, wide range, unused, duplicate, dev-in-production)
- **New DB model**: `Dependency` table with ecosystem, version, is_dev, is_pinned
- **New endpoint**: `GET /dependencies` with ecosystem summaries
- Cross-references import edges to detect unused dependencies (DEP003)
- 61 new tests covering all parsers, health rules, API, pipeline integration, and edge cases

## 16. Git Blame / Churn Analysis (Phase 18)

Every function/method now has git blame metadata:
- **Blame extraction**: `app/analysis/blame.py` uses GitPython to run `git blame` per file
- **4 new DB columns on Symbol**: `last_author`, `last_modified_at`, `author_count`, `commit_count`
- **Pipeline integration**: blame runs after persist_graph in `tasks.py`, non-fatal on failure
- **4 new health rules**: GB001 (hotspot = high churn + high CC), GB002 (stale code = old + no callers), GB003 (bus factor = 1 author across module), GB004 (recent churn > 10 commits)
- **2 new endpoints**: `GET /contributors` (per-author stats), `GET /hotspots` (risk = churn x complexity)
- 31 new tests using real temporary git repos with multiple authors/commits

## 17. Dead Code Detection (Phase 19)

Full graph reachability analysis:
- **BFS from entry points**: detects entry points (controllers, main, constructors, public classes, test functions), then BFS following call/contains/inherits edges (NOT import edges)
- **4 categories**: unreachable functions, unreachable classes, dead modules (zero reachable symbols), dead imports (imported but unreachable target)
- **4 new health rules**: DC001 (unreachable function), DC002 (unreachable class), DC003 (dead module), DC004 (dead import)
- **New endpoint**: `GET /dead-code` reconstructs CodeGraph from DB and runs full analysis
- Handles cycles, 1000+ node graphs, public/private visibility
- 29 new tests

## 18. Clone Detection (Phase 20)

AST structural fingerprinting for copy-paste detection:
- **Fingerprinting**: walks tree-sitter AST recording only node types (ignores identifiers/literals/comments), SHA-256 hash
- **Near-clone detection**: sliding window of statement-level hashes, Jaccard similarity >= 60%
- **Pipeline integration**: fingerprint computed alongside complexity in `_enrich_complexity`, stored as `_structural_fingerprint` on SymbolInfo
- **3 new health rules**: DUP001 (exact clone), DUP002 (near clone, API-only), DUP003 (clone cluster > 3 copies)
- **New endpoint**: `GET /clones` with exact groups and near-clone pairs
- Works across all 9 languages (same tree-sitter approach)
- 33 new tests: Python + Java real code clones, similarity math, pipeline enrichment

## 19. Module Coupling & Cohesion (Phase 21)

Robert C. Martin's package metrics computed per module:
- **Afferent coupling (Ca)**: modules that depend on this one
- **Efferent coupling (Ce)**: modules this one depends on
- **Instability**: Ce / (Ca + Ce) -- 0=stable, 1=unstable
- **Abstractness**: interfaces / total types
- **Distance from main sequence**: |A + I - 1|
- **Cohesion**: intra-module edges / total edges
- **Cycle detection**: DFS on module dependency graph
- **5 health rules**: MC001 (high instability), MC002 (low cohesion), MC003 (zone of pain), MC004 (zone of uselessness), MC005 (module cycle)
- **New endpoint**: `GET /coupling` with per-module metrics and cycle list
- 24 new tests

## 20. Refactor Long Functions (Phase 22)

Refactored the 6 longest functions (all >100 lines) into well-named helpers:
- `run_ingestion` (167?68): extracted `_clone_phase`, `_scan_phase`, `_analyze_phase`, `_blame_phase`
- `parse_unified_diff` (133?40): extracted `_finalize_file`, `_handle_metadata`, `_parse_hunk_header`, `_parse_content_line`
- `review_diff` (132?62): extracted `_collect_changes_and_findings`, `_build_diff_summary`
- `search` (123?30): extracted `_search_symbols`, `_search_summaries`, `_search_docs`
- `run_indexing` (119?78): extracted `_build_vector_records`
- `analyze_coupling` (101?30): extracted `_count_module_symbols`, `_apply_file_counts`, `_compute_edge_metrics`, `_compute_derived_metrics`
- All 1,842 tests still pass — zero behavior changes

## 21. API Endpoint Gaps (Phase 23)

6 new endpoints filling frontend needs:
- `GET /repos` — list all repos
- `GET /repos/{id}/snapshots` — paginated snapshot list (limit/offset)
- `DELETE /repos/{id}/snapshots/{sid}` — delete snapshot + cascade
- `GET /repos/{id}/snapshots/{sid}/files` — file browser with language filter
- `GET /repos/{id}/snapshots/{sid}/symbols/{fq}/callers` — who calls this function
- `PATCH /repos/{id}/snapshots/{sid}/symbols/{fq}/notes` — upsert user annotations
- `GET /repos/{id}/snapshots/{sid}/symbols/{fq}/notes` — read annotations
- New `SymbolNote` DB model with snapshot_id + symbol_fq_name index
- New schemas: `SymbolNoteCreate`, `SymbolNoteOut`, `CallerOut`, `CallersResponse`
- 28 new tests covering all endpoints, pagination, filters, 404s, CRUD

## 22. Export Enhancements (Phase 24)

3 new export formats, all pure Python (stdlib csv, json, io, zipfile):
- **CSV/ZIP** (`GET /export/csv`): ZIP containing symbols.csv, edges.csv, health_findings.csv, optionally dependencies.csv
- **SARIF 2.1.0** (`GET /export/sarif`): standard format for GitHub Code Scanning, VS Code, Azure DevOps
- **Markdown report** (`GET /export/markdown`): human-readable health report with severity breakdown, top findings table, most complex functions
- New module: `app/exports/generators.py` with `generate_csv_zip`, `generate_sarif`, `generate_markdown_report`
- New API router: `app/api/exports.py` with 3 endpoints
- 38 new tests: 7 CSV unit tests, 8 SARIF unit tests, 8 Markdown unit tests, 12 API tests, 3 edge cases

## 23. Test Coverage Tracking (Phase 25 / Phase10.1)

Test coverage measurement integrated end-to-end:
- Added `pytest-cov>=5.0` to dev deps; added `[tool.coverage.*]` config to `pyproject.toml`
- Coverage modes: line + branch, fail_under = 60%, omits `__init__.py` and `tests/`
- New module: `app/analysis/coverage_parser.py` parses coverage.py JSON 3.x output into typed `CoverageData` / `FileCoverage` dataclasses
- Files in the report are sorted by lowest coverage first (most actionable)
- New DB model: `CoverageReport` (one per snapshot, unique by snapshot_id, cascades on delete)
- New API router: `app/api/coverage.py` with 4 endpoints:
  - `POST /repos/{id}/snapshots/{sid}/coverage` (upload coverage.json body)
  - `GET /repos/{id}/snapshots/{sid}/coverage` (with `include_files` and `min_percent` filters)
  - `DELETE /repos/{id}/snapshots/{sid}/coverage`
  - `GET /repos/{id}/coverage/history` (paginated history)
- Grades: A (?90), B (?80), C (?70), D (?60), F (<60)
- Updated `.github/workflows/ci.yml` to run `pytest --cov=app --cov-report=xml --cov-report=json:coverage.json` and upload artifacts
- 36 new tests: 12 parser unit tests, 5 grade tests, 5 upload tests, 6 GET tests, 2 delete tests, 5 history tests, 1 cascading delete

## 24. Quality Gates / Thresholds (Phase 26 / Phase10.2)

Configurable quality gates that CI/CD can evaluate against:
- New DB models: `QualityGate` (config per repo) + `QualityGateResult` (evaluation history)
- New module: `app/analysis/gate_evaluator.py` — pure logic evaluator with 10 numeric checks + coverage check + blocked-rules check
- Config schema includes: max_errors, max_warnings, max_findings, min_coverage_percent, max_avg/max_cyclomatic_complexity, max_long_functions, max_clone_groups, max_dead_functions, max_module_cycles, max_instability_violations, blocked_rules
- 7 new API endpoints:
  - `POST /repos/{id}/quality-gates` — create gate
  - `GET /repos/{id}/quality-gates` — list (with active_only filter)
  - `GET /repos/{id}/quality-gates/{gate_id}` — get details
  - `PATCH /repos/{id}/quality-gates/{gate_id}` — update name/config/active
  - `DELETE /repos/{id}/quality-gates/{gate_id}` — delete
  - `POST /repos/{id}/snapshots/{sid}/evaluate-gate/{gate_id}` — evaluate snapshot
  - `GET /repos/quality-gates/schema` — list available config keys
- Evaluation persists result in `QualityGateResult` for history
- Returns "passed"/"failed" status with per-check breakdown
- 38 new tests: 11 evaluator unit tests, 5 config parser tests, 22 API tests

## 25. Audit Log (Phase 27 / Phase10.3)

Immutable audit trail for enterprise compliance (SOC 2, ISO 27001):
- New DB model: `AuditEvent` with indexes on (user_id, timestamp), (action, timestamp), (resource_type, resource_id)
- New module: `app/core/audit.py` — helpers for recording events, classifying requests, and filtering
- `should_audit(method, path)` — skips GETs and noise paths (/health, /metrics)
- `_classify_request(method, path)` — regex-based classifier returns (action, resource_type, resource_id)
- `record_audit_event(db, ...)` — writes an audit row (called from endpoints or middleware)
- New API router: `app/api/audit.py` with 4 endpoints:
  - `GET /admin/audit-log` — paginated query with 7 filters (user_id, action, resource_type, resource_id, success, method, limit/offset)
  - `GET /admin/audit-log/export` — CSV download (up to 10k rows)
  - `GET /admin/audit-log/stats` — total events, unique users, top actions, failure count
  - `DELETE /admin/audit-log/purge?older_than_days=90` — retention management
- 40 new tests: 9 should_audit, 11 classify, 2 record, 8 query, 4 export, 2 stats, 4 purge

## 26. API Key Scoping & Permissions (Phase 28 / Phase10.4)

Fine-grained API key permissions:
- Extended `ApiKey` model with: `scopes` (comma-separated), `expires_at`, `last_used_at`, `usage_count`
- New module: `app/auth/scopes.py` — 17 defined scopes, `parse_scopes`, `has_scope`, `validate_scopes`, `require_scope` dependency
- `_authenticate_api_key` now: checks expiration, stores scopes on `request.state.api_key_scopes`, increments usage_count + last_used_at
- `create_api_key` now accepts `scopes` (comma-separated, validated) and `expires_in_days` (1-365)
- `list_api_keys` now returns: scopes[], expires_at, last_used_at, usage_count
- New endpoint: `GET /auth/api-keys/scopes` — returns full scope catalog for UI
- JWT users bypass all scope checks (full access), only API keys are constrained
- Backward compatible: existing keys default to `scopes="*"` (full access)
- 28 new tests: 6 parse, 4 has_scope, 3 validate, 4 create, 2 list, 1 scopes endpoint, 4 enforcement, 4 internal

## 27. Function-Level Cycle Detection (Phase 29 / Phase10.5)

Tarjan's SCC algorithm for detecting call graph cycles:
- New module: `app/analysis/call_cycles.py` — `detect_call_cycles(callees, symbol_files)` returns `CallCycleReport`
- Algorithm: Tarjan's strongly connected components O(V+E), deterministic (sorted node iteration)
- Detects: direct recursion (self-loops, counted separately), mutual recursion (size-2+ SCCs)
- Report includes: cycle members, size, example cycle path (BFS), files involved, sorted by size desc
- New API router: `app/api/call_cycles.py` — `GET /repos/{id}/snapshots/{sid}/call-cycles`
- Query param: `min_cycle_size` (default 2, filters small cycles)
- 21 new tests: 13 algorithm unit tests + 8 API endpoint tests

## 28. Snapshot Tagging & Search (Phase 30 / Phase10.6)

Tags for organizing and filtering snapshots:
- New DB model: `SnapshotTag` with unique constraint (snapshot_id, tag) + index on tag
- Tags normalized to lowercase and trimmed
- 5 new API endpoints in `app/api/tags.py`:
  - `POST /repos/{id}/snapshots/{sid}/tags` — add tag (409 on duplicate, 400 on empty)
  - `DELETE /repos/{id}/snapshots/{sid}/tags/{tag}` — remove tag
  - `GET /repos/{id}/snapshots/{sid}/tags` — list tags for snapshot
  - `GET /repos/{id}/snapshots/by-tag/{tag}` — find snapshots with tag (includes all tags per snapshot)
  - `GET /repos/tags/stats` — global tag usage counts (sorted desc)
- 17 new tests

## 29. Bulk Operations (Phase 31 / Phase10.7)

Batch endpoints for managing large numbers of resources:
- New router: `app/api/bulk.py` with 4 endpoints:
  - `POST /repos/{id}/snapshots/bulk-delete` — delete up to 100 snapshots, returns per-item success/failure
  - `POST /repos/{id}/snapshots/bulk-tag` — tag up to 100 snapshots, skips duplicates
  - `DELETE /repos/{id}/snapshots/older-than/{days}` — time-based cleanup, returns deleted + remaining counts
  - `POST /repos/bulk-delete` — delete up to 50 repos (admin)
- Safety: max batch size enforced (100 snapshots, 50 repos)
- Tags normalized to lowercase
- 16 new tests

## 30. Health Score & History (Phase 32 / Phase10.8)

Weighted 0-100 health score with 9 category breakdown:
- New module: `app/analysis/health_score.py` — `compute_health_score(metrics)` returns `HealthScore`
- 9 categories: complexity(20%), design(20%), duplication(10%), dead_code(10%), documentation(5%), naming(5%), security(15%), dependencies(10%), testing(5%)
- Each category: 100 minus penalties, capped at 0; final = weighted sum
- Grades: A(?90), B(?80), C(?70), D(?60), F(<60)
- New DB model: `HealthScoreHistory` (persisted per snapshot, computed on first access)
- New API router: `app/api/health_score.py`:
  - `GET /repos/{id}/snapshots/{sid}/health-score` — compute+persist or return cached (supports `?recompute=true`)
  - `GET /repos/{id}/health-history` — time-series for charts
- 21 new tests: 10 algorithm + 11 API tests

## 31. SBOM Generation (Phase 33 / Phase10.9)

Software Bill of Materials in CycloneDX 1.5 and SPDX 2.3 formats:
- New module: `app/exports/sbom.py` — `generate_cyclonedx()` + `generate_spdx()` + `_to_purl()`
- PURL support for 8 ecosystems: pypi, npm, maven, crates, nuget, go, gem, composer
- CycloneDX: full spec 1.5 with metadata (tools, component), scoped components, properties
- SPDX: spec 2.3 with packages, external refs, DESCRIBES relationships
- New API endpoint: `GET /repos/{id}/snapshots/{sid}/export/sbom?format=cyclonedx|spdx`
- Query params: `format` (cyclonedx default), `include_dev` (bool, default true)
- Content-Disposition header for download
- 28 new tests: 7 PURL, 7 CycloneDX, 6 SPDX, 8 API endpoint

## 32. Incremental Health Analysis (Phase 34 / Phase10.10)

Incremental health analysis with fingerprint-based diffing:
- New DB model: `HealthFindingPersisted` with indexes on (snapshot_id) and (snapshot_id, fingerprint)
- New module: `app/analysis/incremental_health.py`:
  - `compute_fingerprint(rule_id, symbol, file, line)` — SHA256-based stable ID
  - `persist_findings(db, snapshot_id, findings)` — store findings with fingerprints
  - `compute_health_diff(db, new_sid, prev_sid)` — fingerprint set comparison
  - `copy_unchanged_findings(db, prev_sid, new_sid, changed_files)` — copies unchanged file findings
- New API router: `app/api/incremental_health.py` with 3 endpoints:
  - `POST /repos/{id}/snapshots/{sid}/health/findings` — persist findings
  - `GET /repos/{id}/snapshots/{sid}/health/findings` — list with severity/file filters
  - `GET /repos/{id}/snapshots/{sid}/health/diff/{prev_sid}` — diff showing added/fixed/unchanged
- Diff response includes summary: "+N new, -M fixed, K unchanged"
- 20 new tests: 5 fingerprint, 3 persist/diff logic, 12 API tests

---

## Phase 10 Summary: All 10 Features Complete

| # | Feature | Tests | Endpoints | Key Files |
|---|---------|-------|-----------|-----------|
| 1 | Coverage Tracking | +36 | +4 | coverage_parser.py, coverage.py |
| 2 | Quality Gates | +38 | +7 | gate_evaluator.py, quality_gates.py |
| 3 | Audit Log | +40 | +4 | audit.py (core + api) |
| 4 | API Key Scoping | +28 | +1 | scopes.py, dependencies.py |
| 5 | Call Cycle Detection | +21 | +1 | call_cycles.py (analysis + api) |
| 6 | Snapshot Tagging | +17 | +5 | tags.py |
| 7 | Bulk Operations | +16 | +4 | bulk.py |
| 8 | Health Score | +21 | +2 | health_score.py (analysis + api) |
| 9 | SBOM Generation | +28 | +1 | sbom.py (exports + api) |
| 10 | Incremental Health | +20 | +3 | incremental_health.py (analysis + api) |
| **Total** | **+265** | **+32** | |

## 33. RBAC Phase 1: Scope Enforcement (Phase 35)

Applied `require_scope()` to all 104 endpoints:
- `require_scope()` now depends on `get_current_user` (ensures auth runs first, populates `request.state.api_key_scopes`)
- **Router-level** scopes on 14 simple routers (analysis, search, diagrams, trends, deps, blame, call_cycles, dead_code, clones, coupling, exports, sbom, health_score)
- **Per-endpoint** scopes on 8 mixed routers (repos, coverage, quality_gates, tags, bulk, incremental_health, portable, indexing)
- All GET endpoints: `read:*` scopes; POST/PATCH: `write:*`; DELETE: `delete:*` or `write:*`; Admin: `admin:*`
- Auth endpoints (`/auth/*`) have no scope requirement
- New doc: `docs/PERMISSIONS.md` — full endpoint?scope matrix
- 19 new integration tests verifying scope enforcement with real API keys
- Backward compatible: JWT users bypass all scope checks, existing `*` keys unaffected

## 34. RBAC Phase 2: Role-to-Scope Mapping (Phase 36)

JWT users now have scope restrictions based on their role:
- New `ROLE_SCOPES` dict in `app/auth/scopes.py` mapping 5 roles to scope sets
- `get_role_scopes(role)` helper returns comma-separated scopes for a role
- `require_scope()` now checks JWT users' role scopes (not just API keys)
- Superadmin = `*` (unrestricted), Admin = all scopes, Employee = all non-admin, Support = read-only + audit, User = standard dev access
- Anonymous user (auth disabled) = superadmin role = all checks pass
- Unknown roles default to `user` scope set
- 25 new tests: 11 unit (role mapping validation) + 14 integration (JWT role enforcement)

## 35. RBAC Phase 3: Unified `protected()` Decorator (Phase 37)

Single decorator combining scope + role + repo ownership checks:
- New `protected(scope, roles, require_repo_owner)` in `app/auth/scopes.py`
- 3 checks in order: role whitelist ? scope check ? repo ownership
- Superadmin bypasses role whitelist; admin+ bypasses ownership
- Repo ownership uses `request.path_params["repo_id"]` + DB query
- Returns 403 for role/scope failures, 404 for ownership (prevents leaking repo existence)
- Uses FastAPI `Depends(get_db)` for testability (works with test DB overrides)
- 13 new tests: scope-only, role-only, ownership, combined, no-restrictions

## 36. RBAC Phase 4: Resource-Level Permissions (Phase 38)

Repo sharing with viewer/editor/owner access levels:
- New DB model: `RepoPermission` with unique constraint (repo_id, user_id)
- New enum: `RepoPermissionLevel` (viewer, editor, owner)
- New API router: `app/api/permissions.py` with 3 endpoints:
  - `POST /repos/{id}/permissions` — grant/update access (protected: write:repos + repo owner)
  - `GET /repos/{id}/permissions` — list permissions (protected: read:repos + repo owner)
  - `DELETE /repos/{id}/permissions/{user_id}` — revoke (protected: write:repos + repo owner)
- Updated `require_repo_access()` in dependencies.py to check `RepoPermission` table
- Access chain: admin role > repo owner > RepoPermission entry
- Validation: invalid level 400, self-grant 400, target not found 404
- 16 new tests

## 37. RBAC Phase 5: Team / Organization Model (Phase 39)

Full team CRUD with members and repo access:
- 3 new DB models: `Team`, `TeamMember`, `TeamRepoAccess` + `TeamRole` enum
- New API router: `app/api/teams.py` with 10 endpoints:
  - `POST /teams` — create (creator becomes admin member)
  - `GET /teams` — list my teams
  - `GET /teams/{id}` — details (members only)
  - `PATCH /teams/{id}` — update (team admin only)
  - `DELETE /teams/{id}` — delete (team admin only)
  - `GET /teams/{id}/members` — list members
  - `POST /teams/{id}/members` — add member (team admin)
  - `DELETE /teams/{id}/members/{uid}` — remove member (team admin)
  - `POST /teams/{id}/repos` — grant team repo access (team admin)
  - `GET /teams/{id}/repos` — list team repo access
- Updated `require_repo_access()` to check team-level access
- Access chain: admin > owner > RepoPermission > TeamRepoAccess
- App admins bypass team admin checks
- 20 new tests

## 38. RBAC Phase 6: Permission Caching (Phase 40)

In-memory TTL permission cache:
- New module: `app/auth/permission_cache.py` (300s TTL, 10K max entries)
- `require_repo_access()` checks cache before DB queries, caches results on success
- Cache invalidation on permission grant/revoke
- Admin endpoints: `GET /admin/cache/stats`, `POST /admin/cache/clear`
- Auto-eviction: expired entries cleaned up, oldest 10% removed when full
- 12 new tests

## 39. RBAC Phase 7: Audit Integration (Phase 41)

Permission events logged to audit trail:
- New module: `app/auth/audit_helpers.py` with `build_permission_denied_event` and `build_permission_change_event`
- `require_scope()` and `protected()` log all 403 denials (action: `permission.denied`)
- Permission grant/revoke in `permissions.py` logged (actions: `permission.granted`, `permission.revoked`)
- Async commit before raising 403 (audit never lost on denial)
- Best-effort: audit failures never block the request
- 6 new tests

## 40. RBAC Phase 8: Documentation & Developer Experience (Phase 42)

Full RBAC documentation:
- New: `docs/AUTHENTICATION.md` — complete auth guide (OAuth, API keys, roles, scopes, security)
- Updated: `docs/PERMISSIONS.md` — full endpoint?scope matrix, role mapping, resource permissions, team access
- Updated: all project docs with final endpoint counts (121), test counts (2,284), file counts (138 source + 104 test)
- All 8 RBAC phases complete ?

## 41. DocGen Phase 1: Enhanced Doc Types (Phase 43)

4 new documentation generators:
- `generate_api_reference(snapshot_id, module_name, symbols, edges, summaries)` — public API docs per module
- `generate_onboarding(snapshot_id, symbols, edges, modules, summaries, entry_points, metrics)` — getting-started guide
- `generate_changelog(snapshot_id, prev_id, cur_symbols, prev_symbols, cur_edges, prev_edges)` — diff-based changelog
- `generate_dependency_map(snapshot_id, symbols, edges, modules)` — internal/external dep graph + circular detection
- New DocType enum values: `api_reference`, `onboarding`, `changelog`, `dependency_map`
- Updated templates.py with 4 new section sets
- Updated orchestrator.py to generate new types in `generate_all_docs` and `generate_single_doc`
- New API endpoint: `POST /repos/{id}/snapshots/{sid}/docs/changelog?previous_snapshot_id=...`
- 42 new tests (all pure unit, no DB needed)

## 42. DocGen Phase 2: Diagram Embedding (Phase 44)

Mermaid diagram generators for documentation:
- New module: `app/docgen/diagrams.py` with 5 generators:
  - `generate_dependency_graph()` — module-level flowchart with auto-simplification
  - `generate_class_diagram()` — UML class diagram per module (classes, methods, inheritance)
  - `generate_sequence_diagram()` — call sequence from entry point (BFS traversal)
  - `generate_flowchart()` — call tree flowchart from any function
  - `generate_er_diagram()` — entity-relationship from class relationships
- `DiagramConfig` dataclass: max_nodes(25), max_edges(50), collapse_threshold(3), direction(TD/LR)
- `MermaidDiagram` dataclass with `.to_markdown()` renderer
- Auto-simplification: collapses small modules, limits nodes/edges, BFS traversal with depth limits
- 42 new tests
