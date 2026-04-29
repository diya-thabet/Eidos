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
  |     code_health.py orchestrates 40 rules from health_rules/
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
