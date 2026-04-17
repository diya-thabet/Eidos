# Testing Strategy & Guide

## Overview

Eidos uses a layered testing strategy:

1. **Unit tests** -- individual functions and classes in isolation
2. **Integration tests** -- components wired together (DB, pipeline)
3. **API tests** -- full HTTP request/response cycle via FastAPI TestClient

All tests run without external services (no Docker, no network, no LLM).

## Running Tests

```bash
cd backend

# Run all tests
pytest -v

# Run a specific test file
pytest tests/test_csharp_parser.py -v

# Run a specific test class
pytest tests/test_csharp_parser.py::TestBasicParsing -v

# Run with coverage (install pytest-cov first)
pytest --cov=app --cov-report=term-missing

# Run only fast tests (skip DB tests)
pytest tests/test_csharp_parser.py tests/test_graph_builder.py tests/test_entry_points.py tests/test_metrics.py tests/test_ingestion.py -v
```

## Test Infrastructure

### Database
- **Engine:** SQLite via `aiosqlite` (in-memory, no files)
- **Setup:** `conftest.py` provides shared engine, session factory, and fixtures
- **Isolation:** Tables created before each test, dropped after
- **Why not Postgres?** Tests must run in CI without Docker

### LLM / External APIs
- All LLM components use the **Strategy pattern**
- Tests use `StubSummariser` (pass-through) and `HashEmbedder` (deterministic)
- Background tasks (git clone) are **mocked** in API tests
- No network calls in any test

### Vector Store
- Tests use `InMemoryVectorStore` (brute-force cosine similarity)
- Same interface as `QdrantVectorStore` -- tests validate the contract

## Test Inventory

### Phase 1 -- Repo Ingestion

| File | Tests | Scope |
|------|-------|-------|
| `test_api.py` | 11 | Repo CRUD, ingestion trigger, validation, 404s |
| `test_ingestion.py` | 3 | Language detection, file hashing, directory scanning |

### Phase 2 -- Static Analysis

| File | Tests | Scope |
|------|-------|-------|
| `test_csharp_parser.py` | 35 | All C# symbol types, edges, modifiers, parameters, nested types, edge cases |
| `test_graph_builder.py` | 17 | Graph construction, callers/callees, BFS neighborhood, modules |
| `test_entry_points.py` | 13 | Controllers, Main, Startup, workers, combined detection |
| `test_metrics.py` | 9 | LOC, fan-in/out, hotspots |
| `test_pipeline.py` | 9 | End-to-end: files on disk -> graph -> DB persistence |
| `test_analysis_api.py` | 21 | Symbol/edge/graph API endpoints with filtering and pagination |

### Phase 3 -- Summarisation & Indexing

| File | Tests | Scope |
|------|-------|-------|
| `test_facts_extractor.py` | 23 | Symbol/module/file fact generation, side effects, risks, confidence |
| `test_summarizer.py` | 10 | Stub pass-through, LLM fallback, factory function |
| `test_embedder.py` | 11 | Hash determinism, vector size, normalisation, batch, factory |
| `test_vector_store.py` | 16 | Upsert, search, filtering, deletion, cosine similarity |
| `test_indexer.py` | 8 | Full pipeline: graph -> DB summaries -> vector store |
| `test_indexing_api.py` | 11 | Summary listing, filtering, retrieval, error handling |

### Phase 4 -- Explain / Q&A

| File | Tests | Scope |
|------|-------|-------|
| `test_question_router.py` | 22 | All question types, symbol extraction, question building |
| `test_llm_client.py` | 15 | Stub client, OpenAI-compatible (mocked), factory, JSON parsing |
| `test_answer_builder.py` | 15 | Deterministic answers, LLM (mocked), confidence, verification |
| `test_retriever.py` | 8 | Symbol lookup, call edges, module summaries, vector search |
| `test_reasoning_api.py` | 14 | Ask + classify endpoints, response structure, error handling |

### Phase 5 -- PR Review

| File | Tests | Scope |
|------|-------|-------|
| `test_diff_parser.py` | 17 | Diff parsing, new/deleted/renamed files, hunks, symbol mapping |
| `test_heuristics.py` | 25 | All 8 heuristic detectors, combined findings, edge cases |
| `test_impact_analyzer.py` | 12 | BFS traversal, distance tracking, risk scoring |
| `test_reviewer.py` | 12 | End-to-end pipeline, LLM mock, graceful failures, multi-file |
| `test_reviews_api.py` | 12 | Review + list endpoints, persistence, response structure |

### Phase 6 -- Auto Documentation

| File | Tests | Scope |
|------|-------|-------|
| `test_templates.py` | 9 | All doc types have templates, section keys valid |
| `test_generator.py` | 28 | README/architecture/module/flow/runbook generation, citations, empty data |
| `test_renderer.py` | 14 | Markdown rendering, sections, citations appendix, dedup, symbol links |
| `test_orchestrator.py` | 14 | Full pipeline with DB, persistence, LLM mock, empty snapshot |
| `test_docgen_api.py` | 15 | Generate/list/get endpoints, filtering, error handling, persistence |

### Total: 423 tests

### Phase 7 -- Evaluation & Guardrails

| File | Tests | Scope |
|------|-------|-------|
| `test_guardrails_models.py` | 5 | EvalReport scoring, severity computation |
| `test_hallucination_detector.py` | 14 | Symbol/relationship verification, partial match |
| `test_answer_evaluator.py` | 13 | Citation coverage, grounding, completeness |
| `test_doc_evaluator.py` | 13 | Completeness, accuracy, staleness, coverage |
| `test_review_evaluator.py` | 12 | Precision, severity distribution, coverage |
| `test_sanitizer.py` | 16 | Injection detection, PII redaction, I/O sanitization |
| `test_eval_runner.py` | 10 | Full pipeline, persistence, empty snapshot, answer eval |
| `test_eval_api.py` | 8 | Endpoints, response structure, error handling |

### Total: 525 tests

### Phase 8 -- Security & Multi-tenant

| File | Tests | Scope |
|------|-------|-------|
| `test_crypto.py` | 6 | Encrypt/decrypt round-trip, invalid data |
| `test_token_service.py` | 10 | JWT create/decode, expiry, tampering |
| `test_github_oauth.py` | 5 | Authorize URL, code exchange, user fetch |
| `test_google_oauth.py` | 7 | Google OAuth authorize, exchange, fetch |
| `test_auth_api.py` | 9 | GitHub login, callback, me, logout |
| `test_google_auth_api.py` | 7 | Google login, callback, user create/update |
| `test_auth_dependencies.py` | 7 | Anonymous mode, JWT validation, isolation |
| `test_retention.py` | 5 | Clone cleanup, disabled mode |
| `test_security_scenarios.py` | 7 | Cross-user isolation, ownership, anonymous |

### Cross-module & Scenario Tests

| File | Tests | Scope |
|------|-------|-------|
| `test_integration_e2e.py` | 36 | Full pipeline: symbols, edges, overview, docs, eval, lifecycle |
| `test_cross_module.py` | 37 | Analysis?indexing, embedder+vector store, guardrails, diff, router |
| `test_edge_cases.py` | 37 | Empty snapshots, invalid inputs, graph edges, sanitizer, data integrity |
| `test_schemas_comprehensive.py` | 39 | All Pydantic schemas, DB models, OAuth dataclasses |

### Total: 727 tests

## Test Design Principles

1. **No external dependencies** -- every test runs offline
2. **Deterministic** -- same input always produces same output
3. **Fast** -- full suite completes in ~30 seconds
4. **Isolated** -- tests don't share state; DB reset between tests
5. **Mirrors source** -- `test_X.py` tests `X.py`
6. **Readable** -- test classes group by feature, names describe intent
7. **C# fixtures as byte literals** -- no fixture files needed

## Adding New Tests

1. Create `tests/test_<module>.py`
2. Import from `tests.conftest` if you need DB fixtures
3. Use `@pytest.mark.asyncio` for async tests
4. Mock external calls (LLM, git, network) -- never call real services
5. Run `pytest tests/test_<module>.py -v` to verify
