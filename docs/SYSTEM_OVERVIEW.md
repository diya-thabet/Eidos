# Eidos - System Overview

Welcome to Eidos, a code intelligence platform. This document explains how the system works in simple terms, and lists every endpoint with its description.

---

## What is Eidos?

Eidos is a tool that helps developers understand their code. You give it a Git repository, and it:

1. **Reads** all the source code files (Python, Java, C#, TypeScript, Go, Rust, C, C++)
2. **Builds a map** of every class, function, and connection between them
3. **Writes summaries** explaining what each piece of code does
4. **Generates documentation** automatically
5. **Reviews code changes** for risks before you merge them
6. **Answers questions** about your codebase in plain English
7. **Scores code health** with 40 rules checking for common problems

You interact with Eidos through a REST API. No frontend is needed - you can use it from your terminal, CI/CD pipeline, or any HTTP client.

---

## How It Works (Step by Step)

### Step 1: Register a Repository

You tell Eidos about your Git repo by sending the URL.

### Step 2: Ingest the Code

Eidos clones the repo, reads every file, and:
- Parses the code into an AST (abstract syntax tree) using tree-sitter
- Finds all classes, functions, interfaces, and their relationships
- Stores everything in a database

If you run ingestion again later, Eidos only re-parses files that changed (incremental ingestion). This is much faster for large repos.

### Step 3: Use the Analysis

Once ingested, you can:
- Search for any symbol by name
- View the full code graph (who calls what)
- Generate documentation
- Ask questions in natural language
- Submit a PR diff for risk review
- Check code health scores
- Export everything as a portable file

---

## Key Concepts

| Concept | What It Means |
|---------|---------------|
| **Repo** | A Git repository you registered with Eidos |
| **Snapshot** | One analysis of a repo at a specific commit. You can have many snapshots per repo. |
| **Symbol** | A class, function, method, interface, enum, or struct found in your code |
| **Edge** | A connection between two symbols (calls, inherits, implements, uses) |
| **Summary** | A short explanation of what a symbol, file, or module does |
| **Health rule** | One of 40 checks for code problems (long methods, circular dependencies, etc.) |

---

## Authentication

Eidos supports three ways to log in:

1. **GitHub OAuth** - Click a link, log in with GitHub, get a token
2. **Google OAuth** - Same flow but with Google
3. **API Key** - Create a key for scripts and CI/CD pipelines (no browser needed)

When auth is disabled (development mode), everything works without a token.

---

## All Endpoints

Below is every endpoint in the system. They are grouped by what they do.

### Health Checks

| Method | Path | What It Does |
|--------|------|--------------|
| GET | `/health` | Returns "ok" if the server is running |
| GET | `/health/ready` | Checks if the database and services are working |

### Authentication

| Method | Path | What It Does |
|--------|------|--------------|
| GET | `/auth/login` | Opens the GitHub login page |
| GET | `/auth/callback` | Handles the GitHub login response and gives you a token |
| GET | `/auth/google/login` | Opens the Google login page |
| GET | `/auth/google/callback` | Handles the Google login response and gives you a token |
| GET | `/auth/me` | Shows your user information |
| POST | `/auth/logout` | Tells the server you logged out (you should delete your token) |
| POST | `/auth/api-keys?name=...` | Creates a new API key. The key is shown only once - save it! |
| GET | `/auth/api-keys` | Lists your API keys (shows name and prefix, not the full key) |
| DELETE | `/auth/api-keys/{key_id}` | Deletes an API key so it cannot be used anymore |

### Repository Management

| Method | Path | What It Does |
|--------|------|--------------|
| POST | `/repos/` | Register a new repository (give it a name and Git URL) |
| GET | `/repos/` | List all your repositories |
| GET | `/repos/{repo_id}/status` | Check the status of a repo and its latest snapshot |
| GET | `/repos/{repo_id}/detail` | Detailed info about a repo including all snapshots |
| PATCH | `/repos/{repo_id}` | Update a repo (change name, branch, etc.) |
| DELETE | `/repos/{repo_id}` | Delete a repo and all its data |
| POST | `/repos/{repo_id}/ingest` | Start analyzing the code (clone + parse + index) |

### Code Analysis

| Method | Path | What It Does |
|--------|------|--------------|
| GET | `/repos/{repo_id}/snapshots/{sid}/symbols` | List all symbols (classes, functions) found in the code |
| GET | `/repos/{repo_id}/snapshots/{sid}/symbols/{fq_name}` | Get details about one specific symbol |
| GET | `/repos/{repo_id}/snapshots/{sid}/edges` | List all connections between symbols |
| GET | `/repos/{repo_id}/snapshots/{sid}/callgraph/{fq_name}` | Show who calls a function and who it calls |
| GET | `/repos/{repo_id}/snapshots/{sid}/overview` | High-level stats: total files, symbols, edges, languages |
| GET | `/repos/{repo_id}/snapshots/{sid}/health` | Run 40 code health rules and get a score out of 100 |

### Search

| Method | Path | What It Does |
|--------|------|--------------|
| GET | `/repos/{repo_id}/snapshots/{sid}/search?q=...` | Search for symbols, summaries, or docs by keyword |
| GET | `/repos/{repo_id}/snapshots/{sid}/fulltext?q=...` | Full-text search with ranking (uses PostgreSQL when available) |
| GET | `/repos/{repo_id}/snapshots/{sid}/diff/{other_sid}` | Compare two snapshots - what symbols were added, removed, or changed |
| GET | `/repos/{repo_id}/snapshots/{sid}/export` | Download all analysis results as JSON |

### Questions and Answers

| Method | Path | What It Does |
|--------|------|--------------|
| POST | `/repos/{repo_id}/snapshots/{sid}/ask` | Ask a question about the code in plain English |

### Code Reviews

| Method | Path | What It Does |
|--------|------|--------------|
| POST | `/repos/{repo_id}/snapshots/{sid}/review` | Submit a code diff and get a risk analysis |
| GET | `/repos/{repo_id}/snapshots/{sid}/reviews` | List all past reviews for a snapshot |

### Documentation

| Method | Path | What It Does |
|--------|------|--------------|
| POST | `/repos/{repo_id}/snapshots/{sid}/docs/generate` | Generate documentation for the codebase |
| GET | `/repos/{repo_id}/snapshots/{sid}/docs` | List all generated documents |
| GET | `/repos/{repo_id}/snapshots/{sid}/docs/{doc_id}` | Get one specific document |

### Evaluations (Quality Checks)

| Method | Path | What It Does |
|--------|------|--------------|
| POST | `/repos/{repo_id}/snapshots/{sid}/evaluate` | Run quality checks on generated content |
| GET | `/repos/{repo_id}/snapshots/{sid}/evaluations` | List all past evaluations |

### Diagrams

| Method | Path | What It Does |
|--------|------|--------------|
| GET | `/repos/{repo_id}/snapshots/{sid}/diagrams/class` | Generate a Mermaid class diagram |
| GET | `/repos/{repo_id}/snapshots/{sid}/diagrams/modules` | Generate a Mermaid module dependency diagram |

### Trends

| Method | Path | What It Does |
|--------|------|--------------|
| GET | `/repos/{repo_id}/health/trend` | See how code health score changed across snapshots |

### Portable Export/Import

| Method | Path | What It Does |
|--------|------|--------------|
| GET | `/repos/{repo_id}/snapshots/{sid}/portable` | Download a compressed .eidos file with all analysis data |
| POST | `/repos/{repo_id}/import` | Upload a .eidos file to restore a snapshot without re-analyzing |

### Indexing

| Method | Path | What It Does |
|--------|------|--------------|
| POST | `/repos/{repo_id}/snapshots/{sid}/index` | Run the summarization and vector indexing pipeline |
| GET | `/repos/{repo_id}/snapshots/{sid}/summaries` | List all generated summaries |

### Webhooks

| Method | Path | What It Does |
|--------|------|--------------|
| POST | `/webhooks/github` | Receive a GitHub push event and auto-analyze the new code |
| POST | `/webhooks/gitlab` | Receive a GitLab push event and auto-analyze |
| POST | `/webhooks/push` | Receive a generic push event from any Git provider |

### Admin

| Method | Path | What It Does |
|--------|------|--------------|
| GET | `/admin/users` | List all users (admin only) |
| GET | `/admin/users/{user_id}` | Get details about one user |
| PATCH | `/admin/users/{user_id}/role` | Change a user's role (user, admin, etc.) |
| GET | `/admin/plans` | List all subscription plans |
| POST | `/admin/plans` | Create a new plan |
| GET | `/admin/usage` | View usage statistics |

### Monitoring

| Method | Path | What It Does |
|--------|------|--------------|
| GET | `/metrics` | Prometheus metrics - request counts, latency, ingestion stats |

---

## How Authentication Works

### For Browser Users (OAuth)
1. Open `/auth/login` in your browser
2. Log in with GitHub
3. You get redirected back with a JWT token
4. Use the token in every request: `Authorization: Bearer YOUR_TOKEN`

### For Scripts and CI/CD (API Keys)
1. Create a key: `POST /auth/api-keys?name=my-ci`
2. Save the key from the response (it is shown only once)
3. Use it in every request: `X-API-Key: eidos_abc123...`

---

## How Incremental Ingestion Works

When you ingest the same repo a second time:

1. Eidos compares file hashes between the old and new version
2. Files with the same hash are skipped (no re-parsing needed)
3. Only changed or new files are parsed
4. Symbols from unchanged files are copied from the previous snapshot

This means analyzing a repo with 10,000 files where only 5 changed takes seconds instead of minutes.

---

## Code Health Rules

Eidos checks your code against 40 rules in 8 categories:

| Category | Examples |
|----------|----------|
| **Clean Code** | Methods too long, too many parameters, empty methods |
| **SOLID** | God classes, deep inheritance, fat interfaces |
| **Complexity** | High fan-out, tight coupling, low cohesion |
| **Design** | Circular dependencies, dead code, feature envy |
| **Naming** | Short names, misleading boolean names, Hungarian notation |
| **Documentation** | Missing docstrings on public classes/methods |
| **Security** | Hardcoded secrets, SQL injection risks, exposed passwords |
| **Best Practices** | Files too large, unused imports, deep nesting |

Each rule gives a severity (info, warning, error) and a suggestion for how to fix it.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API framework | FastAPI (Python) |
| Database | PostgreSQL (production) or SQLite (development) |
| Code parsing | tree-sitter (9 language grammars) |
| Authentication | JWT + OAuth 2.0 (GitHub, Google) + API keys |
| Logging | JSON (production) or text (development) |
| Metrics | Prometheus-compatible `/metrics` endpoint |
| Vector search | Qdrant (optional, for semantic search) |

---

## Numbers

| Metric | Value |
|--------|-------|
| Python source lines | 39,719 |
| Application files | 100 |
| Test files | 78 |
| Automated tests | 1,779 |
| API endpoints | 55 |
| Language parsers | 9 (all validated on real repos) |
| Code health rules | 40 |
| Test-to-code ratio | 1.05:1 (tests exceed code!) |
