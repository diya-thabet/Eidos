# How to Use Eidos — Practical Guide

This guide shows how to interact with every Eidos API endpoint using
**curl** (command line) and **Postman** (GUI).  All examples assume the
server runs at `http://localhost:8000`.

---

## Table of Contents

1. [Start the Server](#1-start-the-server)
2. [Health Check](#2-health-check)
3. [Authentication (Optional)](#3-authentication-optional)
4. [Repository Management](#4-repository-management)
5. [Ingestion (Clone & Analyze)](#5-ingestion-clone--analyze)
6. [Browse Analysis Results](#6-browse-analysis-results)
7. [Summaries & Vector Search](#7-summaries--vector-search)
8. [Ask Questions (Reasoning)](#8-ask-questions-reasoning)
9. [PR Review](#9-pr-review)
10. [Auto-Generate Documentation](#10-auto-generate-documentation)
11. [Run Evaluation / Guardrails](#11-run-evaluation--guardrails)
12. [Private Repositories](#12-private-repositories)
13. [Database Configuration](#13-database-configuration)
14. [Postman Collection Tips](#14-postman-collection-tips)

---

## 1. Start the Server

```bash
# Start infrastructure
cd infra && docker compose up -d

# Start the API
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 2. Health Check

**curl:**
```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{"status": "ok"}
```

**Postman:** GET `http://localhost:8000/health`

---

## 3. Authentication (Optional)

Auth is **disabled by default** (`EIDOS_AUTH_ENABLED=false`).  All
endpoints work without tokens for local development.

### 3a. GitHub OAuth

```bash
# Step 1: Open in browser (redirects to GitHub)
open "http://localhost:8000/auth/login"

# Step 2: After authorizing, the callback returns a JWT
# Response:
# {
#   "access_token": "eyJ...",
#   "token_type": "bearer",
#   "user": { "id": "gh-123", "login": "yourname", ... }
# }

# Step 3: Use the token in subsequent requests
curl -H "Authorization: Bearer eyJ..." http://localhost:8000/auth/me
```

### 3b. Google OAuth

```bash
# Same flow but via Google
open "http://localhost:8000/auth/google/login"
# callback returns JWT + user info
```

### 3c. Get Current User

```bash
curl -H "Authorization: Bearer <YOUR_TOKEN>" \
     http://localhost:8000/auth/me
```

**Response:**
```json
{
  "id": "gh-12345",
  "login": "yourname",
  "name": "Your Name",
  "email": "you@example.com",
  "avatar_url": "https://..."
}
```

---

## 4. Repository Management

### 4a. Register a Public Repository

**curl:**
```bash
curl -X POST http://localhost:8000/repos \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-csharp-project",
    "url": "https://github.com/dotnet/runtime",
    "default_branch": "main"
  }'
```

**Response (201 Created):**
```json
{
  "id": "a1b2c3d4e5f6",
  "name": "my-csharp-project",
  "url": "https://github.com/dotnet/runtime",
  "default_branch": "main",
  "created_at": "2024-12-01T10:00:00+00:00",
  "last_indexed_at": null
}
```

### 4b. Register a Private Repository (with Token)

**curl:**
```bash
curl -X POST http://localhost:8000/repos \
  -H "Content-Type: application/json" \
  -d '{
    "name": "private-project",
    "url": "https://github.com/myorg/private-repo",
    "default_branch": "main",
    "git_provider": "github",
    "git_token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }'
```

Supported `git_provider` values: `github`, `gitlab`, `azure_devops`, `bitbucket`, `other`.

The token is **encrypted at rest** using Fernet (AES-128-CBC) and
never returned in API responses.

### 4c. GitLab Private Repo

```bash
curl -X POST http://localhost:8000/repos \
  -H "Content-Type: application/json" \
  -d '{
    "name": "gitlab-project",
    "url": "https://gitlab.com/myorg/myrepo",
    "git_provider": "gitlab",
    "git_token": "glpat-xxxxxxxxxxxxxxxx"
  }'
```

### 4d. Azure DevOps Private Repo

```bash
curl -X POST http://localhost:8000/repos \
  -H "Content-Type: application/json" \
  -d '{
    "name": "azure-project",
    "url": "https://dev.azure.com/myorg/myproject/_git/myrepo",
    "git_provider": "azure_devops",
    "git_token": "YOUR_PAT_HERE"
  }'
```

### 4e. Check Repo Status

```bash
curl http://localhost:8000/repos/{repo_id}/status
```

**Response:**
```json
{
  "repo_id": "a1b2c3d4e5f6",
  "name": "my-csharp-project",
  "snapshots": [
    {
      "id": "f7e8d9c0b1a2",
      "status": "completed",
      "file_count": 42,
      "commit_sha": "abc123def456",
      "created_at": "2024-12-01T10:01:00+00:00"
    }
  ]
}
```

---

## 5. Ingestion (Clone & Analyze)

**curl:**
```bash
curl -X POST http://localhost:8000/repos/{repo_id}/ingest \
  -H "Content-Type: application/json" \
  -d '{"commit_sha": null}'
```

**Response (202 Accepted):**
```json
{
  "snapshot_id": "f7e8d9c0b1a2",
  "status": "pending"
}
```

The ingestion runs in the background:
1. Clones the repository (with token if private)
2. Scans all indexable files
3. Parses C# files with tree-sitter
4. Builds the code graph (symbols + edges)
5. Generates summaries and vector embeddings
6. Cleans up clone directory (configurable)

**Poll for status:**
```bash
curl http://localhost:8000/repos/{repo_id}/status
# Wait for status to change to "completed"
```

---

## 6. Browse Analysis Results

### 6a. List Symbols

```bash
# All symbols
curl http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/symbols

# Filter by kind
curl "http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/symbols?kind=class"

# Filter by file
curl "http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/symbols?file_path=Program.cs"
```

### 6b. Get a Single Symbol

```bash
curl http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/symbols/MyApp.Program.Main
```

### 6c. List Edges (Call Graph)

```bash
# All edges
curl http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/edges

# Filter by type
curl "http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/edges?edge_type=calls"
```

### 6d. Graph Neighborhood

```bash
curl http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/graph/MyApp.OrderService
```

**Response:**
```json
{
  "symbol": { "fq_name": "MyApp.OrderService", "kind": "class", ... },
  "callers": [...],
  "callees": [...],
  "children": [...]
}
```

### 6e. Analysis Overview

```bash
curl http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/overview
```

---

## 7. Summaries & Vector Search

### 7a. List Summaries

```bash
curl http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/summaries

# Filter by scope
curl "http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/summaries?scope_type=module"
```

### 7b. Search (Vector Similarity)

```bash
curl -X POST http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/search \
  -H "Content-Type: application/json" \
  -d '{"query": "How does the order processing work?", "limit": 5}'
```

---

## 8. Ask Questions (Reasoning)

```bash
curl -X POST http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What does OrderService.PlaceOrder do?"}'
```

**Response:**
```json
{
  "answer": "OrderService.PlaceOrder validates the order, ...",
  "citations": [
    {"file_path": "OrderService.cs", "symbol_fq_name": "App.OrderService.PlaceOrder", "start_line": 10}
  ],
  "confidence": "high"
}
```

---

## 9. PR Review

```bash
curl -X POST http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/reviews \
  -H "Content-Type: application/json" \
  -d '{
    "diff": "diff --git a/OrderService.cs b/OrderService.cs\n--- a/OrderService.cs\n+++ b/OrderService.cs\n@@ -10,3 +10,4 @@\n existing\n+newLine\n end",
    "max_hops": 3
  }'
```

**Response:**
```json
{
  "snapshot_id": "...",
  "risk_score": 45,
  "risk_level": "medium",
  "findings": [
    {
      "category": "complexity",
      "severity": "medium",
      "title": "High fan-out in Main",
      "file_path": "Program.cs",
      "suggestion": "Consider extracting a service"
    }
  ],
  "impacted_symbols": [...]
}
```

---

## 10. Auto-Generate Documentation

### 10a. Generate All Doc Types

```bash
curl -X POST http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/docs/generate \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 10b. Generate a Specific Type

```bash
curl -X POST http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/docs/generate \
  -H "Content-Type: application/json" \
  -d '{"doc_type": "architecture"}'
```

### 10c. List Generated Docs

```bash
curl http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/docs
```

### 10d. Get a Single Doc

```bash
curl http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/docs/{doc_id}
```

---

## 11. Run Evaluation / Guardrails

```bash
curl -X POST http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/evaluate
```

**Response:**
```json
{
  "overall_score": 0.82,
  "overall_severity": "pass",
  "checks": [
    {"name": "hallucinated_symbols", "passed": true, "score": 1.0, ...},
    {"name": "doc_symbol_accuracy",  "passed": true, "score": 0.95, ...},
    {"name": "review_precision",     "passed": true, "score": 0.8, ...}
  ],
  "summary": "8 check(s) passed, 0 failed"
}
```

**List past evaluations:**
```bash
curl http://localhost:8000/repos/{repo_id}/snapshots/{snap_id}/evaluations
```

---

## 12. Private Repositories

Eidos supports private repos from **any Git hosting provider**.
When registering a repo, supply the `git_token` field:

| Provider | `git_provider` | Token Type |
|----------|---------------|------------|
| GitHub | `github` | Personal Access Token (`ghp_...`) |
| GitLab | `gitlab` | Personal Access Token (`glpat-...`) |
| Azure DevOps | `azure_devops` | PAT from Azure portal |
| Bitbucket | `bitbucket` | App password |
| Self-hosted | `other` | Any HTTPS token |

The token is:
- **Encrypted at rest** with Fernet (AES-128-CBC)
- **Never returned** in any API response
- **Used only** during the `git clone` step
- **Injected** into the HTTPS URL (e.g., `https://TOKEN@github.com/...`)

---

## 13. Database Configuration

Eidos uses SQLAlchemy with async drivers.  Switch databases by
changing one environment variable:

```bash
# PostgreSQL (default)
EIDOS_DATABASE_URL=postgresql+asyncpg://eidos:eidos@localhost:5432/eidos

# MySQL
EIDOS_DATABASE_URL=mysql+aiomysql://eidos:eidos@localhost:3306/eidos

# SQLite (for development/testing)
EIDOS_DATABASE_URL=sqlite+aiosqlite:///./eidos.db

# Oracle
EIDOS_DATABASE_URL=oracle+oracledb://eidos:eidos@localhost:1521/eidos

# SQL Server
EIDOS_DATABASE_URL=mssql+aioodbc://eidos:eidos@localhost:1433/eidos?driver=ODBC+Driver+18+for+SQL+Server
```

Install the matching driver:
```bash
pip install asyncpg          # PostgreSQL
pip install aiomysql         # MySQL
pip install aiosqlite        # SQLite
pip install "eidos[mysql]"   # shortcut for MySQL extra
pip install "eidos[oracle]"  # shortcut for Oracle extra
pip install "eidos[mssql]"   # shortcut for SQL Server extra
```

---

## 14. Postman Collection Tips

1. **Import:** Create a new collection, add the base URL as a variable:
   `{{base_url}}` = `http://localhost:8000`

2. **Auth header:** In Collection settings ? Authorization ? Bearer Token,
   set the token to `{{jwt_token}}`.  After login, set the variable.

3. **Endpoints to add:**

   | Name | Method | URL |
   |------|--------|-----|
   | Health | GET | `{{base_url}}/health` |
   | Create Repo | POST | `{{base_url}}/repos` |
   | Ingest | POST | `{{base_url}}/repos/:repo_id/ingest` |
   | Status | GET | `{{base_url}}/repos/:repo_id/status` |
   | Symbols | GET | `{{base_url}}/repos/:repo_id/snapshots/:snap_id/symbols` |
   | Edges | GET | `{{base_url}}/repos/:repo_id/snapshots/:snap_id/edges` |
   | Overview | GET | `{{base_url}}/repos/:repo_id/snapshots/:snap_id/overview` |
   | Ask | POST | `{{base_url}}/repos/:repo_id/snapshots/:snap_id/ask` |
   | Review | POST | `{{base_url}}/repos/:repo_id/snapshots/:snap_id/reviews` |
   | Gen Docs | POST | `{{base_url}}/repos/:repo_id/snapshots/:snap_id/docs/generate` |
   | Evaluate | POST | `{{base_url}}/repos/:repo_id/snapshots/:snap_id/evaluate` |
   | Login (GitHub) | GET | `{{base_url}}/auth/login` |
   | Login (Google) | GET | `{{base_url}}/auth/google/login` |
   | Me | GET | `{{base_url}}/auth/me` |

4. **Chaining:** Use Postman's *Tests* tab to auto-extract IDs:
   ```javascript
   // After "Create Repo"
   pm.collectionVariables.set("repo_id", pm.response.json().id);

   // After "Ingest"
   pm.collectionVariables.set("snap_id", pm.response.json().snapshot_id);
   ```
