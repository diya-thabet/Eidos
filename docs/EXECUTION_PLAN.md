# Execution Plan: What To Build Next

> Generated from a deep scan of the entire backend codebase.
> Priority is based on impact-to-effort ratio. Items marked with a lightning bolt are the highest leverage.

---

## Current State (Baseline)

| Metric | Value |
|--------|-------|
| App code | 19,413 lines across 100 files |
| Tests | 1,818 (CI-verified) |
| API endpoints | 55 |
| Language parsers | 9 (all validated) |
| Health rules | 40 |
| Long functions (>60 lines) | 33 remaining |

### What Works Well
- Parsing, graph building, health checks, search, diagrams, export/import: production-ready
- Auth, API keys, webhooks, metrics: fully functional
- Test coverage: 1.09:1 ratio

### What Does Not Work Without an LLM
- **Q&A answers**: returns empty `answer_text`, `confidence: "low"`
- **Doc generation**: generates skeleton docs only (no summaries, no explanations)
- **Review summaries**: `llm_summary: null` in every review
- **Health insights**: `llm_insights: null`
- **Embeddings**: falls back to SHA-256 hash (not semantic)
- **Summaries**: `StubSummariser` returns facts only, no natural language

---

## Phase 1: Wire the LLM (Highest Impact)

**Why**: Every premium feature (Q&A, docs, reviews, summaries) is architecturally complete but produces empty output without an LLM. Wiring this unlocks 40% of the product's value in one move.

### 1.1 Wire OpenAI Embedder (2 hours)

The `OpenAIEmbedder` class exists but falls back to hash. Wire it to the real API.

**File**: `app/indexing/embedder.py` (lines 73-93)

```
Current:  OpenAIEmbedder.embed() -> HashEmbedder fallback
Target:   OpenAIEmbedder.embed() -> openai.embeddings.create()
```

**What it unlocks**: Semantic search. "find functions that handle authentication" will find `verify_jwt_token()` even though "authentication" never appears in the name.

### 1.2 Wire OpenAI Summariser (3 hours)

The `Summariser` ABC and `StubSummariser` exist. Build `OpenAISummariser`.

**File**: `app/indexing/summarizer.py` (line 130-134, `create_summariser()` factory)

```
Current:  create_summariser() -> StubSummariser (facts only)
Target:   create_summariser(api_key) -> OpenAISummariser (real NL summaries)
```

**What it unlocks**: Every symbol and module gets a human-readable summary. Doc generation becomes useful. Q&A retrieval gets richer context.

### 1.3 Wire LLM into Q&A Answer Builder (2 hours)

The prompt template and evidence retrieval are built. The `_build_llm_answer()` function at `app/reasoning/answer_builder.py:176` works but is never reached because `StubLLMClient` is detected.

```
Current:  Always takes deterministic path (line 73)
Target:   With API key set, takes LLM path with full prompt + evidence
```

**What it unlocks**: Real natural-language answers to code questions with citations.

### 1.4 Wire LLM into Review Summaries (1 hour)

`app/reviews/reviewer.py:144` already has the LLM branch. Just needs the client to not be a stub.

### 1.5 Wire LLM into Doc Generation (2 hours)

`app/docgen/orchestrator.py:165` already checks for a real LLM. The generation pipeline is complete.

### 1.6 Wire LLM into Health Insights (1 hour)

`app/analysis/code_health.py:348` `run_llm_health_analysis()` is built. Just needs a real client.

**Total Phase 1 effort: ~11 hours. Unlocks: 6 major features.**

---

## Phase 2: Caching Layer (Massive Performance Boost)

**Why**: Every API call re-computes everything from the database. A cache layer eliminates 90% of redundant work.

### 2.1 Add Redis Cache for Analysis Results (4 hours)

Redis is already in `pyproject.toml` dependencies.

**Cache these hot paths**:

| Endpoint | Key Pattern | TTL |
|----------|-------------|-----|
| `GET /overview` | `overview:{snapshot_id}` | forever (snapshot is immutable) |
| `POST /health` | `health:{snapshot_id}:{config_hash}` | forever |
| `GET /diagram` | `diagram:{snapshot_id}:{type}` | forever |
| `GET /export` | `export:{snapshot_id}` | forever |
| `GET /search` | `search:{snapshot_id}:{query_hash}` | 1 hour |

Snapshots are immutable once completed, so most caches never need invalidation.

### 2.2 Cache LLM Responses (2 hours)

LLM calls are expensive ($0.01-0.10 per call). Cache responses keyed by `(snapshot_id, prompt_hash)`.

**What it unlocks**: First Q&A call takes 2-5 seconds. Every subsequent identical question is instant.

**Total Phase 2 effort: ~6 hours. Unlocks: 10x faster responses, 90% cost reduction.**

---

## Phase 3: Dependency Analysis (New Feature, High Value)

**Why**: The graph currently tracks calls/inherits/imports. Adding dependency analysis (package.json, requirements.txt, pom.xml, go.mod, Cargo.toml) is what security-conscious companies pay for.

### 3.1 Dependency File Parsers (8 hours)

Parse manifest files and extract dependency trees:

| File | Language | Parser |
|------|----------|--------|
| `requirements.txt` / `pyproject.toml` | Python | regex + toml |
| `package.json` / `package-lock.json` | JS/TS | json |
| `pom.xml` / `build.gradle` | Java | xml + regex |
| `go.mod` | Go | regex |
| `Cargo.toml` | Rust | toml |
| `*.csproj` | C# | xml |
| `CMakeLists.txt` / `vcpkg.json` | C/C++ | regex + json |

### 3.2 Known Vulnerability Check (4 hours)

Query the OSV (Open Source Vulnerabilities) database -- free, no API key needed:

```
POST https://api.osv.dev/v1/query
{ "package": { "name": "requests", "ecosystem": "PyPI" }, "version": "2.28.0" }
```

### 3.3 Dependency Health Rules (3 hours)

Add to the 40-rule health engine:
- `DEP001`: Outdated dependency (>1 year behind latest)
- `DEP002`: Known CVE in dependency
- `DEP003`: Unused dependency (declared but never imported)
- `DEP004`: Pinning violation (unpinned or wildcard version)
- `DEP005`: License incompatibility (GPL in MIT project)

### 3.4 New API Endpoint (2 hours)

```
GET /repos/{id}/snapshots/{sid}/dependencies
POST /repos/{id}/snapshots/{sid}/dependencies/audit
```

**Total Phase 3 effort: ~17 hours. Unlocks: Security scanning, vulnerability alerts, license compliance.**

---

## Phase 4: Code Complexity Metrics (New Feature, Medium Effort)

**Why**: The health rules check structural patterns but don't compute standard industry metrics. Teams want McCabe, Halstead, and maintainability index numbers.

### 4.1 McCabe Cyclomatic Complexity (3 hours)

Count decision points per function (if, for, while, case, &&, ||). Tree-sitter already gives us the AST.

### 4.2 Cognitive Complexity (3 hours)

Sonar's cognitive complexity metric (nesting penalties). More useful than McCabe for modern code.

### 4.3 Maintainability Index (2 hours)

Microsoft's formula: `MI = max(0, (171 - 5.2 * ln(HV) - 0.23 * CC - 16.2 * ln(LOC)) * 100 / 171)`

### 4.4 New API Endpoint (1 hour)

```
GET /repos/{id}/snapshots/{sid}/metrics
```

Returns per-function and per-file complexity scores.

### 4.5 Health Rules Integration (2 hours)

- `CX001`: Cyclomatic complexity > 15
- `CX002`: Cognitive complexity > 20
- `CX003`: Maintainability index < 40
- `CX004`: Function has more branches than lines

**Total Phase 4 effort: ~11 hours. Unlocks: Industry-standard metrics, SonarQube parity.**

---

## Phase 5: Git Blame Integration (New Feature, High Insight Value)

**Why**: Knowing WHO wrote each function and WHEN it was last changed transforms code health from structural analysis into team-level insights.

### 5.1 Blame Data Extraction (4 hours)

During ingestion, run `git blame --porcelain` on each file. Extract:
- Author per line range
- Last commit date per function
- Commit frequency per file (churn)

### 5.2 New Database Columns (2 hours)

Add to `Symbol` model:
- `last_author: str`
- `last_modified: datetime`
- `commit_count: int` (churn)

### 5.3 Churn-Based Health Rules (2 hours)

- `GB001`: Hot spot (>10 commits in last 30 days + high complexity)
- `GB002`: Stale code (no commits in 1 year + no callers)
- `GB003`: Bus factor risk (only 1 author across entire module)

### 5.4 Author Analytics Endpoint (2 hours)

```
GET /repos/{id}/snapshots/{sid}/contributors
```

Returns: contribution per author, modules owned, hotspot ownership.

**Total Phase 5 effort: ~10 hours. Unlocks: Team analytics, ownership maps, bus factor detection.**

---

## Phase 6: Incremental LLM Indexing (Performance)

**Why**: Re-indexing an entire repo is expensive. When only 3 files changed, only re-summarize those 3.

### 6.1 Extend Incremental Pipeline (4 hours)

`app/core/incremental.py` already computes `changed_files`. Extend it to:
1. Only re-summarize changed symbols
2. Only re-embed changed summaries
3. Copy unchanged summaries from previous snapshot

### 6.2 Partial Vector Store Update (3 hours)

Delete old vectors for changed files, insert new ones. Keep everything else.

**Total Phase 6 effort: ~7 hours. Unlocks: 90% faster re-ingestion, 90% cheaper LLM costs.**

---

## Phase 7: Webhook Notifications (New Feature)

**Why**: Users want to know when analysis completes, when health drops, when vulnerabilities are found.

### 7.1 Notification Dispatcher (3 hours)

Abstract notification interface with implementations:
- Slack webhook
- Email (SMTP or SendGrid)
- Microsoft Teams webhook
- Generic HTTP callback

### 7.2 Event Triggers (2 hours)

- Ingestion completed
- Health score dropped >10 points
- New vulnerability found (Phase 3)
- Review risk level = critical

### 7.3 User Notification Preferences (2 hours)

```
GET/PUT /settings/notifications
```

**Total Phase 7 effort: ~7 hours. Unlocks: CI/CD integration, team awareness, automated alerts.**

---

## Phase 8: Scheduled Analysis (New Feature)

**Why**: Users should not have to manually trigger ingestion. Repos should auto-scan on a schedule.

### 8.1 Cron Scheduler (3 hours)

Use APScheduler (already compatible with async). Run on configurable interval per repo.

### 8.2 Per-Repo Schedule Config (2 hours)

```
PATCH /repos/{id} { "schedule": "daily" | "weekly" | "on_push" | "manual" }
```

### 8.3 Health Regression Detection (2 hours)

Compare new snapshot health vs previous. If score drops >5 points, trigger alert.

**Total Phase 8 effort: ~7 hours. Unlocks: Continuous monitoring, regression alerts.**

---

## Phase 9: Refactor Long Functions (Code Quality)

33 functions exceed 60 lines. The worst offenders:

| Function | Lines | File |
|----------|-------|------|
| `parse_unified_diff()` | 133 | `reviews/diff_parser.py` |
| `_build_section()` | 129 | `docgen/generator.py` |
| `search()` | 123 | `api/search.py` |
| `run_ingestion()` | 122 | `core/tasks.py` |
| `run_indexing()` | 119 | `indexing/indexer.py` |
| `export_snapshot()` | 96 | `api/search.py` |
| `_build_deterministic_answer()` | 95 | `reasoning/answer_builder.py` |
| `generate_flow_doc()` | 91 | `docgen/generator.py` |
| `_class_diagram()` | 88 | `api/diagrams.py` |

### Approach

Extract helper functions. Each long function should be <40 lines calling well-named helpers.

**Total Phase 9 effort: ~8 hours. Unlocks: Better maintainability, easier testing.**

---

## Priority Matrix

| Phase | Feature | Effort | Impact | Priority |
|-------|---------|--------|--------|----------|
| 1 | Wire LLM | 11h | Unlocks 6 features (Q&A, docs, reviews, summaries, search, insights) | P0 |
| 2 | Redis Cache | 6h | 10x faster, 90% cheaper | P0 |
| 3 | Dependency Analysis | 17h | Security scanning, vulnerability alerts | P1 |
| 4 | Complexity Metrics | 11h | Industry-standard metrics | P1 |
| 5 | Git Blame | 10h | Team analytics, ownership maps | P1 |
| 6 | Incremental LLM | 7h | 90% faster re-ingestion | P2 |
| 7 | Notifications | 7h | CI/CD integration, alerts | P2 |
| 8 | Scheduled Analysis | 7h | Continuous monitoring | P2 |
| 9 | Refactor Long Funcs | 8h | Maintainability | P3 |

**Total: ~84 hours of development (10-11 working days).**

---

## Execution Timeline

```
Week 1:  Phase 1 (Wire LLM)           + Phase 2 (Redis Cache)         = 17h
Week 2:  Phase 3 (Dependencies)        + Phase 4 (Complexity Metrics)  = 28h
Week 3:  Phase 5 (Git Blame)           + Phase 6 (Incremental LLM)    = 17h
Week 4:  Phase 7 (Notifications)       + Phase 8 (Scheduled Analysis)  = 14h
Week 5:  Phase 9 (Refactor)            + Buffer/polish                 = 8h
```

After 5 weeks: the product goes from "excellent static analysis tool" to "full AI-powered code intelligence platform with security scanning, team analytics, and continuous monitoring."

---

## What NOT to Build (Anti-Priorities)

| Temptation | Why Skip It |
|-----------|-------------|
| Build your own LLM | Use OpenAI/Ollama/vLLM. The LLM client abstraction already supports any provider. |
| GraphQL API | REST is fine. The frontend only needs 55 endpoints, not ad-hoc queries. |
| Real-time WebSocket updates | Polling the status endpoint every 2s during ingestion is simpler and sufficient. |
| Custom vector DB | Qdrant is already integrated and scales independently. |
| Multi-tenant database isolation | Shared-schema with `user_id` filtering is fine up to 10K users. Shard later. |
| Kubernetes operator | Docker Compose is sufficient until you have paying customers. |
