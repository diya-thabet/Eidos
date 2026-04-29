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

### Multi-Language Parsers

| File | Tests | Scope |
|------|-------|-------|
| `test_java_parser.py` | 79 | Java packages, imports, classes, interfaces, enums, generics, Javadoc, nested, calls, registry, pipeline |
| `test_python_parser.py` | 66 | Python imports, classes, functions, methods, decorators, async, docstrings, nested, calls, registry, pipeline |
| `test_typescript_parser.py` | 83 | TypeScript/TSX imports, classes, interfaces, enums, methods, constructors, fields, generics, TSDoc, calls, new expressions, abstract, pipeline |

### System Hardening

| File | Tests | Scope |
|------|-------|-------|
| `test_hardening.py` | 82 | Input validation (RepoCreate), path traversal, sanitizer PII/injection, parser enhancements, cross-language pipeline, token injection, registry robustness, language detection, crypto, JWT |
| `test_go_parser.py` | 58 | Go packages, imports, structs, interfaces, functions, methods, receivers, fields, calls, doc comments, type aliases, registry, pipeline |
| `test_rust_parser.py` | 63 | Rust use declarations, structs, traits, enums, impl blocks, trait impl, constructors, fields, calls, doc comments, modules, type aliases, registry, pipeline |
| `test_c_parser.py` | 42 | C includes, structs, enums, functions, typedefs, fields, calls, doc comments, static functions, registry, pipeline |
| `test_cpp_parser.py` | 45 | C++ includes, namespaces, classes, structs, enums, inheritance, constructors, destructors, methods, fields, free functions, new expressions, scoped calls, registry, pipeline |
| `test_rbac_metering.py` | 39 | RBAC roles, role hierarchy, metering engine (time/token/scan/combo/unlimited), plan limits JSONB, usage recording, edition config, dependencies |
| `test_code_health.py` | 95 | All 40 rules (clean code, SOLID, complexity, coupling/cohesion, naming, code smells, architecture, security, best practices), config, scoring, category filtering, rule disabling, report format, edge cases |

### Total: 1379 tests

### Production Hardening (Phase 10)

| File | Tests | Scope |
|------|-------|-------|
| `test_middleware_and_infra.py` | 36 | Request ID middleware, CORS, global exception handler, rate limiting, deep healthcheck, pagination envelope, token bucket unit tests, PaginatedResponse schema |
| `test_search_and_compare.py` | 35 | Full-text search (symbols, summaries, docs), snapshot diff (added/removed/modified), export API, search scoring |
| `test_webhooks.py` | 18 | GitHub/GitLab/generic webhook receivers, HMAC signature verification, branch matching, snapshot creation |
| `test_repo_crud.py` | 12 | DELETE /repos/{id} (cascade, idempotent), PATCH /repos/{id} (partial update, whitespace, not found) |
| `test_diagrams_and_trends.py` | 23 | Mermaid class/module diagrams, health score trends (improving/degrading/stable/insufficient) |
| `test_portable.py` | 25 | Portable .eidos export (gzip, compact keys, headers), import (restore, validation), round-trip (symbols/edges/summaries/docs preserved) |
| `test_progress.py` | 7 | Ingestion progress fields in status/detail responses, default values, all snapshot states |
| `test_api_keys.py` | 13 | API key create (format, hash, prefix), list (metadata only, no raw key), revoke, auth with X-API-Key header |
| `test_logging.py` | 3 | JSON formatter in client mode, text in internal mode, field verification |
| `test_parallel_parsing.py` | 15 | Sequential/parallel parsing, single-file isolation, mixed languages, empty list, worker count |
| `test_prometheus.py` | 12 | /metrics endpoint, Prometheus text format, request counters, duration metrics, path normalization, ingestion counter |
| `test_retry.py` | 11 | Exponential backoff: success, retry-then-succeed, exhaustion, delay timing, non-retryable exceptions, max delay cap, kwargs |
| `test_incremental.py` | 9 | First snapshot full parse, unchanged files excluded, changed/new file detection, copy symbols from unchanged files |
| `test_fulltext_search.py` | 10 | /fulltext endpoint, ILIKE fallback, PostgreSQL detection, partial match, result structure, limit, 404 |

| `test_real_repo_e2e.py` | 33 | Full E2E against real Java GitHub repo (Neon-Defenders): clone, parse, symbols, edges, health, search, docs, review, diagrams, export/import, API keys, metrics |
| `test_multilang_e2e.py` | 144 | Full E2E against 8 real GitHub repos (Python/markupsafe, C#/GuardClauses, TS/p-map, TSX/zustand, Go/go-patterns, Rust/thiserror, C/sds, C++/spdlog): clone, parse, API, search, health, export, portable round-trip |
| `test_deep_languages.py` | 38 | Deep per-language validation against 9 challenging repos (click, GuardClauses, java-design-patterns, ky, cmdk, bubbletea, http, cJSON, fmt): full graph analysis, inheritance chains, call graphs, API pipeline |

| `test_deep_languages.py` | 38 | Deep validation: 9 challenging repos (click, GuardClauses, java-design-patterns, ky, cmdk, bubbletea, http, cJSON, fmt) |
| `test_complexity.py` | 57 | Cyclomatic & cognitive complexity: calculator unit tests (9 langs), pipeline integration, 5 health rules, API endpoint, edge cases |
| `test_dependency_parser.py` | 61 | Dependency parsing: 11 manifest parsers (7 ecosystems), pipeline integration, 5 health rules, API endpoint, edge cases |
| `test_blame.py` | 31 | Git blame/churn: blame extraction on real git repos, blame_for_range, 4 health rules (hotspot/stale/bus-factor/churn), 2 API endpoints |

### Updated Total: ~1,967 tests (1,961 passed + 6 skipped)

## Test Design Principles

1. **No external dependencies** -- every test runs offline
2. **Deterministic** -- same input always produces same output
3. **Fast** -- full suite completes in ~30 seconds
4. **Isolated** -- tests don't share state; DB reset between tests
5. **Mirrors source** -- `test_X.py` tests `X.py`
6. **Readable** -- test classes group by feature, names describe intent
7. **Source fixtures as byte literals** -- no fixture files needed for C#, Java, Python, TypeScript parsing

## Adding New Tests

1. Create `tests/test_<module>.py`
2. Import from `tests.conftest` if you need DB fixtures
3. Use `@pytest.mark.asyncio` for async tests
4. Mock external calls (LLM, git, network) -- never call real services
5. Run `pytest tests/test_<module>.py -v` to verify
