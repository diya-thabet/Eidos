# Phase 4 -- Explain / Q&A Engine

## Overview

Phase 4 adds a natural-language question-answering engine that lets
developers ask questions about their legacy codebase and receive
structured answers with evidence, confidence ratings, and verification
checklists.

**Works with or without an LLM.** Without an LLM, answers are built
entirely from deterministic code graph analysis. With an LLM (any
OpenAI-compatible provider), answers gain richer natural-language prose.

## Architecture

```
User Question
      |
      v
Question Router         (classify type, extract target symbol)
      |
      v
Hybrid Retriever        (vector search + graph BFS expansion)
      |
      v
Answer Builder          (assemble context + LLM or deterministic)
      |
      v
Structured Answer       (evidence + confidence + verification)
```

## Components

### 1. LLM Client (`reasoning/llm_client.py`)

Universal client supporting **any OpenAI-compatible API**:

| Provider | base_url | api_key | model |
|----------|----------|---------|-------|
| OpenAI | `https://api.openai.com/v1` | `sk-...` | `gpt-4o-mini` |
| Azure OpenAI | `https://{name}.openai.azure.com/v1` | `...` | deployment name |
| Ollama (local) | `http://localhost:11434/v1` | (empty) | `llama3.1` |
| LM Studio (local) | `http://localhost:1234/v1` | (empty) | `local-model` |
| vLLM (local) | `http://localhost:8000/v1` | (empty) | `meta-llama/Llama-3.1-8B` |
| llama.cpp server | `http://localhost:8080/v1` | (empty) | `default` |
| LocalAI | `http://localhost:8080/v1` | (empty) | model name |
| Together AI | `https://api.together.xyz/v1` | `...` | model name |
| Groq | `https://api.groq.com/openai/v1` | `...` | model name |
| No LLM | (empty) | -- | -- |

**Implementations:**
- `OpenAICompatibleClient` -- calls `/chat/completions`, handles JSON fences
- `StubLLMClient` -- returns deterministic "no LLM" message

### 2. Question Router (`reasoning/question_router.py`)

Classifies questions using keyword pattern matching:

| Type | Example Questions | Retrieval Strategy |
|------|-------------------|--------------------|
| ARCHITECTURE | "How is the system structured?" | Module summaries + broad search |
| FLOW | "What happens when CreateOrder is called?" | Symbol + outbound call edges |
| COMPONENT | "What does UserService do?" | Symbol + direct neighborhood |
| IMPACT | "What would break if I change GetById?" | Symbol + inbound call edges (3 hops) |
| GENERAL | "How many controllers are there?" | Vector search only |

Also extracts target symbols from:
- Backtick-quoted names: `` `MyApp.Foo` ``
- Dotted identifiers: `MyApp.Services.UserService`
- PascalCase names: `UserService`

### 3. Hybrid Retriever (`reasoning/retriever.py`)

Combines two retrieval strategies:

**Vector search:** Embeds the question, searches the summary vector
store for semantically similar records.

**Graph expansion:** Starting from the target symbol, performs BFS
traversal of call edges in the database:
- FLOW/COMPONENT: outbound edges (what does it call?)
- IMPACT: inbound edges (what calls it?)
- ARCHITECTURE: module-level summaries

### 4. Answer Builder (`reasoning/answer_builder.py`)

Two modes:

**Deterministic (no LLM):**
- Formats symbol info, call edges, and summaries into structured text
- Always produces evidence with file paths and line numbers
- Builds verification checklists tailored to question type

**LLM-enriched:**
- Sends system prompt + context to LLM
- Requests JSON response format
- Parses evidence, confidence, verification from LLM output
- Falls back to deterministic on LLM failure

### 5. Data Models (`reasoning/models.py`)

```
Question
  - text, snapshot_id, question_type, target_symbol, max_hops

Answer
  - question, question_type, answer_text
  - evidence: [{file_path, symbol_fq_name, start_line, end_line, relevance}]
  - confidence: high | medium | low
  - verification: [{description, how_to_verify}]
  - related_symbols: [fq_name, ...]
  - error: "" (or error message if LLM failed)
```

## API Endpoints

### `POST /repos/{id}/snapshots/{sid}/ask`

Ask a question about the codebase.

**Request:**
```json
{
  "question": "What does OrderService.CreateOrder do?",
  "target_symbol": "MyApp.OrderService.CreateOrder"  // optional
}
```

**Response:**
```json
{
  "question": "What does OrderService.CreateOrder do?",
  "question_type": "component",
  "answer_text": "**Method `MyApp.OrderService.CreateOrder`**: declared in `OrderService.cs` (lines 10-25)...",
  "evidence": [
    {
      "file_path": "OrderService.cs",
      "symbol_fq_name": "MyApp.OrderService.CreateOrder",
      "start_line": 10,
      "end_line": 25,
      "relevance": "Direct symbol match"
    }
  ],
  "confidence": "high",
  "verification": [
    {
      "description": "Verify the component's behaviour matches the description",
      "how_to_verify": "Read the source code at the cited file and line range"
    }
  ],
  "related_symbols": ["MyApp.OrderService", "MyApp.OrderService.CreateOrder"],
  "error": ""
}
```

### `POST /repos/{id}/snapshots/{sid}/classify`

Debug endpoint: classify a question without generating an answer.

**Response:**
```json
{
  "question": "What would break if I change UserService?",
  "question_type": "impact",
  "target_symbol": "UserService"
}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EIDOS_LLM_BASE_URL` | `""` | OpenAI-compatible endpoint (empty = no LLM) |
| `EIDOS_LLM_API_KEY` | `""` | API key (empty for local models) |
| `EIDOS_LLM_MODEL` | `gpt-4o-mini` | Model name |
| `EIDOS_LLM_TEMPERATURE` | `0.1` | Low for deterministic answers |
| `EIDOS_LLM_MAX_TOKENS` | `2048` | Response length limit |
| `EIDOS_LLM_TIMEOUT` | `60` | Seconds before timeout |

## Connecting a Local LLM

### Ollama
```bash
# Install and start Ollama
ollama serve

# Pull a model
ollama pull llama3.1

# Set env vars
export EIDOS_LLM_BASE_URL="http://localhost:11434/v1"
export EIDOS_LLM_MODEL="llama3.1"
```

### LM Studio
```bash
# Start LM Studio server on port 1234
export EIDOS_LLM_BASE_URL="http://localhost:1234/v1"
export EIDOS_LLM_MODEL="local-model"
```

### vLLM
```bash
python -m vllm.entrypoints.openai.api_server --model meta-llama/Llama-3.1-8B
export EIDOS_LLM_BASE_URL="http://localhost:8000/v1"
export EIDOS_LLM_MODEL="meta-llama/Llama-3.1-8B"
```
