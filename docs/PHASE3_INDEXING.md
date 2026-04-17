# Phase 3 - Summarisation & Indexing

## Overview

Phase 3 builds the **knowledge layer** on top of the code graph from Phase 2.
It extracts structured facts from every symbol, module, and file, optionally
enriches them with an LLM, generates embeddings, and stores everything for
fast retrieval.

**Key constraint:** LLM integration is currently **disabled** due to company
policy.  The system is designed with a clean abstraction layer so that LLM
access can be enabled by simply providing an API key -- no code changes
required.

## Pipeline Flow

```
CodeGraph (Phase 2)
       |
       v
  Facts Extractor           (deterministic, no AI)
       |
       v
  Summariser                (StubSummariser or LLMSummariser)
       |
       v
  +---------+-----------+
  |                     |
  v                     v
PostgreSQL          Vector Store
(summaries table)   (embeddings)
```

## Components

### 1. Summary Schema (`indexing/summary_schema.py`)

Defines the shape of all summaries as Python dataclasses.

**SymbolSummary fields:**
- `fq_name` -- fully qualified symbol name
- `kind` -- class, method, interface, etc.
- `purpose` -- one-sentence description
- `inputs` -- method parameters
- `outputs` -- return types
- `side_effects` -- inferred writes, logging, network calls
- `assumptions` -- implicit preconditions
- `risks` -- high fan-in, large methods, complex orchestration
- `citations` -- file path + line ranges (always present)
- `confidence` -- HIGH / MEDIUM / LOW

**ModuleSummary fields:**
- `name`, `purpose`, `responsibilities`, `key_classes`, `dependencies`, `entry_points`, `citations`, `confidence`

**FileSummary fields:**
- `path`, `purpose`, `symbols`, `namespace`, `imports`, `citations`, `confidence`

### 2. Facts Extractor (`indexing/facts_extractor.py`)

Builds summaries from the CodeGraph **without any AI**.  Pure deterministic
logic that synthesises human-readable text from structural information.

**What it infers:**

| Inference | How |
|-----------|-----|
| Purpose | Constructed from kind, name, member count, base types, return type |
| Side effects | Scans callee names for keywords: write, save, delete, send, log |
| Assumptions | Checks parameter count, static vs instance |
| Risks | Fan-in >= 5, fan-out >= 5, LOC >= 50 |
| Confidence | Scored from signature, params, return type, doc comments, graph edges |

### 3. Summariser (`indexing/summarizer.py`)

Strategy pattern with two implementations:

| Implementation | When Used | Behaviour |
|----------------|-----------|-----------|
| `StubSummariser` | No API key (default) | Pass-through; returns facts unchanged |
| `LLMSummariser` | API key provided | Placeholder; falls back to stub |

The factory `create_summariser(api_key)` returns the appropriate one.

**When LLM access is approved**, implement the three methods in
`LLMSummariser`:
1. Serialise facts + code snippet into a structured prompt
2. Call the LLM API with JSON schema enforcement
3. Parse response, preserve citations, adjust confidence

### 4. Embedder (`indexing/embedder.py`)

| Implementation | When Used | Vector Size | Deterministic |
|----------------|-----------|-------------|---------------|
| `HashEmbedder` | No API key (default) | 256 (configurable) | Yes |
| `OpenAIEmbedder` | API key provided | 1536 | No |

`HashEmbedder` uses SHA-256 to produce consistent vectors from text.
Not semantically meaningful but preserves the full pipeline contract,
enabling end-to-end testing without external dependencies.

### 5. Vector Store (`indexing/vector_store.py`)

| Implementation | When Used | Backend |
|----------------|-----------|---------|
| `InMemoryVectorStore` | Testing / default | Python dict + brute-force cosine |
| `QdrantVectorStore` | Production | Qdrant REST API |

Both implement the same `VectorStore` abstract class:
- `ensure_collection(name, vector_size)`
- `upsert(collection, records, vectors)`
- `search(collection, query_vector, limit, filters)`
- `delete_by_snapshot(collection, snapshot_id)`

**VectorRecord payload:**
- `snapshot_id` -- ties to a specific analysis snapshot
- `scope_type` -- symbol_summary, module_summary, file_summary
- `text` -- the embedded text
- `refs` -- citations back to source code
- `metadata` -- extra fields (fq_name, kind, etc.)

### 6. Indexer Orchestrator (`indexing/indexer.py`)

Coordinates the full pipeline:

1. Extract facts (symbols + modules + files)
2. Enrich with summariser
3. Persist summaries to `summaries` PostgreSQL table
4. Generate embeddings in batches (max 64 per call)
5. Upsert vectors to vector store
6. Return stats dict

## Database Model

```sql
CREATE TABLE summaries (
    id          SERIAL PRIMARY KEY,
    snapshot_id VARCHAR(24) REFERENCES repo_snapshots(id) ON DELETE CASCADE,
    scope_type  VARCHAR(32) NOT NULL,  -- symbol | module | file
    scope_id    TEXT NOT NULL,          -- fq_name, module name, or path
    summary_json TEXT NOT NULL,         -- full JSON payload
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_summaries_snapshot_scope ON summaries(snapshot_id, scope_type);
CREATE INDEX ix_summaries_snapshot_id_scope_id ON summaries(snapshot_id, scope_id);
```

## API Endpoints

### `GET /repos/{id}/snapshots/{sid}/summaries`

List summaries with optional filters.

| Param | Type | Description |
|-------|------|-------------|
| `scope_type` | string | Filter: symbol, module, file |
| `scope_id` | string | Filter by fq_name / module / path |
| `limit` | int | 1-1000, default 100 |
| `offset` | int | Pagination |

### `GET /repos/{id}/snapshots/{sid}/summaries/{scope_type}/{scope_id}`

Get a specific summary by type and ID.

**Response example:**
```json
{
  "id": 42,
  "snapshot_id": "abc123",
  "scope_type": "symbol",
  "scope_id": "MyApp.Services.UserService.GetById",
  "summary": {
    "fq_name": "MyApp.Services.UserService.GetById",
    "kind": "method",
    "purpose": "Method 'GetById', returns User, takes 1 parameter(s), calls 2 other symbol(s).",
    "inputs": ["int id"],
    "outputs": ["User"],
    "side_effects": ["Calls 'LogInfo' (logging/output)."],
    "assumptions": [],
    "risks": [],
    "citations": [{"file_path": "Services/UserService.cs", "symbol_fq_name": "MyApp.Services.UserService.GetById", "start_line": 15, "end_line": 22}],
    "confidence": "high"
  },
  "created_at": "2025-01-15T10:35:00+00:00"
}
```

## Enabling LLM (Future)

1. Set `EIDOS_OPENAI_API_KEY` in environment / secrets
2. The factory functions automatically switch to LLM-powered implementations
3. No code changes required
4. Summaries gain richer natural-language descriptions while keeping citations
