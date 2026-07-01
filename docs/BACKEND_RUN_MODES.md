# Backend Run Modes — Demo Mode and Real Mode

This guide explains how to start the Eidos backend in two modes:

1. **Demo mode** for presentations, local testing and quick validation.
2. **Real mode** for persistent data, authentication and production-like usage.

---

## 1. Prerequisites

From the repository root:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

On Linux/macOS:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## 2. Demo Mode

Demo mode is the easiest mode for showing the project or testing the backend locally. It disables authentication and uses an in-memory database.

### 2.1 When to Use Demo Mode

Use demo mode when:

- You want to present the project quickly.
- You do not want to configure PostgreSQL.
- You do not want to configure OAuth.
- You want a backend that starts with minimal setup.
- You only need temporary data for a demo.

### 2.2 Start Demo Mode with PowerShell

```powershell
cd backend
.venv\Scripts\Activate.ps1
$env:EIDOS_DEMO_MODE = "true"
$env:EIDOS_IN_MEMORY_DB = "true"
$env:EIDOS_AUTH_ENABLED = "false"
$env:EIDOS_DATABASE_URL = "sqlite+aiosqlite://"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2.3 Start Demo Mode with Command Prompt

```bat
cd backend
.venv\Scripts\activate
set EIDOS_DEMO_MODE=true
set EIDOS_IN_MEMORY_DB=true
set EIDOS_AUTH_ENABLED=false
set EIDOS_DATABASE_URL=sqlite+aiosqlite://
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2.4 Start Demo Mode with `.env`

Create or update `backend/.env`:

```env
EIDOS_DEMO_MODE=true
EIDOS_IN_MEMORY_DB=true
EIDOS_AUTH_ENABLED=false
EIDOS_DATABASE_URL=sqlite+aiosqlite://
EIDOS_RATE_LIMIT_ENABLED=false
```

Then run:

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2.5 Verify Demo Mode

Open:

```text
http://127.0.0.1:8000/health
```

Open Swagger UI:

```text
http://127.0.0.1:8000/docs
```

A normal demo workflow is:

1. Register a repository with `POST /repos/`.
2. Trigger ingestion with `POST /repos/{repo_id}/ingest`.
3. Check status with `GET /repos/{repo_id}/status`.
4. Explore symbols, edges and overview endpoints.
5. Run health analysis.
6. Generate documentation.
7. Export the analysis if needed.

---

## 3. Real Mode

Real mode is used for realistic local deployment, staging or production-like usage. It should use persistent storage and authentication.

### 3.1 When to Use Real Mode

Use real mode when:

- You need persistent repository and snapshot data.
- You want authentication enabled.
- You want API keys and RBAC.
- You want PostgreSQL.
- You want optional services such as Qdrant, Redis or an LLM provider.

### 3.2 Recommended Real Mode Services

A real setup normally includes:

- FastAPI backend.
- PostgreSQL database.
- Optional Qdrant vector store.
- Optional Redis for cache/queue/rate limiting extensions.
- Optional OpenAI-compatible LLM provider.

### 3.3 Real Mode `.env` Example

Create or update `backend/.env`:

```env
EIDOS_DEMO_MODE=false
EIDOS_IN_MEMORY_DB=false
EIDOS_AUTH_ENABLED=true

EIDOS_DATABASE_URL=postgresql+asyncpg://eidos_user:eidos_password@localhost:5432/eidos
EIDOS_SECRET_KEY=replace-with-a-long-random-secret-key

EIDOS_CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]

# Optional LLM configuration
EIDOS_LLM_API_KEY=replace-with-your-api-key
EIDOS_LLM_BASE_URL=https://api.openai.com/v1
EIDOS_LLM_MODEL=gpt-4o-mini

# Optional vector store
EIDOS_QDRANT_URL=http://localhost:6333
```

These names match the backend `Settings` class, which uses the `EIDOS_` environment prefix.

### 3.4 Start Real Mode

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For local development with auto-reload:

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3.5 Verify Real Mode

Check the health endpoint:

```text
http://127.0.0.1:8000/health
```

Check readiness:

```text
http://127.0.0.1:8000/health/ready
```

---

## 5. LLM Provider Configuration

Both demo and real modes support **dynamic LLM provider management**. You can configure LLM providers in two ways:

### Option A: Environment Variables (Simple)

```bash
EIDOS_LLM_BASE_URL=https://api.fanar.qa/v1
EIDOS_LLM_API_KEY=your-api-key
EIDOS_LLM_MODEL=Fanar-C-2-27B
```

### Option B: Admin API (Recommended for Production)

Register providers at runtime without restart:

```bash
# Register Fanar
curl -X POST http://localhost:8000/admin/llm-providers \
  -H "Content-Type: application/json" \
  -d '{"name":"Fanar","base_url":"https://api.fanar.qa/v1","api_key":"YOUR_KEY","default_model":"Fanar-C-2-27B"}'

# Set as default
curl -X POST http://localhost:8000/admin/llm-providers/{id}/set-default

# Test connectivity
curl -X POST http://localhost:8000/admin/llm-providers/{id}/test
```

See `docs/LLM_PROVIDER_API.md` for full API reference.

### Config Resolution Order

1. DB-registered default provider (if active)
2. Environment variables (`EIDOS_LLM_*`)
3. No LLM (deterministic analysis only)

Open Swagger UI:

```text
http://127.0.0.1:8000/docs
```

When authentication is enabled, protected endpoints require either:

```http
Authorization: Bearer <jwt-token>
```

or:

```http
X-API-Key: <api-key>
```

---

## 4. Demo Mode vs Real Mode

| Area | Demo Mode | Real Mode |
|---|---|---|
| Purpose | Quick presentation and local tests | Staging or production-like usage |
| Database | In-memory SQLite | PostgreSQL recommended |
| Authentication | Disabled | Enabled |
| Persistence | Temporary | Persistent |
| OAuth | Not required | GitHub/Google OAuth can be configured |
| API keys | Optional | Recommended for CI/CD |
| Vector store | Optional or in-memory | Qdrant optional |
| LLM | Optional or disabled | Optional configured provider |
| Best for | Demos and local exploration | Real users and real repositories |

---

## 5. Common Problems

### Port Already Used

```bash
uvicorn app.main:app --reload --port 8001
```

### Authentication Blocks Requests

For demo mode, set:

```env
EIDOS_AUTH_ENABLED=false
```

For real mode, authenticate with OAuth or an API key.

### Database Connection Fails

Check that:

- PostgreSQL is running.
- The database exists.
- The username and password are correct.
- `EIDOS_DATABASE_URL` uses `postgresql+asyncpg://`.

### No LLM Answers

The static-analysis backend still works without an LLM. Natural-language answers and generated summaries may be limited unless an LLM provider is configured.

### Ingestion Is Slow

Large repositories can take longer. Use repository status endpoints to follow progress. Later ingestions are faster because unchanged files are skipped.

---

## 6. Quick Checklist

- [ ] `GET /health` works.
- [ ] `GET /health/ready` works in real mode.
- [ ] Swagger UI opens at `/docs`.
- [ ] Repository registration works.
- [ ] Ingestion can be triggered.
- [ ] Symbols and overview are available after ingestion.
- [ ] Authentication is disabled only in demo mode.
- [ ] Authentication is enabled in real mode.
