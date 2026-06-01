# Demo Mode

Run the entire Eidos backend **without any external infrastructure** — no PostgreSQL, no Redis, no OAuth setup. Perfect for demos, presentations, and quick local testing.

---

## What Demo Mode Does

| Feature | Normal Mode | Demo Mode |
|---------|-------------|-----------|
| Database | PostgreSQL (external) | SQLite in-memory (auto-created) |
| Authentication | JWT / OAuth / API keys | **Disabled** — all endpoints open |
| Rate limiting | Enabled | **Disabled** |
| Data persistence | Permanent | **Lost on restart** (in-memory) |
| External services | Redis, Qdrant, LLM | Not required (graceful fallback) |

---

## Quick Start

### Option 1: Using the demo launcher script

```bash
cd backend
python demo.py
```

### Option 2: Using environment variable + uvicorn

**Linux / macOS:**
```bash
cd backend
EIDOS_DEMO_MODE=true uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Windows PowerShell:**
```powershell
cd backend
$env:EIDOS_DEMO_MODE = "true"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Windows CMD:**
```cmd
cd backend
set EIDOS_DEMO_MODE=true
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Option 3: Using a `.env` file

Create `backend/.env`:
```ini
EIDOS_DEMO_MODE=true
```

Then run:
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Prerequisites (Any PC)

1. **Python 3.11+** installed
2. Install dependencies:
   ```bash
   cd backend
   pip install -e .
   ```
   Or if using `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```

That's it. No database server, no Redis, no API keys needed.

---

## Accessing the API

Once running, open your browser:

| URL | Description |
|-----|-------------|
| http://localhost:8000/docs | **Swagger UI** — interactive API explorer |
| http://localhost:8000/redoc | ReDoc — alternative API docs |
| http://localhost:8000/health | Health check |
| http://localhost:8000/version | Version info |
| http://localhost:8000/metrics | Prometheus metrics |

---

## Demo Workflow Example

No login required. All endpoints work immediately:

```bash
# 1. Check the server is running
curl http://localhost:8000/health
# {"status": "ok"}

# 2. Register a repository
curl -X POST http://localhost:8000/repos \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/diya-thabet/DevOps.git", "name": "my-demo"}'
# {"id": "abc123...", "name": "my-demo", ...}

# 3. List repositories
curl http://localhost:8000/repos
# [{"id": "abc123...", "name": "my-demo", ...}]

# 4. Trigger ingestion (clone + parse + index)
curl -X POST http://localhost:8000/repos/abc123/ingest

# 5. Check ingestion progress
curl http://localhost:8000/repos/abc123/status

# 6. Once ingested, explore the code graph
curl http://localhost:8000/repos/abc123/snapshots/{snap_id}/symbols
curl http://localhost:8000/repos/abc123/snapshots/{snap_id}/edges
curl http://localhost:8000/repos/abc123/snapshots/{snap_id}/graph/overview

# 7. Generate documentation
curl -X POST http://localhost:8000/repos/abc123/snapshots/{snap_id}/docs/generate

# 8. Run code health analysis
curl http://localhost:8000/repos/abc123/snapshots/{snap_id}/analysis/health

# 9. Export as portable .eidos file
curl http://localhost:8000/repos/abc123/snapshots/{snap_id}/export/portable -o snapshot.eidos
```

---

## Configuration Reference

All settings use the `EIDOS_` prefix as environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `EIDOS_DEMO_MODE` | `false` | Enable demo mode (in-memory DB, no auth, no rate limit) |
| `EIDOS_IN_MEMORY_DB` | `false` | Use in-memory SQLite (without full demo mode) |
| `EIDOS_AUTH_ENABLED` | `false` | Enforce authentication |
| `EIDOS_LLM_BASE_URL` | `""` | OpenAI-compatible LLM endpoint (optional) |
| `EIDOS_LLM_API_KEY` | `""` | LLM API key (optional) |

---

## Notes

- **Data is ephemeral**: Everything is lost when the server stops. This is by design for demos.
- **LLM features are optional**: Doc generation and reasoning work in deterministic mode without an LLM configured. Set `EIDOS_LLM_BASE_URL` and `EIDOS_LLM_API_KEY` for AI-enhanced output.
- **Ingestion clones repos**: The server needs internet access to clone Git repositories. Cloned repos are stored in a temp directory.
- **Multiple users**: Since auth is disabled, all requests run as an anonymous superadmin. There's no user isolation in demo mode.
