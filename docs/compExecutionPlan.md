# Company-Constrained Execution Plan

> What we can build RIGHT NOW on the company PC.
> No LLM APIs, no Docker, no external services, no new pip installs that require approval.

## Constraints

| Resource | Available | Not Available |
|----------|-----------|---------------|
| Python 3.14 | Yes | - |
| tree-sitter (all 9 grammars) | Yes | - |
| SQLAlchemy + aiosqlite | Yes | PostgreSQL (no server) |
| FastAPI + uvicorn | Yes | - |
| httpx | Yes | External API calls (blocked) |
| GitPython | Yes | - |
| redis (library) | Yes | Redis server (no Docker) |
| tomllib (stdlib) | Yes | - |
| xml.etree (stdlib) | Yes | - |
| ast (stdlib) | Yes | - |
| statistics (stdlib) | Yes | - |
| LLM (OpenAI/Ollama) | No | Company policy |
| Docker | No | Company policy |
| pip install new packages | Risky | Needs approval |

**Everything below uses ONLY what is already installed or stdlib.**

---

## Phase 1: Cyclomatic & Cognitive Complexity (Pure Tree-Sitter)

**Effort: 8 hours | Impact: High | Dependencies: None**

We already parse every function's AST with tree-sitter. Complexity is just counting nodes.

### 1.1 Cyclomatic Complexity Calculator

Count decision points in each function's AST subtree:

| Node Type | Languages | Weight |
|-----------|-----------|--------|
| `if_statement` | All | +1 |
| `for_statement` / `for_in_statement` | All | +1 |
| `while_statement` | All | +1 |
| `case` / `switch_case` | Java, C#, C, C++, Go, TS | +1 |
| `catch_clause` | Java, C#, TS, C++ | +1 |
| `conditional_expression` (ternary) | All | +1 |
| `binary_expression` with `&&` or `\|\|` | All | +1 |
| `match_arm` | Rust | +1 |
| `select_statement` | Go | +1 |

Implementation: Walk the tree-sitter subtree for each function node. Count matching node types. Store on the `Symbol` model.

### 1.2 Cognitive Complexity Calculator

Like cyclomatic but penalizes nesting:

```
Base: +1 for each control flow keyword
Nesting: +1 extra for each nesting level
Penalty: +1 for recursion (function calls itself)
```

### 1.3 New DB Columns

Add to `Symbol` model:
```python
cyclomatic_complexity: int = 0
cognitive_complexity: int = 0
```

### 1.4 New Health Rules (5 rules)

| Rule ID | Name | Trigger | Severity |
|---------|------|---------|----------|
| `CX001` | `high_cyclomatic` | CC > 15 | warning |
| `CX002` | `very_high_cyclomatic` | CC > 30 | error |
| `CX003` | `high_cognitive` | CogC > 20 | warning |
| `CX004` | `very_high_cognitive` | CogC > 40 | error |
| `CX005` | `complexity_ratio` | CC / LOC > 0.5 | warning |

### 1.5 New API Endpoint

```
GET /repos/{id}/snapshots/{sid}/metrics
```

Returns per-function complexity + aggregates per file and per module.

### 1.6 Tests

~30 tests: one per language with known complexity, edge cases (nested loops, switch, ternary chains).

---

## Phase 2: Dependency File Parsing (Pure Stdlib)

**Effort: 10 hours | Impact: High | Dependencies: tomllib (stdlib), xml.etree (stdlib)**

No external API calls needed. We just parse manifest files that are already cloned.

### 2.1 Manifest Parsers

| File | Language | Parser | Stdlib |
|------|----------|--------|--------|
| `requirements.txt` | Python | regex line-by-line | Yes |
| `pyproject.toml` `[project.dependencies]` | Python | `tomllib` | Yes |
| `setup.cfg` | Python | `configparser` | Yes |
| `package.json` `dependencies/devDependencies` | JS/TS | `json` | Yes |
| `pom.xml` `<dependency>` | Java | `xml.etree` | Yes |
| `build.gradle` | Java | regex | Yes |
| `go.mod` `require (...)` | Go | regex | Yes |
| `Cargo.toml` `[dependencies]` | Rust | `tomllib` | Yes |
| `*.csproj` `<PackageReference>` | C# | `xml.etree` | Yes |
| `CMakeLists.txt` | C/C++ | regex | Yes |
| `vcpkg.json` | C/C++ | `json` | Yes |

### 2.2 Dependency Model

```python
class Dependency(Base):
    snapshot_id: str
    name: str            # "requests", "lodash", "serde"
    version: str         # "2.28.0", "^4.17", ">=1.0"
    ecosystem: str       # "pypi", "npm", "maven", "crates", "go", "nuget"
    file_path: str       # "requirements.txt"
    is_dev: bool         # dev dependency or production
    is_pinned: bool      # exact version vs range
```

### 2.3 Dependency Health Rules (5 rules, no network needed)

| Rule ID | Name | Check | Severity |
|---------|------|-------|----------|
| `DEP001` | `unpinned_dependency` | Version is `*`, `latest`, or missing | warning |
| `DEP002` | `wide_version_range` | Range spans >1 major version | info |
| `DEP003` | `unused_dependency` | Declared but never imported in source | warning |
| `DEP004` | `duplicate_dependency` | Same package in multiple manifest files | info |
| `DEP005` | `dev_in_production` | Dev dependency imported in non-test code | warning |

`DEP003` (unused dependency) cross-references the import edges from the code graph with the manifest. This is uniquely powerful because we already have the full import graph.

### 2.4 New API Endpoints

```
GET  /repos/{id}/snapshots/{sid}/dependencies
GET  /repos/{id}/snapshots/{sid}/dependencies/unused
```

### 2.5 Integration into Ingestion Pipeline

During `scan_files()`, detect manifest files. Parse them in `analyze_snapshot_files()` alongside source code.

### 2.6 Tests

~40 tests: real manifest files from the 18 repos we already validate against. Every ecosystem covered.

---

## Phase 3: Git Blame / Churn Analysis (GitPython, Already Installed)

**Effort: 8 hours | Impact: High | Dependencies: GitPython (already installed)**

GitPython is already in `pyproject.toml`. We already clone repos. Adding blame is just more git commands on the clone.

### 3.1 Blame Extraction

During ingestion, after cloning:

```python
repo = git.Repo(clone_path)
for file in source_files:
    blame = repo.blame("HEAD", file.path)
    # blame returns: [(commit, [lines]), ...]
```

Extract per-function:
- `last_author`: who last touched it
- `last_modified`: when
- `author_count`: how many distinct authors
- `commit_count`: total commits touching this function (churn)

### 3.2 New DB Columns on Symbol

```python
last_author: str = ""
last_modified: datetime | None = None
author_count: int = 0
commit_count: int = 0
```

### 3.3 Churn Health Rules (4 rules)

| Rule ID | Name | Check | Severity |
|---------|------|-------|----------|
| `GB001` | `hotspot` | commit_count > 10 AND cyclomatic_complexity > 15 | warning |
| `GB002` | `stale_code` | last_modified > 1 year AND no callers | info |
| `GB003` | `bus_factor` | author_count == 1 across entire module (>5 files) | warning |
| `GB004` | `recent_churn` | >5 commits in last 7 days on a single function | info |

### 3.4 New API Endpoints

```
GET /repos/{id}/snapshots/{sid}/contributors
GET /repos/{id}/snapshots/{sid}/hotspots
```

`/contributors` returns per-author stats: files touched, symbols owned, modules.
`/hotspots` returns functions sorted by `commit_count * complexity` (churn x risk).

### 3.5 Tests

~25 tests: mock git blame output, verify extraction, verify health rules fire correctly.

---

## Phase 4: Dead Code Detection (Pure Graph Analysis)

**Effort: 5 hours | Impact: Medium | Dependencies: None**

We already have the full call graph. Dead code = symbols with zero incoming edges.

### 4.1 Enhanced Dead Code Analysis

Current rule `SM001` checks for uncalled methods. Enhance it:

| Check | What It Finds |
|-------|--------------|
| Unreachable classes | Class never instantiated and not inherited |
| Unreachable modules | File never imported by any other file |
| Dead parameters | Parameter never used in function body (tree-sitter) |
| Dead imports | Import statement where imported symbol is never referenced |
| Orphan test files | Test file testing a class that no longer exists |

### 4.2 Reachability Analysis from Entry Points

The overview already detects `entry_points`. Build a reachability set:

```
reachable = BFS from all entry_points following call edges
dead = all_symbols - reachable
```

This finds deep dead code that simple "no callers" misses: A calls B calls C, but nothing calls A.

### 4.3 New API Endpoint

```
GET /repos/{id}/snapshots/{sid}/dead-code
```

Returns dead symbols grouped by: unreachable classes, unreachable functions, dead imports, dead modules.

### 4.4 Tests

~20 tests with synthetic graphs and real repo validation.

---

## Phase 5: Duplicate / Clone Detection (Pure AST)

**Effort: 6 hours | Impact: Medium | Dependencies: None**

Detect copy-pasted code using AST structure fingerprinting. No LLM needed.

### 5.1 AST Fingerprinting

For each function, compute a structural hash:
1. Walk the tree-sitter AST
2. Record node types only (ignore identifiers and literals)
3. Hash the sequence

Two functions with the same structural hash are clones (logic identical, names different).

### 5.2 Near-Clone Detection

For functions >10 lines:
1. Split AST into sliding windows of 5 statements
2. Hash each window
3. Functions sharing >60% of windows are near-clones

### 5.3 New Health Rules (3 rules)

| Rule ID | Name | Check | Severity |
|---------|------|-------|----------|
| `DUP001` | `exact_clone` | Identical AST structure | warning |
| `DUP002` | `near_clone` | >60% structural overlap | info |
| `DUP003` | `clone_cluster` | >3 clones of the same function | error |

### 5.4 New API Endpoint

```
GET /repos/{id}/snapshots/{sid}/clones
```

Returns clone groups: `[{fingerprint, functions: [{fq_name, file, lines}]}]`

### 5.5 Tests

~15 tests with real duplicate code patterns from the validated repos.

---

## Phase 6: Module Coupling & Cohesion Metrics (Pure Graph)

**Effort: 5 hours | Impact: Medium | Dependencies: None**

We have all edges. Coupling and cohesion are graph computations.

### 6.1 Coupling Score

For each module (directory):
- **Afferent coupling (Ca)**: number of external modules that depend on this module
- **Efferent coupling (Ce)**: number of external modules this module depends on
- **Instability**: `Ce / (Ca + Ce)` (0 = stable, 1 = unstable)

### 6.2 Cohesion Score

For each module:
- Count internal edges (symbols calling other symbols in same module)
- Count total edges involving module symbols
- **Cohesion**: `internal_edges / total_edges` (1 = perfectly cohesive)

### 6.3 Abstractness

For each module:
- Count abstract symbols (interfaces, abstract classes)
- Count total symbols
- **Abstractness**: `abstract / total`

### 6.4 Distance from Main Sequence

Robert C. Martin's metric: `|Abstractness + Instability - 1|`

0 = ideal. >0.5 = zone of pain (too concrete + too stable) or zone of uselessness (too abstract + too unstable).

### 6.5 New Health Rules (4 rules)

| Rule ID | Name | Check | Severity |
|---------|------|-------|----------|
| `MC001` | `high_coupling` | Ce > 10 | warning |
| `MC002` | `low_cohesion` | cohesion < 0.3 | warning |
| `MC003` | `zone_of_pain` | distance > 0.7 AND abstractness < 0.2 | warning |
| `MC004` | `circular_dependency` | Module A imports B imports A | error |

### 6.6 New API Endpoint

```
GET /repos/{id}/snapshots/{sid}/coupling
```

Returns per-module: Ca, Ce, instability, cohesion, abstractness, distance.

### 6.7 Tests

~20 tests using real data from the 18 validated repos.

---

## Phase 7: Refactor the 33 Long Functions

**Effort: 8 hours | Impact: Medium (maintainability) | Dependencies: None**

Break down each function into well-named helpers. Target: every function under 40 lines.

### Top 10 Targets (by line count)

| # | Function | Lines | File | Strategy |
|---|----------|-------|------|----------|
| 1 | `parse_unified_diff()` | 133 | `reviews/diff_parser.py` | Extract `_parse_hunk()`, `_parse_file_header()` |
| 2 | `_build_section()` | 129 | `docgen/generator.py` | Extract per-section-type builders |
| 3 | `search()` | 123 | `api/search.py` | Extract `_build_search_query()`, `_rank_results()` |
| 4 | `run_ingestion()` | 122 | `core/tasks.py` | Extract `_clone_phase()`, `_parse_phase()`, `_index_phase()` |
| 5 | `run_indexing()` | 119 | `indexing/indexer.py` | Extract `_build_summaries()`, `_embed_summaries()` |
| 6 | `export_snapshot()` | 96 | `api/search.py` | Extract `_serialize_symbols()`, `_serialize_edges()` |
| 7 | `_build_deterministic_answer()` | 95 | `reasoning/answer_builder.py` | Extract `_gather_evidence()`, `_format_answer()` |
| 8 | `generate_flow_doc()` | 91 | `docgen/generator.py` | Extract `_trace_http_flows()`, `_trace_event_flows()` |
| 9 | `_class_diagram()` | 88 | `api/diagrams.py` | Extract `_collect_diagram_nodes()`, `_render_mermaid()` |
| 10 | `health_trend()` | 86 | `api/trends.py` | Extract `_compute_trend_data()` |

### Remaining 23

Same pattern. Each session: pick 3-5 functions, extract helpers, run tests, commit.

---

## Phase 8: API Endpoint Gaps

**Effort: 6 hours | Impact: Medium | Dependencies: None**

Endpoints that are missing but the data already exists in the DB.

### 8.1 GET /repos (list all repos)

Currently missing. The frontend needs a repo list page.

```python
@router.get("", response_model=list[RepoOut])
async def list_repos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Repo))
    return result.scalars().all()
```

### 8.2 GET /repos/{id}/snapshots (list snapshots)

Currently only available via `/status`. Add a dedicated paginated endpoint.

### 8.3 DELETE /repos/{id}/snapshots/{sid}

Allow deleting old snapshots to free storage.

### 8.4 GET /repos/{id}/snapshots/{sid}/files

List all files in a snapshot with language, size, hash. Useful for file browser in frontend.

### 8.5 GET /repos/{id}/snapshots/{sid}/symbols/{fq}/callers

Dedicated endpoint for "who calls this function?" Easier than parsing the full edge list client-side.

### 8.6 PATCH /repos/{id}/snapshots/{sid}/symbols/{fq}/notes

Allow users to annotate symbols with notes. New `SymbolNote` model. Simple CRUD.

---

## Phase 9: Export Enhancements (Pure Python)

**Effort: 4 hours | Impact: Low-Medium | Dependencies: None (stdlib csv, json)**

### 9.1 CSV Export

```
GET /repos/{id}/snapshots/{sid}/export/csv
```

Returns a ZIP with:
- `symbols.csv`
- `edges.csv`
- `health_findings.csv`
- `dependencies.csv` (if Phase 2 done)

Teams want spreadsheets.

### 9.2 SARIF Export

```
GET /repos/{id}/snapshots/{sid}/export/sarif
```

SARIF (Static Analysis Results Interchange Format) is the standard for GitHub Code Scanning, VS Code, and Azure DevOps. Health findings map directly:

```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [{
    "tool": { "driver": { "name": "Eidos", "rules": [...] } },
    "results": [...]
  }]
}
```

This lets users see Eidos findings directly in GitHub PR checks and VS Code.

### 9.3 Markdown Report Export

```
GET /repos/{id}/snapshots/{sid}/export/report
```

Returns a single Markdown file: executive summary, health score, top findings, class diagram, contributor stats. Drop-in for a README or wiki page.

---

## Priority Matrix

| Phase | Feature | Effort | Impact | Blocked? |
|-------|---------|--------|--------|----------|
| **1** | Complexity Metrics | 8h | High (industry standard) | ? DONE |
| **2** | Dependency Parsing | 10h | High (security value) | ? DONE |
| **3** | Git Blame / Churn | 8h | High (team insights) | ? DONE |
| **4** | Dead Code Detection | 5h | Medium (cleanup value) | No |
| **5** | Clone Detection | 6h | Medium (DRY enforcement) | No |
| **6** | Coupling & Cohesion | 5h | Medium (architecture) | No |
| **7** | Refactor Long Funcs | 8h | Medium (maintainability) | No |
| **8** | API Endpoint Gaps | 6h | Medium (frontend needs) | No |
| **9** | Export Enhancements | 4h | Low-Medium (integration) | No |
| | **TOTAL** | **60h** | | **Nothing blocked** |

---

## Execution Timeline

```
Week 1 (Mon-Fri):
  Day 1-2: Phase 1 - Complexity metrics (tree-sitter node counting)
  Day 3-4: Phase 2 - Dependency parsing (tomllib, xml, json, regex)
  Day 5:   Phase 3 start - Git blame extraction

Week 2 (Mon-Fri):
  Day 1:   Phase 3 finish - Churn rules + API endpoints
  Day 2:   Phase 4 - Dead code detection (graph BFS)
  Day 3:   Phase 5 - Clone detection (AST fingerprinting)
  Day 4:   Phase 6 - Coupling & cohesion (graph math)
  Day 5:   Phase 8 - API endpoint gaps

Week 3 (Mon-Wed):
  Day 1-2: Phase 7 - Refactor long functions (top 15)
  Day 3:   Phase 9 - Export enhancements (CSV, SARIF, Markdown)

Total: 12 working days = 2.5 weeks
```

---

## Expected Results After Execution

| Metric | Before | After |
|--------|--------|-------|
| Health rules | 40 | 61 (+21 new rules) |
| API endpoints | 55 | 65 (+10 new endpoints) |
| Tests | 1,818 | ~2,020 (+200 new tests) |
| Lines of code | 40,537 | ~45,000 |
| Long functions (>60 lines) | 33 | <5 |
| Metrics computed | 0 | 3 (cyclomatic, cognitive, maintainability) |
| Ecosystems parsed | 0 | 7 (pypi, npm, maven, crates, go, nuget, cmake) |
| Clone detection | No | Yes (exact + near clones) |
| Git analytics | No | Yes (blame, churn, bus factor, hotspots) |
| Export formats | 2 (JSON, .eidos) | 5 (+CSV, SARIF, Markdown report) |
| Coupling metrics | No | Yes (Ca, Ce, instability, cohesion, abstractness) |

---

## What This Does NOT Cover (Needs Personal Machine)

These remain for when you can use LLM/Docker on your personal machine:

| Feature | Why Blocked | Where Documented |
|---------|-------------|-----------------|
| Wire LLM (Q&A, docs, reviews) | Company policy: no LLM API calls | `docs/EXECUTION_PLAN.md` Phase 1 |
| Redis cache | No Redis server (no Docker) | `docs/EXECUTION_PLAN.md` Phase 2 |
| Vulnerability scanning (OSV API) | External API calls blocked | `docs/EXECUTION_PLAN.md` Phase 3.2 |
| Scheduled analysis (APScheduler) | Would need `pip install` approval | `docs/EXECUTION_PLAN.md` Phase 8 |
| Notifications (Slack/email) | External API calls blocked | `docs/EXECUTION_PLAN.md` Phase 7 |
| Docker deployment | Company policy | - |
