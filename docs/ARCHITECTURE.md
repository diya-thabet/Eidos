# Eidos - Legacy Code Intelligence Tool

## Technical Documentation (Phases 0-2)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Tech Stack](#3-tech-stack)
4. [Phase 0 - Foundation](#4-phase-0---foundation)
5. [Phase 1 - Repo Ingestion](#5-phase-1---repo-ingestion)
6. [Phase 2 - Static Analysis](#6-phase-2---static-analysis)
7. [Data Model](#7-data-model)
8. [API Reference](#8-api-reference)
9. [Analysis Engine Deep Dive](#9-analysis-engine-deep-dive)
10. [Testing Strategy](#10-testing-strategy)
11. [Project Structure](#11-project-structure)
12. [Getting Started](#12-getting-started)
13. [Configuration](#13-configuration)
14. [Design Decisions](#14-design-decisions)
15. [What's Next](#15-whats-next)

---

## 1. Project Overview

**Eidos** is a language-agnostic code intelligence platform that analyzes any codebase (C#, Java, Python, TypeScript, Go, Rust, C, C++) and provides three core capabilities:

1. **Explains legacy codebases** - architecture, intent, data flows, with evidence
2. **Auto-generates documentation** - accurate, regeneratable, with citations to actual code
3. **Reviews PRs for logic/behavior risks** - not style nitpicks, but real behavioral concerns

### Core Principles

Every output from Eidos must include:

| Principle | Description |
|-----------|-------------|
| **Evidence** | File path + symbol name + line range |
| **Confidence** | High / Medium / Low rating |
| **Verification** | 2-5 bullet checklist ("what to verify") |
| **No style nitpicks** | Focus on behavior, logic, architecture, contracts, side effects |

### Current Status

| Phase | Name | Status |
|-------|------|--------|
| Phase 0 | Foundation | **Complete** |
| Phase 1 | Repo Ingestion | **Complete** |
| Phase 2 | Static Analysis | **Complete** |
| Phase 3 | Summarization & Indexing | **Complete** |
| Phase 4 | Explain / Q&A | **Complete** |
| Phase 5 | PR Review | **Complete** |
| Phase 6 | Auto Documentation | **Complete** |
| Phase 7 | Evaluation & Guardrails | **Complete** |
| Phase 8 | Security & Multi-tenant | **Complete** |
| Phase 9 | Deployment & Beta | Planned |
| Phase 10 | Production Hardening | **Complete** |

---

## 2. Architecture

Eidos follows a **modular monolith** architecture. All components live in a single Python backend but are organized into clearly separated packages with defined responsibilities.

```
              ???????????????????????????????????????????????????????
              ?              FastAPI  (REST API)                     ?
              ?  /auth  /repos  /analysis  /indexing  /reasoning     ?
              ?  /reviews  /docs  /evaluations  /health             ?
              ???????????????????????????????????????????????????????
                                    ?
        ?????????????????????????????????????????????????????????
        ?           ?               ?            ?              ?
  ????????????? ????????? ?????????????????? ??????????? ?????????????
  ?   Auth    ? ?Ingest ? ?   Analysis     ? ? Indexing? ? Reasoning ?
  ?(JWT,OAuth)? ?(clone)? ?(parser, graph) ? ?(summary)? ?(Q&A, LLM) ?
  ????????????? ????????? ?????????????????? ??????????? ?????????????
                    ?              ?              ?
        ?????????????       ????????       ????????
        ?           ?       ?      ?       ?      ?
  ????????????? ????????? ???????????? ???????????????? ?????????????
  ?  Reviews  ? ?DocGen ? ?Guardrails? ?  Storage      ? ? VectorDB  ?
  ?(diff,risk)? ?(md)   ? ?(eval)    ? ?  (any SQL DB) ? ? (Qdrant)  ?
  ????????????? ????????? ???????????? ????????????????? ?????????????
```

### Data Flow (Current)

```
1. User registers repo via POST /repos (with optional git_token for private repos)
2. User triggers ingestion via POST /repos/{id}/ingest
3. Background task:
   a. Clones the repo (GitPython, with auth token injection for private repos)
   b. Scans files (language detection, hashing)
   c. Parses all C# files (tree-sitter)
   d. Builds code graph (symbols + edges)
   e. Generates summaries (symbol, module, file level)
   f. Creates vector embeddings for semantic search
   g. Persists everything to database
   h. Cleans up clone directory (configurable)
4. User queries symbols, edges, graph neighborhoods via API
5. User asks questions answered with citations (Phase 4)
6. User submits PR diffs for behavioral review (Phase 5)
7. User generates documentation (README, architecture, etc.) (Phase 6)
8. User runs evaluation / guardrails checks (Phase 7)
```

---

## 3. Tech Stack

### Backend

| Technology | Purpose | Version |
|-----------|---------|---------|
| **Python** | Primary language | 3.11+ |
| **FastAPI** | REST API framework | >=0.115 |
| **SQLAlchemy** | Async ORM | >=2.0 |
| **asyncpg** | PostgreSQL async driver | >=0.29 |
| **aiomysql** | MySQL async driver (optional) | >=0.2 |
| **aiosqlite** | SQLite async driver (dev/test) | >=0.20 |
| **Alembic** | Database migrations | >=1.13 |
| **GitPython** | Git repo cloning (any provider) | >=3.1 |
| **tree-sitter** | Incremental parsing framework | >=0.23 |
| **tree-sitter-c-sharp** | C# grammar for tree-sitter | >=0.23 |
| **tree-sitter-java** | Java grammar for tree-sitter | >=0.23 |
| **tree-sitter-python** | Python grammar for tree-sitter | >=0.23 |
| **tree-sitter-typescript** | TypeScript/TSX grammar for tree-sitter | >=0.23 |
| **tree-sitter-go** | Go grammar for tree-sitter | >=0.23 |
| **tree-sitter-rust** | Rust grammar for tree-sitter | >=0.23 |
| **tree-sitter-c** | C grammar for tree-sitter | >=0.23 |
| **tree-sitter-cpp** | C++ grammar for tree-sitter | >=0.23 |
| **Pydantic** | Data validation & schemas | >=2.0 |
| **pydantic-settings** | Configuration management | >=2.0 |
| **PyJWT** | JWT session tokens | >=2.8 |
| **cryptography** | Fernet encryption (secrets at rest) | >=42.0 |

### Infrastructure

| Technology | Purpose |
|-----------|---------|
| **PostgreSQL 16** | Default data store (switchable via env var) |
| **MySQL / Oracle / SQL Server** | Alternative databases (via SQLAlchemy async) |
| **SQLite** | Zero-setup development and testing |
| **Redis 7** | Background job queue, future token blocklist |
| **Qdrant** | Vector database for semantic search |
| **Docker Compose** | Local development infrastructure |

### Development & Testing

| Tool | Purpose |
|------|---------|
| **pytest** | Test framework |
| **pytest-asyncio** | Async test support |
| **aiosqlite** | In-memory SQLite for tests |
| **httpx** | Async HTTP client for API tests |
| **ruff** | Linting & formatting |
| **mypy** | Static type checking |
| **GitHub Actions** | CI pipeline |

---

## 4. Phase 0 - Foundation

**Goal:** Make it buildable - repo structure, infrastructure, CI, API skeleton.

### What Was Built

1. **Monorepo structure** with clear package boundaries:
   - `backend/app/` - Application code
   - `backend/tests/` - Test suite
   - `infra/` - Docker Compose and deployment scripts
   - `.github/workflows/` - CI pipeline

2. **Docker Compose** (`infra/docker-compose.yml`):
   - PostgreSQL 16 (Alpine) on port 5432
   - Redis 7 (Alpine) on port 6379
   - Qdrant v1.9.7 on ports 6333/6334
   - Backend API service (auto-built from Dockerfile)
   - Health checks on postgres and redis
   - Persistent volumes for data and cloned repos

3. **CI Pipeline** (`.github/workflows/ci.yml`):
   - Triggers on push/PR to main
   - Runs: ruff lint ? mypy type check ? pytest
   - Python 3.11

4. **API Skeleton** (`app/main.py`):
   - FastAPI app with lifespan management
   - Auto-creates tables on startup (graceful fallback if DB unavailable)
   - Health check endpoint
   - Router registration for repos and analysis

5. **Configuration** (`app/core/config.py`):
   - Environment-based settings via pydantic-settings
   - Prefix: `EIDOS_` for all env vars
   - Supports `.env` file

### Acceptance Criteria Met

- [x] Local stack starts with one command (`docker compose up -d`)
- [x] CI green on push
- [x] API skeleton responds on `/health`

---

## 5. Phase 1 - Repo Ingestion

**Goal:** Get code into the system - clone repos, create snapshots, scan and catalog files.

### What Was Built

#### 1. Git Repository Cloning (`app/core/ingestion.py`)

```
clone_repo(url, branch, dest, commit_sha?) ? resolved_sha
```

- Clones via GitPython to `{repos_data_dir}/{repo_id}/{snapshot_id}`
- Supports specific commit SHA checkout or HEAD
- Shallow clone (depth=1) when no specific SHA requested
- Cleans up existing directory before cloning

#### 2. File Scanning (`app/core/ingestion.py`)

```
scan_files(repo_dir) ? list[{path, language, hash, size_bytes}]
```

- Walks the repo directory tree
- **Language detection** by file extension (C#-focused):

  | Extension | Language |
  |-----------|----------|
  | `.cs`, `.csx` | csharp |
  | `.csproj`, `.config`, `.props`, `.targets` | xml |
  | `.sln` | solution |
  | `.json` | json |
  | `.xml` | xml |
  | `.yaml`, `.yml` | yaml |
  | `.md` | markdown |
  | `.sql` | sql |

- **Skipped directories:** `.git`, `bin`, `obj`, `node_modules`, `.vs`, `packages`, `TestResults`, `artifacts`
- **File size limit:** 1 MB max per file
- **SHA-256 hashing** for change detection across snapshots
- Empty files are skipped

#### 3. Snapshot Management

- Each ingestion creates an immutable `RepoSnapshot` record
- Snapshots track: commit SHA, status (pending/running/completed/failed), file count, error messages
- Repos track `last_indexed_at` timestamp

#### 4. Background Task Pipeline (`app/core/tasks.py`)

The ingestion runs as a FastAPI `BackgroundTask`:

```
POST /repos/{id}/ingest ? 202 Accepted (snapshot_id, status: pending)

Background:
  1. Set status ? running
  2. Clone repo to disk
  3. Scan files ? File records in DB
  4. Run static analysis (Phase 2) ? Symbol + Edge records in DB
  5. Set status ? completed (or failed with error message)
```

#### 5. Database Models

- `Repo` - Repository registration (name, URL, branch)
- `RepoSnapshot` - Immutable snapshot per commit SHA
- `File` - Individual file metadata (path, language, hash, size)

### Security Measures

- **Never executes repo code** - only reads and parses
- File extension allowlist (unknown extensions ignored)
- Size limits enforced
- Binary files skipped

### Acceptance Criteria Met

- [x] Ingest a repo and see files recorded in DB
- [x] Snapshot created with commit SHA tracking
- [x] File inventory with language detection and hashing

---

## 6. Phase 2 - Static Analysis

**Goal:** Build the code graph - extract symbols, call graph, module dependencies, entry points, metrics.

### What Was Built

#### 1. C# Parser (`app/analysis/csharp_parser.py`)

Uses **tree-sitter** with the C# grammar for fast, error-tolerant parsing. Tree-sitter is an incremental parsing library that builds concrete syntax trees and handles malformed code gracefully without crashing.

**Symbols extracted:**

| Symbol Kind | What's Captured |
|------------|-----------------|
| `class` | Name, namespace, fq_name, modifiers, base types, line range |
| `interface` | Name, namespace, fq_name, modifiers, line range |
| `struct` | Name, namespace, fq_name, modifiers, line range |
| `enum` | Name, namespace, fq_name, modifiers, line range |
| `record` | Name, namespace, fq_name, modifiers, line range |
| `delegate` | Name, namespace, fq_name, line range |
| `method` | Name, signature, parameters, return type, modifiers, line range |
| `constructor` | Name, parameters, modifiers, line range |
| `property` | Name, type, modifiers, line range |
| `field` | Name, type, modifiers, line range |

**Per symbol, we capture:**
- `fq_name` - Fully qualified name (e.g., `MyApp.Services.UserService.GetById`)
- `file_path` - Relative path to the source file
- `start_line` / `end_line` - Exact line range in the file
- `namespace` - Containing namespace
- `parent_fq_name` - Enclosing type (for members and nested types)
- `modifiers` - Access modifiers (`public`, `static`, `abstract`, etc.)
- `signature` - Human-readable declaration (truncated at body)
- `parameters` - List of typed parameters (for methods/constructors)
- `return_type` - Return type (for methods/properties)
- `base_types` - Inherited classes / implemented interfaces
- `doc_comment` - XML doc comments (`///`) if present

**Edge (relationship) extraction:**

| Edge Type | Description | Example |
|----------|-------------|---------|
| `calls` | Method invokes another method | `Delete()` calls `GetById()` |
| `contains` | Parent-child relationship | `UserService` contains `GetById` |
| `implements` | Class implements interface | `UserService` implements `IUserService` |
| `inherits` | Interface/struct inheritance | `IAdminService` inherits `IUserService` |
| `imports` | Using directive | File imports `System.Collections.Generic` |

**Call detection covers:**
- Direct method invocations (`foo.Bar()`)
- Simple function calls (`DoWork()`)
- Object creation expressions (`new OrderItem()`)
- Member access chains (`_service.GetById(id)`)

**Robustness:**
- Empty files produce empty results (no crash)
- Malformed C# code is handled gracefully (tree-sitter is error-tolerant)
- Missing files are logged and skipped
- Unicode is handled with fallback replacement

#### 2. Graph Builder (`app/analysis/graph_builder.py`)

The `CodeGraph` class aggregates file analyses into a navigable code graph:

```python
graph = build_graph(analyses: list[FileAnalysis]) ? CodeGraph
```

**CodeGraph provides:**

| Method | Description |
|--------|-------------|
| `get_callers(fq_name)` | Symbols that call the given symbol |
| `get_callees(fq_name)` | Symbols that the given symbol calls |
| `get_children(fq_name)` | Members of a class/struct/interface |
| `get_neighborhood(fq_name, depth)` | BFS expansion via call edges (configurable hops) |
| `get_symbols_by_kind(kind)` | All symbols of a given kind |
| `get_symbols_in_file(path)` | All symbols in a specific file |
| `fan_in(fq_name)` | Count of distinct callers |
| `fan_out(fq_name)` | Count of distinct callees |

**Module graph:**
- Symbols are grouped by **namespace** into logical modules
- Each module tracks: file count, symbol count, file paths, namespace dependencies
- Dependencies derived from `using` directives
- Fallback: folder-based grouping when no namespace is declared

#### 3. Entry Point Detection (`app/analysis/entry_points.py`)

Automatically identifies application entry points:

| Entry Point Kind | Detection Logic |
|-----------------|-----------------|
| `controller` | Classes inheriting `Controller`, `ControllerBase`, `ApiController`, `ODataController` |
| `controller_action` | Public methods inside controller classes |
| `main` | Static `Main` methods |
| `startup` | Classes named `Startup` or `Program` |
| `worker` | Classes inheriting `BackgroundService` or implementing `IHostedService` |

**Controller route inference:**
- Convention-based: `UsersController` ? `/users`
- Action methods: `UsersController.Details` ? `/users/Details`

#### 4. Code Metrics (`app/analysis/metrics.py`)

Computes lightweight complexity indicators per symbol:

| Metric | Description |
|--------|-------------|
| `lines_of_code` | `end_line - start_line + 1` |
| `fan_in` | Number of distinct callers |
| `fan_out` | Number of distinct callees |
| `child_count` | Number of members (for classes) |
| `is_public` | Whether the symbol has `public` modifier |
| `is_static` | Whether the symbol has `static` modifier |

**Hotspot detection:**
```python
find_hotspots(graph, min_fan_in=3, min_loc=50) ? list[SymbolMetrics]
```
Identifies symbols that are both **large** (many lines) and **highly called** (many callers) - these are high-risk for regressions.

#### 5. Analysis Pipeline (`app/analysis/pipeline.py`)

Orchestrates the full analysis flow:

```python
# Step 1: Analyze all C# files in the snapshot
graph = analyze_snapshot_files(repo_dir, file_records) ? CodeGraph

# Step 2: Persist to database
await persist_graph(db, snapshot_id, graph)
```

**Pipeline behavior:**
- Filters for C# files only (other languages skipped)
- Logs warnings for missing files but continues
- Catches per-file parse errors without aborting
- Links edge records to symbol IDs via `flush()` after each symbol insert
- Stores modifiers as comma-separated strings in DB

### Acceptance Criteria Met

- [x] From any symbol: list callers and callees
- [x] From any module: list dependencies
- [x] Entry points detected (controllers, Main, Startup, workers)
- [x] Basic metrics computed (LOC, fan-in/out)
- [x] Analysis integrated into ingestion pipeline

---

## 7. Data Model

### Entity Relationship Diagram

```
????????????       ??????????????????       ????????????
?  repos   ? 1???* ? repo_snapshots ? 1???* ?  files   ?
?          ?       ?                ?       ?          ?
? id (PK)  ?       ? id (PK)        ?       ? id (PK)  ?
? name     ?       ? repo_id (FK)   ?       ? snap_id  ?
? url      ?       ? commit_sha     ?       ? path     ?
? branch   ?       ? status         ?       ? language ?
? created  ?       ? file_count     ?       ? hash     ?
? indexed  ?       ? error_message  ?       ? size     ?
????????????       ? created_at     ?       ????????????
                   ??????????????????
                           ?
                    ???????????????
                    ?             ?
              ????????????? ????????????
              ?  symbols  ? ?  edges   ?
              ?           ? ?          ?
              ? id (PK)   ? ? id (PK)  ?
              ? snap_id   ? ? snap_id  ?
              ? file_id   ? ? src_sym  ?
              ? kind      ? ? tgt_sym  ?
              ? name      ? ? src_fq   ?
              ? fq_name   ? ? tgt_fq   ?
              ? file_path ? ? type     ?
              ? start_ln  ? ? file     ?
              ? end_ln    ? ? line     ?
              ? namespace ? ????????????
              ? parent_fq ?
              ? signature ?
              ? modifiers ?
              ? ret_type  ?
              ?????????????
```

### Database Indexes

| Table | Index | Columns | Purpose |
|-------|-------|---------|---------|
| files | `ix_files_snapshot_path` | snapshot_id, path | Fast file lookup per snapshot |
| symbols | `ix_symbols_snapshot_fq` | snapshot_id, fq_name | Symbol lookup by fully-qualified name |
| symbols | `ix_symbols_snapshot_kind` | snapshot_id, kind | Filter symbols by type |
| symbols | `ix_symbols_snapshot_file` | snapshot_id, file_path | List symbols in a file |
| edges | `ix_edges_snapshot_type` | snapshot_id, edge_type | Filter edges by relationship type |
| edges | `ix_edges_snapshot_source` | snapshot_id, source_fq_name | Find outgoing edges |
| edges | `ix_edges_snapshot_target` | snapshot_id, target_fq_name | Find incoming edges |

### Cascade Behavior

- Deleting a `Repo` cascades to all `RepoSnapshot` records
- Deleting a `RepoSnapshot` cascades to all `File`, `Symbol`, and `Edge` records
- Deleting a `File` sets `Symbol.file_id` to NULL (no data loss)
- Deleting a `Symbol` cascades to related `Edge` records

---

## 8. API Reference

### Repo Management

#### `GET /health`
Health check.

**Response:** `{"status": "ok"}`

---

#### `POST /repos`
Register a new repository.

**Request Body:**
```json
{
  "name": "my-csharp-app",
  "url": "https://github.com/org/repo",
  "default_branch": "main"  // optional, defaults to "main"
}
```

**Response (201):**
```json
{
  "id": "a1b2c3d4e5f6",
  "name": "my-csharp-app",
  "url": "https://github.com/org/repo",
  "default_branch": "main",
  "created_at": "2025-01-15T10:30:00+00:00",
  "last_indexed_at": null
}
```

---

#### `POST /repos/{repo_id}/ingest`
Trigger repo ingestion (clone + scan + analysis).

**Request Body (optional):**
```json
{
  "commit_sha": "abc123def456"  // null = HEAD
}
```

**Response (202):**
```json
{
  "snapshot_id": "x1y2z3w4a5b6",
  "status": "pending"
}
```

---

#### `GET /repos/{repo_id}/status`
Get all snapshots for a repo.

**Response (200):**
```json
{
  "repo_id": "a1b2c3d4e5f6",
  "name": "my-csharp-app",
  "snapshots": [
    {
      "id": "x1y2z3w4a5b6",
      "repo_id": "a1b2c3d4e5f6",
      "commit_sha": "abc123def456",
      "status": "completed",
      "file_count": 42,
      "error_message": null,
      "created_at": "2025-01-15T10:31:00+00:00"
    }
  ]
}
```

---

#### `GET /repos/{repo_id}/snapshots/{snapshot_id}`
Get snapshot detail with file list.

---

### Analysis Endpoints

#### `GET /repos/{repo_id}/snapshots/{snapshot_id}/symbols`
List symbols in a snapshot.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `kind` | string | Filter: `class`, `method`, `interface`, `enum`, etc. |
| `file_path` | string | Filter by source file path |
| `limit` | int | Max results (1-1000, default 100) |
| `offset` | int | Pagination offset (default 0) |

**Response (200):**
```json
[
  {
    "id": 1,
    "kind": "class",
    "name": "UserService",
    "fq_name": "MyApp.Services.UserService",
    "file_path": "Services/UserService.cs",
    "start_line": 5,
    "end_line": 45,
    "namespace": "MyApp.Services",
    "parent_fq_name": null,
    "signature": "public class UserService : IUserService",
    "modifiers": "public",
    "return_type": ""
  }
]
```

---

#### `GET /repos/{repo_id}/snapshots/{snapshot_id}/symbols/{fq_name}`
Get a single symbol by fully-qualified name.

**Example:** `GET /repos/.../symbols/MyApp.Services.UserService.GetById`

---

#### `GET /repos/{repo_id}/snapshots/{snapshot_id}/edges`
List edges (relationships) between symbols.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `edge_type` | string | Filter: `calls`, `contains`, `implements`, `inherits`, `imports` |
| `source` | string | Filter by source symbol fq_name |
| `target` | string | Filter by target symbol fq_name |
| `limit` | int | Max results (1-1000, default 100) |
| `offset` | int | Pagination offset (default 0) |

---

#### `GET /repos/{repo_id}/snapshots/{snapshot_id}/graph/{fq_name}`
Get the call graph neighborhood for a symbol.

**Response (200):**
```json
{
  "symbol": { "id": 1, "name": "UserService", "kind": "class", ... },
  "callers": [ ... ],
  "callees": [ ... ],
  "children": [ ... ]
}
```

---

#### `GET /repos/{repo_id}/snapshots/{snapshot_id}/overview`
High-level analysis summary.

**Response (200):**
```json
{
  "snapshot_id": "x1y2z3w4a5b6",
  "total_symbols": 156,
  "total_edges": 423,
  "total_modules": 8,
  "symbols_by_kind": {
    "class": 24,
    "method": 98,
    "interface": 12,
    "property": 18,
    "field": 4
  },
  "entry_points": [],
  "hotspots": []
}
```

---

## 9. Analysis Engine Deep Dive

### How tree-sitter Works

Tree-sitter is an incremental parsing library that builds **concrete syntax trees** (CSTs). Unlike traditional parsers that fail on syntax errors, tree-sitter:

1. **Parses in one pass** - no separate lexing step
2. **Handles errors gracefully** - inserts `ERROR` nodes but keeps parsing
3. **Is language-agnostic** - grammars are generated from declarative rules
4. **Is fast** - written in C, parses megabyte files in milliseconds

We use the `tree-sitter-c-sharp` grammar which supports C# 12 syntax.

### AST Node Structure (Example)

For this C# code:
```csharp
namespace MyApp {
    public class Foo : IBar {
        public void Baz(int x) { Console.WriteLine(x); }
    }
}
```

Tree-sitter produces:
```
compilation_unit
  namespace_declaration
    identifier [field=name]: "MyApp"
    declaration_list
      class_declaration
        modifier: public
        identifier [field=name]: "Foo"
        base_list
          identifier: "IBar"
        declaration_list
          method_declaration
            modifier: public
            predefined_type [field=returns]: "void"
            identifier [field=name]: "Baz"
            parameter_list
              parameter
                predefined_type [field=type]: "int"
                identifier [field=name]: "x"
            block
              expression_statement
                invocation_expression
                  member_access_expression [field=function]
                    identifier: "Console"
                    identifier [field=name]: "WriteLine"
                  argument_list
                    argument
                      identifier: "x"
```

### Parser Field Mappings

Key tree-sitter C# field conventions our parser relies on:

| Node Type | Field | Contains |
|-----------|-------|----------|
| `namespace_declaration` | `name` | Namespace identifier |
| `class_declaration` | `name` | Class name |
| `method_declaration` | `name` | Method name |
| `method_declaration` | `returns` | Return type |
| `property_declaration` | `name` | Property name |
| `property_declaration` | `type` | Property type |
| `parameter` | `name` | Parameter name |
| `parameter` | `type` | Parameter type |
| `invocation_expression` | `function` | Called function/method |
| `constructor_declaration` | `name` | Constructor name |

### Graph Neighborhood Algorithm

The `get_neighborhood()` method uses BFS expansion:

```
Input: fq_name, depth (default=2)

visited = {fq_name}
frontier = {fq_name}

for each hop (1..depth):
    next_frontier = {}
    for each symbol in frontier:
        for neighbor in callers(symbol) + callees(symbol):
            if neighbor not in visited:
                visited.add(neighbor)
                next_frontier.add(neighbor)
    frontier = next_frontier

return visited
```

This is used to expand the "blast radius" of a change - if a method is modified, what else might be affected within N hops?

---

## 10. Testing Strategy

### Test Architecture

Tests use **in-memory SQLite** (via `aiosqlite`) to avoid requiring a running PostgreSQL instance. A shared `conftest.py` provides:

- A single test engine and session factory
- `create_tables()` / `drop_tables()` fixtures for DB setup/teardown
- `override_get_db()` dependency override for FastAPI

Background tasks (git clone, etc.) are **mocked** in API tests to keep them fast and deterministic.

### Test Coverage Summary

| Test File | Tests | What's Covered |
|-----------|-------|----------------|
| `test_api.py` | 11 | Repo CRUD, ingestion trigger, snapshot status, validation errors, 404s |
| `test_analysis_api.py` | 21 | Symbol CRUD, edge filtering, graph neighborhood, overview, pagination, error handling |
| `test_csharp_parser.py` | 35 | Every symbol type, modifiers, parameters, return types, signatures, nested types, using directives, call edges, object creation, inheritance, edge cases (empty files, malformed code, comments-only) |
| `test_graph_builder.py` | 17 | Multi-file graph, callers/callees, children, fan-in/out, BFS neighborhood (depth 0/1/2), module grouping, symbol filtering by kind/file, empty graph |
| `test_entry_points.py` | 13 | Controller + action detection, route inference, Main methods, Startup classes, workers (BackgroundService + IHostedService), combined multi-file detection, sort order, no-entry-point case |
| `test_metrics.py` | 9 | LOC computation, sort order, child count, fan-out, public/static flags, hotspot detection with thresholds |
| `test_pipeline.py` | 9 | End-to-end: disk files ? analysis ? DB persistence, symbol/edge verification, field correctness, missing file handling, empty input |
| `test_ingestion.py` | 3 | Language detection, SHA-256 hashing, file scanning with skip dirs and size limits |
| **Total** | **117** | |

### Test Design Principles

1. **Each test file mirrors a source module** - easy to find related tests
2. **Test classes group by feature** - `TestBasicParsing`, `TestEdgeExtraction`, etc.
3. **C# source fixtures are defined as byte literals** at the top of test files
4. **No external dependencies** - no network, no Docker, no git repos needed
5. **Deterministic** - same input always produces same output
6. **Fast** - full suite runs in ~4 seconds

---

## 11. Project Structure

```
backend/
??? pyproject.toml                  # Dependencies, tool config (ruff, mypy, pytest)
??? app/
?   ??? __init__.py
?   ??? main.py                     # FastAPI app, lifespan, router registration
?   ??? api/
?   ?   ??? __init__.py
?   ?   ??? repos.py                # POST /repos, POST /ingest, GET /status, GET /snapshots
?   ?   ??? analysis.py             # GET /symbols, /edges, /graph, /overview
?   ??? core/
?   ?   ??? __init__.py
?   ?   ??? config.py               # Settings (DB URL, Redis, Qdrant, OpenAI key, paths)
?   ?   ??? ingestion.py            # clone_repo, scan_files, detect_language, hash_file
?   ?   ??? tasks.py                # run_ingestion background task (clone + scan + analyze)
?   ??? analysis/
?   ?   ??? __init__.py             # Package docstring
?   ?   ??? models.py               # SymbolInfo, EdgeInfo, FileAnalysis, ModuleInfo, EntryPoint
?   ?   ??? csharp_parser.py        # tree-sitter C# parser (parse_file, parse_file_from_path)
?   ?   ??? graph_builder.py        # CodeGraph (adjacency lists, BFS, modules)
?   ?   ??? entry_points.py         # detect_entry_points (controllers, Main, Startup, workers)
?   ?   ??? metrics.py              # compute_metrics, find_hotspots
?   ?   ??? pipeline.py             # analyze_snapshot_files, persist_graph
?   ??? indexing/
?   ?   ??? __init__.py             # [Phase 3 placeholder]
?   ??? reasoning/
?   ?   ??? __init__.py             # [Phase 4 placeholder]
?   ??? reviews/
?   ?   ??? __init__.py             # [Phase 5 placeholder]
?   ??? storage/
?       ??? __init__.py
?       ??? database.py             # SQLAlchemy async engine, session factory, get_db
?       ??? models.py               # ORM: Repo, RepoSnapshot, File, Symbol, Edge
?       ??? schemas.py              # Pydantic: RepoOut, SymbolOut, EdgeOut, GraphNeighborhood, etc.
??? tests/
?   ??? __init__.py
?   ??? conftest.py                 # Shared test DB (SQLite), fixtures
?   ??? test_api.py                 # Repo API tests
?   ??? test_analysis_api.py        # Analysis API tests
?   ??? test_csharp_parser.py       # Parser unit tests
?   ??? test_graph_builder.py       # Graph builder tests
?   ??? test_entry_points.py        # Entry point detection tests
?   ??? test_metrics.py             # Metrics computation tests
?   ??? test_pipeline.py            # End-to-end pipeline tests
?   ??? test_ingestion.py           # File scanning tests
infra/
?   ??? docker-compose.yml          # Postgres + Redis + Qdrant
.github/
?   ??? workflows/
?       ??? ci.yml                  # Lint + type check + test
README.md                           # Quick start guide
docs/
    ??? ARCHITECTURE.md             # This file
```

---

## 12. Getting Started

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for infrastructure)
- Git

### Local Development

```bash
# 1. Start infrastructure services
docker compose -f infra/docker-compose.yml up -d

# 2. Install the backend with dev dependencies
cd backend
cp .env.example .env   # then edit .env with your settings
pip install -e ".[dev]"

# 3. Run database migrations
alembic upgrade head

# 4. Run the API server
uvicorn app.main:app --reload --port 8000

# 5. Run the test suite
pytest -v

# 6. Run linting
ruff check .

# 7. Run type checking
mypy app --ignore-missing-imports
```

### One-command Docker Start

```bash
# Start everything (postgres, redis, qdrant, api) in one command:
docker compose -f infra/docker-compose.yml up -d --build
# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### Quick Smoke Test

```bash
# Register a repo
curl -X POST http://localhost:8000/repos \
  -H "Content-Type: application/json" \
  -d '{"name": "dotnet-sample", "url": "https://github.com/dotnet/samples"}'

# Trigger ingestion (replace {id} with the returned repo ID)
curl -X POST http://localhost:8000/repos/{id}/ingest

# Check status
curl http://localhost:8000/repos/{id}/status

# Once completed, explore symbols
curl "http://localhost:8000/repos/{id}/snapshots/{snap_id}/symbols?kind=class"

# Get call graph for a symbol
curl "http://localhost:8000/repos/{id}/snapshots/{snap_id}/graph/Namespace.ClassName"
```

---

## 13. Configuration

All settings are managed via environment variables (prefix `EIDOS_`) or a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `EIDOS_DATABASE_URL` | `postgresql+asyncpg://eidos:eidos@localhost:5432/eidos` | PostgreSQL connection string |
| `EIDOS_REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `EIDOS_QDRANT_URL` | `http://localhost:6333` | Qdrant vector DB URL |
| `EIDOS_OPENAI_API_KEY` | `""` | OpenAI API key (for future LLM features) |
| `EIDOS_REPOS_DATA_DIR` | `/data/repos` | Directory for cloned repositories |

---

## 14. Design Decisions

### Why tree-sitter instead of Roslyn?

| Factor | tree-sitter | Roslyn |
|--------|------------|--------|
| **Runtime** | Pure C, Python bindings | Requires .NET SDK |
| **Speed** | Microseconds per file | Seconds for project load |
| **Error tolerance** | Parses malformed code | Fails on syntax errors |
| **Deployment** | pip install | Separate dotnet tool |
| **Trade-off** | No semantic analysis (type resolution) | Full semantic model |

We chose tree-sitter for MVP because:
1. No .NET runtime dependency in the Python backend
2. Fast enough for interactive use
3. Error-tolerant (important for legacy/partial code)
4. Call targets are captured as unresolved names (sufficient for graph building)

**Limitation:** Without type resolution, `GetById` in a call edge might match multiple methods across classes. This is acceptable for MVP and can be improved with heuristic resolution later.

### Why symbol-based chunking?

Instead of arbitrary line-based or token-based chunking (common in RAG systems), we chunk by **code symbols** (methods, classes). This means:
- Every chunk has a clear identity (fq_name)
- Citations point to real code entities, not arbitrary ranges
- Graph edges connect meaningful units

### Why snapshot-based indexing?

Each ingestion creates an immutable snapshot tied to a commit SHA. This allows:
- Comparing analysis across commits
- Knowing exactly what code the analysis reflects
- Safe re-indexing without data corruption

### Why in-memory SQLite for tests?

- **Fast:** No database server needed, tests run in ~4 seconds
- **Isolated:** Each test gets fresh tables
- **CI-friendly:** No Docker required in the test pipeline
- **Trade-off:** SQLite doesn't support all PostgreSQL features (e.g., ENUM types behave differently), but SQLAlchemy abstracts this sufficiently

---

## 15. What's Next

### Phase 3 - Summarization & Indexing (Next)

- Deterministic facts extraction per symbol (no AI)
- LLM-generated structured summaries (purpose, inputs, outputs, side effects, risks)
- Vector embeddings of summaries in Qdrant
- Hybrid retrieval: vector search + graph expansion

### Phase 4 - Explain / Q&A

- Question router (architecture / flow / component / impact)
- Graph-augmented retrieval (vector search seeds, graph broadens)
- Structured responses with citations and confidence

### Phase 5 - PR Review

- Diff parsing and changed-line-to-symbol mapping
- Impact expansion via call graph
- Behavioral heuristics (removed validations, changed conditions, etc.)
- LLM risk reasoning with evidence

---

*Last updated: Phase 2 completion*
*Test count: 117 passing*
*Lines of production code: ~1,200*
*Lines of test code: ~1,100*
