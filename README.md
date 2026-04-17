# Eidos — Legacy Code Intelligence Tool

Explains legacy C# codebases, auto-generates documentation with citations, and reviews PRs for logic/behavior risks.

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

## API Endpoints

| Method | Path                                          | Description                     |
|--------|-----------------------------------------------|---------------------------------|
| GET    | `/health`                                     | Health check                    |
| POST   | `/repos`                                      | Register a repo                 |
| POST   | `/repos/{id}/ingest`                          | Trigger clone + analysis        |
| GET    | `/repos/{id}/status`                          | Snapshots with status           |
| GET    | `/repos/{id}/snapshots/{sid}`                 | Snapshot detail with files      |
| GET    | `/repos/{id}/snapshots/{sid}/symbols`         | List symbols (filter by kind, file) |
| GET    | `/repos/{id}/snapshots/{sid}/symbols/{fq}`    | Get symbol by fully-qualified name |
| GET    | `/repos/{id}/snapshots/{sid}/edges`           | List edges (filter by type, source, target) |
| GET    | `/repos/{id}/snapshots/{sid}/graph/{fq}`      | Call graph neighborhood         |
| GET    | `/repos/{id}/snapshots/{sid}/overview`        | Analysis summary                |
| GET    | `/repos/{id}/snapshots/{sid}/summaries`       | List summaries (filter by scope) |
| GET    | `/repos/{id}/snapshots/{sid}/summaries/{type}/{id}` | Get specific summary      |
| POST   | `/repos/{id}/snapshots/{sid}/ask`             | Ask a question (Q&A engine)     |
| POST   | `/repos/{id}/snapshots/{sid}/classify`        | Classify a question (debug)     |
| POST   | `/repos/{id}/snapshots/{sid}/review`          | Review a PR diff                |
| GET    | `/repos/{id}/snapshots/{sid}/reviews`         | List past reviews               |
| POST   | `/repos/{id}/snapshots/{sid}/docs`            | Generate documentation          |
| GET    | `/repos/{id}/snapshots/{sid}/docs`            | List generated docs             |
| GET    | `/repos/{id}/snapshots/{sid}/docs/{doc_id}`   | Get a specific generated doc    |

## Project Structure

```
backend/
  app/
    api/
      repos.py          # Repo + snapshot endpoints
      analysis.py       # Symbol, edge, graph, overview endpoints
      indexing.py        # Summary listing + retrieval endpoints
      reasoning.py       # Q&A ask + classify endpoints
      reviews.py        # PR review + list endpoints
      docgen.py         # Doc generation + list + get endpoints
    core/
      config.py         # Settings via pydantic-settings
      ingestion.py      # Git clone, file scanning, hashing
      tasks.py          # Background ingestion + analysis + indexing
    analysis/
      models.py         # Data classes (SymbolInfo, EdgeInfo, etc.)
      csharp_parser.py  # Tree-sitter C# parser
      graph_builder.py  # Call graph + module graph construction
      entry_points.py   # Controller, Main, Startup detection
      metrics.py        # LOC, fan-in/out, hotspot detection
      pipeline.py       # Analysis orchestrator + DB persistence
    indexing/
      summary_schema.py # Summary data classes
      facts_extractor.py # Deterministic facts from code graph
      summarizer.py     # LLM interface + stub (no AI required)
      embedder.py       # Embedding generation (hash + OpenAI stub)
      vector_store.py   # Vector DB abstraction (in-memory + Qdrant)
      indexer.py        # Pipeline orchestrator
    reasoning/
      models.py         # Question, Answer, Evidence, RetrievalContext
      llm_client.py     # Universal LLM client (OpenAI/Ollama/vLLM/stub)
      question_router.py # Question classification + symbol extraction
      retriever.py      # Hybrid retrieval (vector + graph)
      answer_builder.py  # Context assembly + answer generation
    reviews/
      models.py         # DiffHunk, ChangedSymbol, ReviewFinding, ReviewReport
      diff_parser.py    # Unified diff parser + line-to-symbol mapping
      heuristics.py     # 8 behavioural risk detectors
      impact_analyzer.py # Call-graph blast radius analysis
      reviewer.py       # Pipeline orchestrator
    docgen/
      models.py         # DocSection, Citation, GeneratedDocument
      templates.py      # Section templates per document type
      generator.py      # Deterministic doc generation from graph + summaries
      renderer.py       # Markdown rendering with citation appendix
      orchestrator.py   # Pipeline: fetch -> generate -> persist
    storage/
      database.py       # SQLAlchemy async engine + session
      models.py         # DB models (Repo, Snapshot, File, Symbol, Edge, Summary, Review, GeneratedDoc)
      schemas.py        # Pydantic response schemas
  tests/                # 423 tests (see docs/TESTING.md)
  Dockerfile            # Production container image
infra/
  docker-compose.yml    # Postgres + Redis + Qdrant (local dev)
k8s/
  namespace.yaml        # Kubernetes namespace
  configmap.yaml        # Non-secret config
  secrets.yaml          # API keys, passwords
  infrastructure.yaml   # Postgres, Redis, Qdrant deployments
  api.yaml              # Eidos API deployment + NodePort
  deploy-local.sh       # One-command deployment (kind/minikube)
docs/
  ARCHITECTURE.md       # Full technical documentation
  PHASE3_INDEXING.md    # Summarisation & indexing details
  KUBERNETES.md         # K8s deployment guide
  TESTING.md            # Test strategy & inventory
```
