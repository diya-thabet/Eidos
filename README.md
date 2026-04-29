# Eidos — Code Intelligence Platform

# Eidos — Code Intelligence Platform

Analyzes any codebase across **9 languages**, auto-generates documentation with citations, detects code health issues with **66 rules**, computes complexity / coupling / clone metrics, and reviews PRs for logic and behavior risks.

**Supported languages:** C#, Java, Python, TypeScript, Go, Rust, C, C++, Kotlin

## Quick Start

```bash
# 1. Start infrastructure
docker compose -f infra/docker-compose.yml up -d

# 2. Install backend
cd backend
pip install -e ".[dev]"

# 3. Run API
uvicorn app.main:app --reload

# 4. Run tests
pytest -v
```

## Key Capabilities

| Capability | Description |
|-----------|-------------|
| **Multi-language parsing** | 9 tree-sitter parsers extract classes, methods, calls, inheritance |
| **Code health** | 66 rules: complexity, SOLID, clean code, coupling, dead code, clones |
| **Complexity metrics** | Cyclomatic + cognitive complexity per function |
| **Dependency scanning** | 7 ecosystems: PyPI, npm, Maven, Crates.io, Go, NuGet, CMake |
| **Git blame / churn** | Hotspot detection, bus factor, stale code, author analytics |
| **Dead code detection** | BFS from entry points to find unreachable symbols and modules |
| **Clone detection** | AST structural fingerprinting for exact and near-clone detection |
| **Module coupling** | Martin's package metrics: Ca, Ce, instability, abstractness, cohesion |
| **PR review** | Diff parsing, heuristic risk detection, blast radius analysis |
| **Auto documentation** | Generate module, flow, and API docs from code graph |
| **Q&A engine** | Ask natural language questions about the codebase |
| **Export** | JSON, .eidos, CSV/ZIP, SARIF (GitHub Code Scanning), Markdown report |

## API Endpoints (72)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| GET | `/health/ready` | Readiness check (DB) |
| GET | `/repos` | List all repos |
| POST | `/repos` | Register a repo |
| PATCH | `/repos/{id}` | Update repo settings |
| DELETE | `/repos/{id}` | Delete repo + all data |
| POST | `/repos/{id}/ingest` | Trigger clone + analysis |
| GET | `/repos/{id}/status` | Snapshots with status |
| GET | `/repos/{id}/snapshots` | List snapshots (paginated) |
| GET | `/repos/{id}/snapshots/{sid}` | Snapshot detail with files |
| DELETE | `/repos/{id}/snapshots/{sid}` | Delete a snapshot |
| GET | `/repos/{id}/snapshots/{sid}/symbols` | List symbols (filter by kind, file) |
| GET | `/repos/{id}/snapshots/{sid}/symbols/{fq}` | Symbol detail |
| GET | `/repos/{id}/snapshots/{sid}/symbols/{fq}/callers` | Who calls this function |
| PATCH | `/repos/{id}/snapshots/{sid}/symbols/{fq}/notes` | Add/update symbol annotation |
| GET | `/repos/{id}/snapshots/{sid}/symbols/{fq}/notes` | Get symbol annotations |
| GET | `/repos/{id}/snapshots/{sid}/edges` | List edges (filter by type) |
| GET | `/repos/{id}/snapshots/{sid}/graph/{fq}` | Call graph neighborhood |
| GET | `/repos/{id}/snapshots/{sid}/files` | List files (filter by language) |
| GET | `/repos/{id}/snapshots/{sid}/overview` | Analysis summary |
| GET | `/repos/{id}/snapshots/{sid}/health` | Run 66 health rules |
| POST | `/repos/{id}/snapshots/{sid}/health/llm` | LLM-enhanced health analysis |
| GET | `/repos/{id}/snapshots/{sid}/diagrams/class` | Mermaid class diagram |
| GET | `/repos/{id}/snapshots/{sid}/diagrams/module` | Mermaid module diagram |
| GET | `/repos/{id}/snapshots/{sid}/dependencies` | Dependency list |
| GET | `/repos/{id}/snapshots/{sid}/dead-code` | Dead code detection (BFS) |
| GET | `/repos/{id}/snapshots/{sid}/clones` | Clone detection (AST fingerprint) |
| GET | `/repos/{id}/snapshots/{sid}/coupling` | Module coupling & cohesion metrics |
| GET | `/repos/{id}/snapshots/{sid}/contributors` | Git blame contributors |
| GET | `/repos/{id}/snapshots/{sid}/hotspots` | Churn × complexity hotspots |
| GET | `/repos/{id}/snapshots/{sid}/summaries` | List summaries |
| GET | `/repos/{id}/snapshots/{sid}/summaries/{type}/{id}` | Get specific summary |
| POST | `/repos/{id}/snapshots/{sid}/ask` | Ask a question (Q&A engine) |
| POST | `/repos/{id}/snapshots/{sid}/classify` | Classify a question |
| POST | `/repos/{id}/snapshots/{sid}/review` | Review a PR diff |
| GET | `/repos/{id}/snapshots/{sid}/reviews` | List past reviews |
| POST | `/repos/{id}/snapshots/{sid}/docs` | Generate documentation |
| GET | `/repos/{id}/snapshots/{sid}/docs` | List generated docs |
| GET | `/repos/{id}/snapshots/{sid}/docs/{doc_id}` | Get a specific doc |
| POST | `/repos/{id}/snapshots/{sid}/evaluate` | Run evaluation & guardrails |
| GET | `/repos/{id}/snapshots/{sid}/evaluations` | List past evaluations |
| GET | `/repos/{id}/snapshots/{sid}/search` | Full-text search |
| GET | `/repos/{id}/snapshots/{sid}/fulltext` | PostgreSQL full-text search |
| GET | `/repos/{id}/snapshots/{sid}/diff/{other}` | Compare two snapshots |
| GET | `/repos/{id}/snapshots/{sid}/export` | Export as JSON |
| GET | `/repos/{id}/snapshots/{sid}/export/csv` | Export as CSV (ZIP) |
| GET | `/repos/{id}/snapshots/{sid}/export/sarif` | Export as SARIF 2.1.0 |
| GET | `/repos/{id}/snapshots/{sid}/export/markdown` | Export as Markdown report |
| GET | `/repos/{id}/snapshots/{sid}/portable` | Export as .eidos (gzip) |
| POST | `/repos/{id}/import` | Import a .eidos file |
| GET | `/repos/{id}/health/trend` | Health score trend |
| GET | `/auth/login` | GitHub OAuth flow |
| GET | `/auth/callback` | GitHub OAuth callback |
| GET | `/auth/google/login` | Google OAuth flow |
| GET | `/auth/google/callback` | Google OAuth callback |
| GET | `/auth/me` | Current user info |
| POST | `/auth/logout` | Logout |
| POST | `/auth/api-keys` | Create API key |
| GET | `/auth/api-keys` | List API keys |
| DELETE | `/auth/api-keys/{id}` | Revoke API key |
| POST | `/webhooks/github` | GitHub push webhook |
| POST | `/webhooks/gitlab` | GitLab push webhook |
| POST | `/webhooks/push` | Generic push webhook |
| GET | `/metrics` | Prometheus metrics |
| GET | `/admin/users` | List users (admin) |
| GET | `/admin/users/{id}` | User detail (admin) |
| PUT | `/admin/users/{id}/role` | Change user role |
| GET | `/admin/plans` | List plans |
| POST | `/admin/plans` | Create plan |
| PUT | `/admin/plans/{id}` | Update plan |
| GET | `/admin/stats` | Platform statistics |

## Project Structure

```
backend/
  app/
    api/
      repos.py           # Repo CRUD + snapshot endpoints + file list + callers + notes
      analysis.py         # Symbols, edges, graph, overview, health, diagrams
      search.py           # Full-text search, snapshot diff, JSON export
      indexing.py          # Summary listing + retrieval
      reasoning.py         # Q&A ask + classify
      reviews.py          # PR review + list
      docgen.py           # Doc generation + list + get
      blame.py            # Git contributors + hotspots
      dead_code.py        # Dead code detection endpoint
      clones.py           # Clone detection endpoint
      coupling.py         # Module coupling metrics endpoint
      deps.py             # Dependency list endpoint
      exports.py          # CSV/ZIP, SARIF, Markdown export
      diagrams.py         # Mermaid class and module diagrams
      trends.py           # Health score trend tracking
      portable.py         # Portable .eidos export/import
      webhooks.py         # GitHub/GitLab/generic push webhooks
      auth.py             # OAuth (GitHub, Google), API keys, JWT
      admin.py            # User/plan management, platform stats
      metrics.py          # Prometheus /metrics endpoint
      evaluations.py      # Guardrails evaluation
      dependencies.py     # Shared FastAPI dependencies
    core/
      config.py           # Settings via pydantic-settings
      ingestion.py        # Git clone, file scanning, hashing
      tasks.py            # Background ingestion orchestrator
      middleware.py       # CORS, request ID, logging, rate limiting
      incremental.py      # Incremental analysis (only changed files)
      retry.py            # Retry with exponential backoff
      retention.py        # Clone cleanup after ingestion
    analysis/
      models.py           # Data classes (SymbolInfo, EdgeInfo, etc.)
      pipeline.py         # Analysis orchestrator + DB persistence
      graph_builder.py    # Call graph + module graph construction
      entry_points.py     # Controller, Main, Startup detection
      code_health.py      # Health check orchestrator (66 rules)
      complexity.py       # Cyclomatic + cognitive complexity (tree-sitter)
      dead_code.py        # BFS reachability dead code detection
      clone_detection.py  # AST structural fingerprinting
      coupling.py         # Module coupling & cohesion (Martin metrics)
      blame.py            # Git blame extraction
      dependency_parser.py # 7-ecosystem dependency scanner
      csharp_parser.py    # C# parser
      java_parser.py      # Java parser
      python_parser.py    # Python parser
      typescript_parser.py # TypeScript parser
      go_parser.py        # Go parser
      rust_parser.py      # Rust parser
      c_parser.py         # C parser
      cpp_parser.py       # C++ parser
      kotlin_parser.py    # Kotlin parser
      parser_registry.py  # Language -> parser registry
      health_rules/       # 66 rules across 13 category modules
        clean_code.py     # 8 rules (long method, empty method, etc.)
        solid.py          # 5 rules (god class, DIP, ISP, etc.)
        complexity.py     # 6 rules (fan-in/out, CBO, LCOM)
        design.py         # 10 rules (circular deps, dead code, etc.)
        naming.py         # 4 rules (short names, boolean names, etc.)
        security.py       # 3 rules (hardcoded secrets, SQL injection)
        best_practices.py # 3 rules (large files, deep nesting)
        documentation.py  # 1 rule (missing docs)
        blame.py          # 4 rules (hotspot, stale, bus factor, churn)
        dead_code.py      # 4 rules (unreachable func/class/module/import)
        clones.py         # 3 rules (exact clone, near clone, cluster)
        coupling.py       # 5 rules (instability, cohesion, zones, cycles)
        dependencies.py   # 10 rules (outdated, missing lock, CVE, etc.)
    exports/
      generators.py       # CSV/ZIP, SARIF 2.1.0, Markdown report generators
    indexing/
      summary_schema.py   # Summary data classes
      facts_extractor.py  # Deterministic facts from code graph
      summarizer.py       # LLM interface + stub
      embedder.py         # Embedding generation
      vector_store.py     # Vector DB abstraction
      indexer.py          # Indexing pipeline orchestrator
    reasoning/
      models.py           # Question, Answer, Evidence
      llm_client.py       # Universal LLM client
      question_router.py  # Question classification
      retriever.py        # Hybrid retrieval (vector + graph)
      answer_builder.py   # Answer generation
    reviews/
      models.py           # DiffHunk, ChangedSymbol, ReviewFinding
      diff_parser.py      # Unified diff parser
      heuristics.py       # 8 behavioural risk detectors
      impact_analyzer.py  # Call-graph blast radius
      reviewer.py         # Review pipeline orchestrator
    docgen/
      models.py           # DocSection, Citation, GeneratedDocument
      templates.py        # Section templates per document type
      generator.py        # Doc generation from graph + summaries
      renderer.py         # Markdown rendering with citations
      orchestrator.py     # Doc generation pipeline
    guardrails/
      runner.py           # Evaluation framework
    auth/
      crypto.py           # Encryption, API key hashing
      dependencies.py     # JWT + API key authentication
    storage/
      database.py         # SQLAlchemy async engine + session
      models.py           # DB models (Repo, Snapshot, File, Symbol, Edge, etc.)
      schemas.py          # Pydantic response schemas
  tests/                  # 2,119 tests (see docs/TESTING.md)
  alembic/                # Database migrations
  Dockerfile              # Production container image
infra/
  docker-compose.yml      # Postgres + Redis + Qdrant
k8s/
  namespace.yaml          # Kubernetes namespace
  configmap.yaml          # Non-secret config
  secrets.yaml            # API keys, passwords
  infrastructure.yaml     # Postgres, Redis, Qdrant deployments
  api.yaml                # Eidos API deployment
  deploy-local.sh         # One-command deployment
docs/                     # 29 documentation files
frontend/                 # Next.js frontend (in development)
```

## Stats

| Metric | Value |
|--------|-------|
| Total lines of code | 49,640 |
| Application code | 119 files / 23,967 lines |
| Test code | 87 files / 25,673 lines |
| Tests (CI-verified) | 2,119 |
| API endpoints | 72 |
| Language parsers | 9 |
| Code health rules | 66 |
| Export formats | 5 |
| Test-to-code ratio | 1.07:1 |

## Documentation

See [`docs/`](docs/) for full documentation including architecture, API reference, deployment guides, and developer guides.
