# Developer Guide — Adding Features to Eidos

This document explains how to add new features, endpoints, parsers, and integrations to Eidos. It's written for a solo developer or a small team picking up the project for the first time.

---

## Table of Contents

1. [Project Layout](#1-project-layout)
2. [How a Request Flows Through the System](#2-how-a-request-flows)
3. [Adding a New API Endpoint](#3-adding-a-new-api-endpoint)
4. [Adding a New Language Parser](#4-adding-a-new-language-parser)
5. [Adding a New Code Health Rule](#5-adding-a-new-code-health-rule)
6. [Adding a New Database Model](#6-adding-a-new-database-model)
7. [Adding a New Integration (LLM, Vector DB, Git Provider)](#7-adding-a-new-integration)
8. [Testing Conventions](#8-testing-conventions)
9. [Common Patterns Used Everywhere](#9-common-patterns)
10. [What NOT to Do](#10-what-not-to-do)

---

## 1. Project Layout

```
backend/
  app/
    api/              ? HTTP endpoints (thin controllers)
    analysis/         ? Static analysis engine (parsers, graph, health)
    indexing/         ? Summarization + vector indexing
    reasoning/        ? Q&A engine
    reviews/          ? PR review engine
    docgen/           ? Documentation generator
    guardrails/       ? Output evaluation
    auth/             ? OAuth, JWT, RBAC
    storage/          ? Database models + Pydantic schemas
    core/             ? Config, ingestion, tasks, middleware
  tests/              ? One test file per feature area
```

**Key rule**: Each module has a single responsibility. The `api/` layer is thin — it validates input, calls a service module, and returns a response. Business logic lives in the service modules (`analysis/`, `reasoning/`, `reviews/`, etc.).

---

## 2. How a Request Flows

Example: `POST /repos/{id}/snapshots/{sid}/ask`

```
1. FastAPI receives the HTTP request
2. Middleware runs (request ID, logging, rate limiting)
3. Route handler in api/reasoning.py is called
4. Depends(verify_snapshot) checks the snapshot exists (api/dependencies.py)
5. Depends(get_db) provides a database session (storage/database.py)
6. Handler calls business logic:
   a. question_router.build_question() — classifies the question
   b. retriever.retrieve_context() — gathers relevant code context
   c. answer_builder.build_answer() — generates the answer
7. Handler returns the response as a Pydantic schema
8. Middleware logs the request duration
```

**Data flow:**

```
HTTP Request ? api/ (controller) ? service module ? storage/ (DB) ? Response
                                       ?
                                  analysis/ (code graph)
                                  indexing/ (vector search)
```

---

## 3. Adding a New API Endpoint

### Step-by-step

**Example**: Adding `GET /repos/{id}/snapshots/{sid}/hotspots` that returns the most complex symbols.

#### Step 1: Create the route in the appropriate `api/` file

If it's analysis-related, add to `api/analysis.py`. If it's a new domain, create a new file like `api/hotspots.py`.

```python
# app/api/analysis.py (or new file)

@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/hotspots",
    summary="Get complexity hotspots in the codebase",
    description="Returns the top N symbols ranked by cyclomatic complexity.",
)
async def get_hotspots(
    repo_id: str,
    snapshot_id: str,
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db),
    _snap: RepoSnapshot = Depends(verify_snapshot),  # ? always verify
) -> Any:
    # Call business logic (NOT inline SQL here)
    result = await db.execute(
        select(Symbol)
        .where(Symbol.snapshot_id == snapshot_id)
        .order_by(Symbol.end_line - Symbol.start_line)  # proxy for complexity
        .limit(limit)
    )
    return [_symbol_to_dict(s) for s in result.scalars().all()]
```

#### Step 2: If new file, register the router in `main.py`

```python
from app.api import hotspots as hotspots_api
app.include_router(hotspots_api.router, prefix="/repos", tags=["hotspots"])
```

#### Step 3: Add response schema in `storage/schemas.py` (if needed)

```python
class HotspotOut(BaseModel):
    fq_name: str
    kind: str
    file_path: str
    line_count: int
    complexity_rank: int
```

#### Step 4: Write tests

```python
# tests/test_hotspots.py
class TestHotspots:
    @pytest.mark.asyncio
    async def test_returns_sorted_by_complexity(self, client):
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/hotspots")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) <= 20
        # Verify sorted descending
        sizes = [i["line_count"] for i in items]
        assert sizes == sorted(sizes, reverse=True)
```

#### Step 5: Run checks

```bash
python -m ruff check app/ tests/
python -m mypy app/ --ignore-missing-imports
python -m pytest tests/test_hotspots.py -v
python -m pytest tests/ -q  # full suite
```

### Checklist for every new endpoint

- [ ] Snapshot-scoped endpoints use `Depends(verify_snapshot)`
- [ ] Database session via `Depends(get_db)`
- [ ] Has `summary=` and `description=` in the route decorator
- [ ] Query parameters have `description=`
- [ ] Response uses a Pydantic model (not raw dicts)
- [ ] Tests cover: happy path, not found, edge cases
- [ ] `ruff check` passes
- [ ] `mypy` passes
- [ ] Full test suite passes

---

## 4. Adding a New Language Parser

This is the most common extension. Eidos supports 9 languages — adding a 10th takes about 2-4 hours.

### Step 1: Install the tree-sitter grammar

```bash
pip install tree-sitter-kotlin  # example
```

Add to `pyproject.toml`:

```toml
dependencies = [
    ...
    "tree-sitter-kotlin>=0.23",
]
```

### Step 2: Create the parser file

Create `app/analysis/kotlin_parser.py`:

```python
from __future__ import annotations

import tree_sitter_kotlin as ts_kotlin
from tree_sitter import Language, Parser

from app.analysis.base_parser import LanguageParser
from app.analysis.models import (
    EdgeInfo, EdgeType, FileAnalysis, SymbolInfo, SymbolKind,
)

KOTLIN_LANGUAGE = Language(ts_kotlin.language())


class KotlinParser(LanguageParser):
    @property
    def language_id(self) -> str:
        return "kotlin"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        parser = Parser(KOTLIN_LANGUAGE)
        tree = parser.parse(source)
        # Walk the tree, extract symbols and edges
        # (see java_parser.py or python_parser.py for patterns)
        ...
```

**Key patterns to follow** (look at existing parsers):
- Extract classes, interfaces, functions, methods
- Set `fq_name` as `Namespace.Class.Method`
- Set `parent_fq_name` for methods inside classes
- Extract `CALLS` edges for method invocations
- Extract `INHERITS` / `IMPLEMENTS` edges for type hierarchies
- Extract `CONTAINS` edges for parent-child (class contains method)

### Step 3: Register in `parser_registry.py`

```python
# In _init_registry():
try:
    from app.analysis.kotlin_parser import KotlinParser
    _registry["kotlin"] = KotlinParser()
    logger.debug("Registered parser: kotlin")
except Exception:
    logger.info("Kotlin parser unavailable")
```

### Step 4: Map file extensions in `core/ingestion.py`

```python
LANGUAGE_MAP: dict[str, str] = {
    ...
    ".kt": "kotlin",
    ".kts": "kotlin",
}
```

### Step 5: Write parser tests

Create `tests/test_kotlin_parser.py` with tests for:
- Class extraction (name, fq_name, line range)
- Function extraction (parameters, return type)
- Inheritance detection
- Nested classes
- Edge cases (empty file, syntax errors, Unicode)

**That's it.** No other files need to change. The ingestion pipeline, analysis pipeline, graph builder, and all API endpoints automatically pick up the new language.

---

## 5. Adding a New Code Health Rule

All 40 rules live in `app/analysis/code_health.py`.

### Step 1: Define the rule function

```python
def check_magic_numbers(symbols, edges, graph):
    """Flag methods with hardcoded numeric literals."""
    findings = []
    for sym in symbols:
        if sym.kind == SymbolKind.METHOD:
            # Your detection logic here
            if _has_magic_numbers(sym):
                findings.append(HealthFinding(
                    rule_id="magic_numbers",
                    category="clean_code",
                    severity="low",
                    symbol_fq_name=sym.fq_name,
                    file_path=sym.file_path,
                    line=sym.start_line,
                    message=f"Method '{sym.name}' contains magic numbers",
                    suggestion="Extract numeric literals into named constants",
                ))
    return findings
```

### Step 2: Register it

Add to the `_ALL_RULES` list at the bottom of `code_health.py`:

```python
_ALL_RULES = [
    ...
    check_magic_numbers,
]
```

### Step 3: Add to `HealthConfig.all_rules()`

Add the rule metadata so it shows up in `GET /health/rules`.

### Step 4: Write tests in `tests/test_code_health.py`

```python
def test_magic_numbers_detected(self):
    # Create a method with magic numbers
    symbols = [SymbolInfo(name="calc", kind=SymbolKind.METHOD, ...)]
    findings = check_magic_numbers(symbols, [], None)
    assert len(findings) == 1
    assert findings[0].rule_id == "magic_numbers"
```

---

## 6. Adding a New Database Model

### Step 1: Define the model in `storage/models.py`

```python
class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_alerts_snapshot", "snapshot_id"),)
```

### Step 2: Add Pydantic schema in `storage/schemas.py`

```python
class AlertOut(BaseModel):
    id: int
    snapshot_id: str
    alert_type: str
    message: str
    created_at: str
```

### Step 3: Restart the server

Tables are auto-created via `Base.metadata.create_all` on startup. For production, use Alembic:

```bash
alembic revision --autogenerate -m "add alerts table"
alembic upgrade head
```

**Important**: Always add `ondelete="CASCADE"` to `ForeignKey` for snapshot-scoped data. This ensures deleting a repo cascades cleanly.

---

## 7. Adding a New Integration

### New LLM Provider

All LLM access goes through `reasoning/llm_client.py`. The `create_llm_client()` factory creates an OpenAI-compatible client. To add a non-OpenAI provider:

1. Create a new class implementing the same interface as `LLMClient`
2. Add a condition in `create_llm_client()` based on config

### New Vector Database

1. Implement the `VectorStore` abstract class in `indexing/vector_store.py`
2. Add a factory function that reads config to pick the implementation
3. Current implementations: `InMemoryVectorStore`, `QdrantVectorStore`

### New Git Provider

1. Add URL pattern detection in `core/ingestion.py` `_inject_token()`
2. Add webhook handler in `api/webhooks.py`
3. Both follow the existing patterns — look at GitHub/GitLab implementations

---

## 8. Testing Conventions

### File naming

- One test file per feature area: `test_<feature>.py`
- Test classes group related tests: `class TestFeatureName:`
- Test methods describe what they verify: `test_returns_404_for_missing_repo`

### Fixtures

```python
# Every test file uses these fixtures:
@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    yield
    await drop_tables()

@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
```

### What to test

Every endpoint needs:
1. **Happy path** — normal input, expected output
2. **Not found** — invalid repo_id or snapshot_id returns 404
3. **Validation** — bad input returns 422
4. **Edge cases** — empty data, large input, special characters

### Running tests

```bash
pytest tests/test_my_feature.py -v          # single file
pytest tests/ -q                            # full suite
pytest tests/ -k "test_search" -v           # by name pattern
pytest tests/ --tb=short                    # shorter tracebacks
```

---

## 9. Common Patterns Used Everywhere

### Pattern 1: Shared snapshot verification

Every snapshot-scoped endpoint uses the `verify_snapshot` dependency:

```python
from app.api.dependencies import verify_snapshot

async def my_endpoint(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snap: RepoSnapshot = Depends(verify_snapshot),  # auto-checks 404
) -> Any:
    ...
```

**Why**: Avoids duplicating the "does this snapshot exist?" check in every endpoint. The dependency runs before your handler code.

### Pattern 2: Paginated responses

List endpoints return `PaginatedResponse`:

```python
return PaginatedResponse(
    items=[...],
    total=total_count,
    limit=limit,
    offset=offset,
)
```

**Why**: Clients know total count, can paginate, and the format is consistent across all list endpoints.

### Pattern 3: Compact serialization for exports

The portable export uses short keys (`n` instead of `name`, `fq` instead of `fq_name`) and omits empty fields:

```python
sym = {"n": s.name, "k": s.kind, "fq": s.fq_name}
if s.namespace:
    sym["ns"] = s.namespace  # only include if non-empty
```

**Why**: Reduces file size by 30-40% before gzip compression.

### Pattern 4: Lazy imports for optional dependencies

Heavy modules are imported inside functions, not at the top:

```python
async def run_health_analysis(...):
    from app.analysis.code_health import run_health_check  # lazy
```

**Why**: Prevents circular imports and keeps startup fast. The import only happens when the endpoint is actually called.

### Pattern 5: Background tasks for long operations

Ingestion runs as a background task:

```python
background.add_task(_run_ingestion_wrapper, snapshot.id)
```

**Why**: The API returns 202 immediately while ingestion runs. Users poll `/status` to check progress.

---

## 10. What NOT to Do

| Don't | Why | Do This Instead |
|-------|-----|-----------------|
| Put business logic in `api/` files | Controllers should be thin | Put logic in service modules (`analysis/`, `reasoning/`, etc.) |
| Use raw SQL strings | SQL injection risk, no type checking | Use SQLAlchemy ORM queries |
| Add `print()` statements | Breaks structured logging | Use `logger.info()` / `logger.debug()` |
| Import at module level if it causes circular imports | Breaks startup | Use lazy imports inside functions |
| Hardcode config values | Can't change per environment | Use `settings.xxx` from `core/config.py` |
| Skip writing tests | Regressions will happen | Write tests BEFORE or WITH the feature |
| Return raw dicts from endpoints | No validation, no docs | Use Pydantic `response_model` |
| Catch `except Exception: pass` | Hides bugs | Log the error, re-raise, or handle specifically |
| Add new pip dependencies without reason | Bloats image, supply chain risk | Check if stdlib or existing deps can do it |
