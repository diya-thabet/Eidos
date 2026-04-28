# API Response Reference

Every JSON shape the backend returns. Use this to build TypeScript interfaces and React Query hooks.

All paginated endpoints return this wrapper:

```json
{
  "items": [...],
  "total": 42,
  "limit": 50,
  "offset": 0,
  "has_more": false
}
```

---

## Health & Monitoring

### GET /health

```json
{ "status": "ok" }
```

### GET /health/ready

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "qdrant": "unavailable"
  }
}
```

Status is `"ready"` or `"degraded"`. Each check is `"ok"` or `"unavailable"`.

### GET /metrics

Not JSON. Returns Prometheus text format (`text/plain`):

```
# HELP eidos_requests_total Total HTTP requests.
# TYPE eidos_requests_total counter
eidos_requests_total{method="GET",path="/health",status="200"} 5
eidos_request_duration_seconds{method="GET",path="/health",quantile="0.5"} 0.001
eidos_ingestions_total{status="completed"} 3
```

---

## Authentication

### POST /auth/api-keys?name=my-key

The raw key is shown ONLY in this response. Save it.

```json
{
  "id": "c574fdd09851",
  "name": "my-key",
  "key": "eidos_2WW9PMy-43hgA_VZeHi2qCNJVvfGBTXu7E9boJMakII",
  "prefix": "eidos_2WW9PM"
}
```

### GET /auth/api-keys

Array of keys. The full key is never returned again.

```json
[
  {
    "id": "c574fdd09851",
    "name": "my-key",
    "prefix": "eidos_2WW9PM",
    "created_at": "2025-07-15T10:30:00.000000"
  }
]
```

### DELETE /auth/api-keys/{key_id}

```json
{ "status": "revoked" }
```

---

## Repository Management

### GET /repos/{id}/status

```json
{
  "repo_id": "r1",
  "name": "my-repo",
  "snapshots": [
    {
      "id": "s1",
      "repo_id": "r1",
      "commit_sha": "abc123def456",
      "status": "completed",
      "file_count": 150,
      "error_message": null,
      "progress_percent": 100,
      "progress_message": "Ingestion complete",
      "created_at": "2025-07-15T10:30:00.000000"
    }
  ]
}
```

Snapshot `status` is one of: `"pending"`, `"running"`, `"completed"`, `"failed"`.

Poll this endpoint during ingestion. Show `progress_percent` and `progress_message` in a progress bar.

### POST /repos

Request:
```json
{ "name": "my-repo", "url": "https://github.com/user/repo" }
```

Response (201):
```json
{
  "id": "a1b2c3d4e5f6",
  "name": "my-repo",
  "url": "https://github.com/user/repo",
  "default_branch": "main"
}
```

---

## Code Analysis

### GET /repos/{id}/snapshots/{sid}/symbols

Paginated. Query params: `?limit=50&offset=0&kind=class&file_path=main.py`

Each item:

```json
{
  "id": 1,
  "kind": "class",
  "name": "UserService",
  "fq_name": "app.UserService",
  "file_path": "main.py",
  "start_line": 1,
  "end_line": 50,
  "namespace": "app",
  "parent_fq_name": null,
  "signature": "class UserService:",
  "modifiers": "public",
  "return_type": ""
}
```

`kind` is one of: `"class"`, `"method"`, `"function"`, `"interface"`, `"struct"`, `"enum"`, `"constructor"`, `"property"`, `"field"`.

`parent_fq_name` is set when a method belongs to a class.

### GET /repos/{id}/snapshots/{sid}/edges

Paginated. Each item:

```json
{
  "id": 1,
  "source_fq_name": "app.UserService.get_user",
  "target_fq_name": "db.query",
  "edge_type": "calls",
  "file_path": "main.py",
  "line": 15
}
```

`edge_type` is one of: `"calls"`, `"inherits"`, `"implements"`, `"imports"`, `"contains"`, `"uses"`.

### GET /repos/{id}/snapshots/{sid}/overview

```json
{
  "snapshot_id": "s1",
  "total_symbols": 1086,
  "total_edges": 5550,
  "total_modules": 12,
  "symbols_by_kind": {
    "class": 91,
    "method": 296,
    "function": 45,
    "interface": 3
  },
  "entry_points": [
    { "fq_name": "app.main", "kind": "function", "file_path": "main.py" }
  ],
  "hotspots": [
    { "fq_name": "app.UserService", "kind": "class", "fan_out": 25, "lines": 200 }
  ]
}
```

### GET /repos/{id}/snapshots/{sid}/callgraph/{fq_name}

```json
{
  "center": "app.UserService.get_user",
  "callers": [
    { "fq_name": "app.routes.user_endpoint", "edge_type": "calls", "file_path": "routes.py", "line": 42 }
  ],
  "callees": [
    { "fq_name": "db.query", "edge_type": "calls", "file_path": "main.py", "line": 15 }
  ]
}
```

---

## Code Health

### POST /repos/{id}/snapshots/{sid}/health

Optional request body (all fields optional):

```json
{
  "categories": ["clean_code", "solid", "security"],
  "max_method_lines": 60,
  "max_params": 5,
  "max_fan_out": 10,
  "use_llm": false
}
```

Response:

```json
{
  "overall_score": 77.4,
  "findings_count": 1696,
  "total_symbols": 1086,
  "total_files": 150,
  "category_scores": {
    "clean_code": 85.0,
    "solid": 90.0,
    "complexity": 72.0,
    "design": 65.0,
    "documentation": 40.0,
    "naming": 95.0,
    "best_practices": 80.0,
    "security": 100.0
  },
  "findings": [
    {
      "rule_id": "SM001",
      "rule_name": "dead_method",
      "category": "design",
      "severity": "warning",
      "symbol": "app.UserService.get_user",
      "file": "main.py",
      "line": 10,
      "message": "Method is never called (dead code)",
      "suggestion": "Remove if unused, or add tests that exercise it"
    }
  ],
  "summary": "77.4/100 - 1696 findings across 8 categories",
  "llm_insights": null
}
```

`severity` is one of: `"info"`, `"warning"`, `"error"`.

`category` is one of: `"clean_code"`, `"solid"`, `"complexity"`, `"design"`, `"documentation"`, `"naming"`, `"best_practices"`, `"security"`.

### GET /repos/{id}/snapshots/{sid}/health/rules

Array of all 40 rules:

```json
[
  {
    "rule_id": "CC001",
    "rule_name": "long_method",
    "category": "clean_code",
    "severity": "warning",
    "description": "Method exceeds maximum line count"
  }
]
```

---

## Search

### GET /repos/{id}/snapshots/{sid}/search?q=User

Paginated. Each item:

```json
{
  "entity_type": "symbol",
  "entity_id": "app.UserService",
  "title": "class: app.UserService",
  "snippet": "class UserService:",
  "file_path": "main.py",
  "score": 8.0,
  "metadata": {
    "kind": "class",
    "start_line": 1,
    "end_line": 50
  }
}
```

`entity_type` is one of: `"symbol"`, `"summary"`, `"doc"`.

### GET /repos/{id}/snapshots/{sid}/fulltext?q=User

Same shape as search. Uses PostgreSQL tsvector ranking when available, ILIKE fallback otherwise.

### GET /repos/{id}/snapshots/{sid}/diff/{other_sid}

```json
{
  "base_snapshot_id": "s1",
  "compare_snapshot_id": "s2",
  "added_symbols": [...],
  "removed_symbols": [...],
  "modified_symbols": [...]
}
```

---

## Q&A

### POST /repos/{id}/snapshots/{sid}/ask

Request:
```json
{ "question": "What does UserService do?" }
```

Response:
```json
{
  "question": "What does UserService do?",
  "question_type": "explanation",
  "answer_text": "UserService handles user-related operations...",
  "evidence": [
    {
      "file_path": "main.py",
      "symbol_fq_name": "app.UserService",
      "start_line": 1,
      "end_line": 50,
      "snippet": "",
      "relevance": "Direct symbol match"
    }
  ],
  "confidence": "low",
  "verification": null,
  "related_symbols": ["app.UserService", "app.UserService.get_user"],
  "error": null
}
```

`confidence` is one of: `"high"`, `"medium"`, `"low"`.

`question_type` is one of: `"explanation"`, `"location"`, `"comparison"`, `"architecture"`, `"debugging"`.

Without an LLM, `answer_text` will be empty and `confidence` will be `"low"`. The `evidence` and `related_symbols` still work.

---

## Code Reviews

### POST /repos/{id}/snapshots/{sid}/review

Request:
```json
{ "diff": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new" }
```

Response:
```json
{
  "id": 1,
  "snapshot_id": "s1",
  "diff_summary": { "files": 1, "additions": 1, "deletions": 1 },
  "files_changed": ["main.py"],
  "changed_symbols": [],
  "findings": [
    {
      "category": "behavioral",
      "severity": "info",
      "title": "Modified function",
      "description": "Logic change in main.py",
      "file_path": "main.py",
      "line": 1
    }
  ],
  "impacted_symbols": [],
  "risk_score": 20,
  "risk_level": "low",
  "llm_summary": null
}
```

`risk_level` is one of: `"low"`, `"medium"`, `"high"`, `"critical"`.

---

## Documentation

### POST /repos/{id}/snapshots/{sid}/docs

Response:
```json
{
  "snapshot_id": "s1",
  "documents": [
    {
      "id": 1,
      "doc_type": "readme",
      "title": "README",
      "scope_id": "",
      "markdown": "# README\n\n> Auto-generated from snapshot...\n\n## Overview\n\n..."
    },
    {
      "id": 2,
      "doc_type": "architecture",
      "title": "Architecture Overview",
      "scope_id": "",
      "markdown": "# Architecture\n\n..."
    }
  ],
  "total": 4
}
```

`doc_type` is one of: `"readme"`, `"architecture"`, `"module"`, `"runbook"`.

`markdown` is the full document content in Markdown format. Render it with a Markdown renderer.

---

## Evaluations

### POST /repos/{id}/snapshots/{sid}/evaluate

Response:
```json
{
  "id": 1,
  "snapshot_id": "s1",
  "scope": "full",
  "overall_score": 0.95,
  "overall_severity": "pass",
  "checks": [
    {
      "category": "doc_completeness",
      "name": "docs_exist",
      "passed": true,
      "severity": "pass",
      "score": 1.0,
      "message": "4 document(s) generated.",
      "details": {}
    }
  ],
  "summary": "All 12 checks passed."
}
```

`severity` is one of: `"pass"`, `"warning"`, `"fail"`.

---

## Diagrams

### GET /repos/{id}/snapshots/{sid}/diagram?diagram_type=class

```json
{
  "snapshot_id": "s1",
  "diagram_type": "class",
  "mermaid": "classDiagram\n    class app_UserService {\n        -get_user() User\n    }\n    BaseService <|-- app_UserService",
  "node_count": 1,
  "edge_count": 1
}
```

`diagram_type` is `"class"` or `"module"`.

`mermaid` is a Mermaid.js diagram string. Render it with the mermaid library.

---

## Trends

### GET /repos/{id}/health/trend

```json
{
  "repo_id": "r1",
  "snapshots": [
    { "snapshot_id": "s1", "score": 77.4, "findings_count": 1696, "created_at": "2025-07-01" },
    { "snapshot_id": "s2", "score": 82.1, "findings_count": 1200, "created_at": "2025-07-15" }
  ]
}
```

Use this for a line chart showing health score over time.

---

## Export & Portable

### GET /repos/{id}/snapshots/{sid}/export

Full JSON dump:

```json
{
  "snapshot_id": "s1",
  "symbols": [...],
  "edges": [...],
  "summaries": [...],
  "docs": [...],
  "metadata": { "repo_name": "demo", "commit_sha": "abc123" }
}
```

### GET /repos/{id}/snapshots/{sid}/portable

Returns binary gzip file. Content-Type: `application/gzip`.

Decompress to get JSON with `schema_version`, `symbols`, `edges`, `files`, `summaries`, `docs`.

Trigger a file download in the browser:
```ts
const res = await fetch(`${API}/repos/${id}/snapshots/${sid}/portable`);
const blob = await res.blob();
const url = URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
a.download = `${repoName}.eidos`;
a.click();
```

### POST /repos/{id}/import

Multipart file upload. Field name: `file`.

```ts
const form = new FormData();
form.append('file', file); // File object from <input type="file">
const res = await fetch(`${API}/repos/${id}/import`, { method: 'POST', body: form });
```

Response (201):
```json
{
  "snapshot_id": "s-imported-abc",
  "symbols_imported": 1086,
  "edges_imported": 5550,
  "files_imported": 150
}
```

---

## Indexing

### POST /repos/{id}/snapshots/{sid}/index

Triggers summarization pipeline. Response:

```json
{
  "snapshot_id": "s1",
  "symbol_summaries": 50,
  "module_summaries": 5,
  "file_summaries": 20
}
```

### GET /repos/{id}/snapshots/{sid}/summaries

Paginated. Each item:

```json
{
  "id": 1,
  "scope": "symbol",
  "scope_id": "app.UserService",
  "summary": "UserService handles user CRUD operations.",
  "facts": ["Contains 5 methods", "Inherits from BaseService"]
}
```

---

## Webhooks (server-to-server, not for frontend)

These are called by GitHub/GitLab, not the frontend. Listed for completeness.

- `POST /webhooks/github` - receives GitHub push events
- `POST /webhooks/gitlab` - receives GitLab push events
- `POST /webhooks/push` - generic push (any provider)

All return:
```json
{ "status": "accepted", "snapshot_id": "s-new-abc" }
```

---

## Admin

### GET /admin/users

```json
[
  { "id": "u1", "email": "user@example.com", "role": "user", "created_at": "2025-07-15" }
]
```

### PATCH /admin/users/{uid}/role

Request: `{ "role": "admin" }`

Roles: `"user"`, `"admin"`, `"viewer"`, `"billing"`, `"super_admin"`.

### GET /admin/plans

```json
[
  { "id": "free", "name": "Free", "max_repos": 3, "max_snapshots": 10, "price_cents": 0 }
]
```

### GET /admin/usage

```json
{
  "total_users": 42,
  "total_repos": 15,
  "total_snapshots": 67,
  "total_symbols": 125000,
  "ingestions_today": 5
}
```

---

## Error Responses

All errors follow this shape:

```json
{ "detail": "Snapshot not found" }
```

Status codes:
- `400` - bad request (validation error)
- `401` - not authenticated
- `403` - not authorized (wrong role)
- `404` - resource not found
- `405` - method not allowed
- `422` - validation error (Pydantic)
- `429` - rate limited
- `500` - server error

Validation errors (422) include field details:

```json
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## TypeScript Interfaces (copy-paste ready)

```ts
// Pagination wrapper
interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

// Symbol
interface Symbol {
  id: number;
  kind: 'class' | 'method' | 'function' | 'interface' | 'struct' | 'enum' | 'constructor' | 'property' | 'field';
  name: string;
  fq_name: string;
  file_path: string;
  start_line: number;
  end_line: number;
  namespace: string | null;
  parent_fq_name: string | null;
  signature: string;
  modifiers: string;
  return_type: string;
}

// Edge
interface Edge {
  id: number;
  source_fq_name: string;
  target_fq_name: string;
  edge_type: 'calls' | 'inherits' | 'implements' | 'imports' | 'contains' | 'uses';
  file_path: string;
  line: number | null;
}

// Overview
interface Overview {
  snapshot_id: string;
  total_symbols: number;
  total_edges: number;
  total_modules: number;
  symbols_by_kind: Record<string, number>;
  entry_points: { fq_name: string; kind: string; file_path: string }[];
  hotspots: { fq_name: string; kind: string; fan_out: number; lines: number }[];
}

// Search hit
interface SearchHit {
  entity_type: 'symbol' | 'summary' | 'doc';
  entity_id: string;
  title: string;
  snippet: string;
  file_path: string | null;
  score: number;
  metadata: Record<string, any>;
}

// Health
interface HealthReport {
  overall_score: number;
  findings_count: number;
  total_symbols: number;
  total_files: number;
  category_scores: Record<string, number>;
  findings: HealthFinding[];
  summary: string;
  llm_insights: string | null;
}

interface HealthFinding {
  rule_id: string;
  rule_name: string;
  category: string;
  severity: 'info' | 'warning' | 'error';
  symbol: string;
  file: string;
  line: number;
  message: string;
  suggestion: string;
}

// Q&A
interface AskResponse {
  question: string;
  question_type: string;
  answer_text: string;
  evidence: Evidence[];
  confidence: 'high' | 'medium' | 'low';
  verification: any | null;
  related_symbols: string[];
  error: string | null;
}

interface Evidence {
  file_path: string;
  symbol_fq_name: string;
  start_line: number;
  end_line: number;
  snippet: string;
  relevance: string;
}

// Review
interface ReviewResponse {
  id: number;
  snapshot_id: string;
  diff_summary: { files: number; additions: number; deletions: number };
  files_changed: string[];
  changed_symbols: string[];
  findings: ReviewFinding[];
  impacted_symbols: string[];
  risk_score: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  llm_summary: string | null;
}

interface ReviewFinding {
  category: string;
  severity: string;
  title: string;
  description: string;
  file_path: string;
  line: number | null;
}

// Document
interface Document {
  id: number;
  doc_type: 'readme' | 'architecture' | 'module' | 'runbook';
  title: string;
  scope_id: string;
  markdown: string;
}

// Evaluation
interface EvalResponse {
  id: number;
  snapshot_id: string;
  scope: string;
  overall_score: number;
  overall_severity: 'pass' | 'warning' | 'fail';
  checks: EvalCheck[];
  summary: string;
}

interface EvalCheck {
  category: string;
  name: string;
  passed: boolean;
  severity: 'pass' | 'warning' | 'fail';
  score: number;
  message: string;
  details: Record<string, any>;
}

// Diagram
interface DiagramResponse {
  snapshot_id: string;
  diagram_type: 'class' | 'module';
  mermaid: string;
  node_count: number;
  edge_count: number;
}

// API Key
interface ApiKeyCreate {
  id: string;
  name: string;
  key: string;    // shown only once
  prefix: string;
}

interface ApiKeyListItem {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
}

// Snapshot
interface Snapshot {
  id: string;
  repo_id: string;
  commit_sha: string | null;
  status: 'pending' | 'running' | 'completed' | 'failed';
  file_count: number;
  error_message: string | null;
  progress_percent: number;
  progress_message: string;
  created_at: string;
}

// Repo status
interface RepoStatus {
  repo_id: string;
  name: string;
  snapshots: Snapshot[];
}
```
