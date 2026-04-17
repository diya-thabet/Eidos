# Future Roadmap & Propositions

This document outlines planned improvements, feature ideas, and
architectural evolution for Eidos beyond Phase 8.

---

## Table of Contents

1. [Short-term (Next 2-4 weeks)](#1-short-term-next-2-4-weeks)
2. [Medium-term (1-3 months)](#2-medium-term-1-3-months)
3. [Long-term Vision (3-6 months)](#3-long-term-vision-3-6-months)
4. [Architecture Evolution](#4-architecture-evolution)
5. [Multi-language Support](#5-multi-language-support)
6. [Deployment Options](#6-deployment-options)
7. [Integration Ideas](#7-integration-ideas)

---

## 1. Short-term (Next 2-4 weeks)

### 1.1 Alembic Migrations

The ORM models have evolved across 8 phases, but no Alembic migration
scripts exist.  Before any production deployment:

- Run `alembic revision --autogenerate -m "initial"` to create the
  first migration capturing all tables (users, repos, repo_snapshots,
  files, symbols, edges, summaries, reviews, generated_docs, evaluations).
- Add a CI step that checks for un-generated migrations.

### 1.2 Redis-backed Token Blocklist

Currently, JWT logout is client-side only.  Adding a Redis set of
revoked JTIs would enable server-side invalidation:

```
POST /auth/logout  ?  add JWT's jti to Redis with TTL = remaining exp
GET  /auth/me      ?  check jti is not in blocklist before proceeding
```

### 1.3 Rate Limiting

Add `slowapi` or a custom middleware to prevent abuse:

```
- 60 requests/minute for authenticated users
- 10 requests/minute for anonymous users
- 5 ingestion triggers per hour per repo
```

### 1.4 Webhook-based Ingestion

Instead of manual `POST /repos/{id}/ingest`, add:

```
POST /webhooks/github    ? GitHub push events
POST /webhooks/gitlab    ? GitLab push events
POST /webhooks/azure     ? Azure DevOps service hooks
```

Auto-trigger ingestion on push to the default branch.

---

## 2. Medium-term (1-3 months)

### 2.1 Real LLM Integration

Replace stubs with production-ready LLM calls:

- **OpenAI GPT-4o-mini** for summaries, Q&A, review narratives
- **Local Ollama** for air-gapped deployments
- **Azure OpenAI** for enterprise customers
- Configurable via `EIDOS_LLM_BASE_URL` (already in config)

### 2.2 Production Vector Store (Qdrant)

The `InMemoryVectorStore` works for testing.  Wire in the
`QdrantVectorStore` with:

- Persistent collections per repo
- Snapshot-level filtering
- Horizontal scaling via Qdrant shards

### 2.3 Async Task Queue

Replace `BackgroundTasks` with a proper queue:

- **ARQ** (async Redis queue) or **Celery + Redis**
- Job status tracking, retries, dead-letter queue
- Dashboard (Flower for Celery, or custom)

### 2.4 RBAC & Team Sharing

Current model: single-owner repos.  Extend to:

```
users  ?  memberships  ?  teams  ?  team_repos  ?  repos
               ?
           role (owner | admin | viewer)
```

### 2.5 Frontend UI

Build a React/Next.js frontend:

- Repo dashboard (list, status, last indexed)
- Code graph visualization (D3.js / Cytoscape)
- Q&A chat interface
- Doc viewer with citation highlights
- PR review diff viewer with inline findings

---

## 3. Long-term Vision (3-6 months)

### 3.1 IDE Extensions

- **VS Code extension**: Ask questions, view docs, get review
  findings inline while coding.
- **JetBrains plugin**: Same for Rider users (C# primary audience).

### 3.2 CI/CD Integration

- GitHub Actions / Azure Pipelines step that:
  1. Triggers Eidos ingestion on every PR
  2. Posts review findings as PR comments
  3. Blocks merge if risk_score > threshold

### 3.3 Multi-tenant SaaS

- Organization-level billing
- Isolated data per org (row-level security or schema-per-tenant)
- SSO via SAML/OIDC
- Audit logging

### 3.4 Incremental Indexing

Current approach re-indexes everything on each ingestion.
Optimize with:

- File-hash diffing: only re-parse changed files
- Symbol-level diffing: only re-summarize changed symbols
- Vector store upsert-by-delta

### 3.5 Code Generation

Given deep understanding of the codebase, Eidos could:

- Generate unit test skeletons
- Suggest refactoring patterns
- Generate migration guides ("here's how to upgrade from .NET 6 to 8")

---

## 4. Architecture Evolution

### Current: Modular Monolith

```
????????????????????????????????????????????
?                FastAPI App               ?
?  ??????????????????????????????????????  ?
?  ? Repos  ?Analysis?Indexing? Reviews  ?  ?
?  ? Auth   ?Reason. ?DocGen ?Guardrails?  ?
?  ??????????????????????????????????????  ?
?           ? SQLAlchemy async ?           ?
?  ??????????????????????????????????????  ?
?  ?  PostgreSQL / MySQL / SQLite / ... ?  ?
?  ??????????????????????????????????????  ?
????????????????????????????????????????????
```

### Future: Microservices (if scale demands)

```
????????????  ????????????  ????????????
?  API GW  ?  ? Ingestion?  ? Analysis ?
? (FastAPI)?  ? Worker   ?  ? Worker   ?
????????????  ????????????  ????????????
     ?             ?             ?
     ?????????????????????????????
            ?             ?
     ??????????????? ????????????
     ? PostgreSQL  ? ?  Qdrant  ?
     ??????????????? ????????????
```

The current code is structured so that each package (analysis,
indexing, reviews, docgen, guardrails, auth) can be extracted
into its own service with minimal refactoring.

---

## 5. Multi-language Support

Currently only C# is parsed via tree-sitter.  Extension plan:

| Language | tree-sitter grammar | Priority |
|----------|-------------------|----------|
| Java | `tree-sitter-java` | **Done** |
| Python | `tree-sitter-python` | **Done** |
| TypeScript | `tree-sitter-typescript` | **Done** |
| Go | `tree-sitter-go` | Medium |
| Rust | `tree-sitter-rust` | Low |
| C/C++ | `tree-sitter-c` / `tree-sitter-cpp` | Low |

Each language needs:
1. A parser module (like `csharp_parser.py`)
2. Symbol/edge extraction rules
3. Entry point detection heuristics
4. Test fixtures

The `analysis.pipeline` already dispatches by `language` field,
so adding a new parser is additive.

---

## 6. Deployment Options

### 6.1 Docker Compose (current)

Best for local dev and small teams.  Already provided in `infra/`.

### 6.2 Kubernetes (current)

Manifests in `k8s/` for kind/minikube.  Production would need:

- Horizontal Pod Autoscaler for API pods
- Separate worker Deployment for ingestion
- PVC for clone storage (or S3 mount)
- Ingress with TLS

### 6.3 Serverless (future)

- API on AWS Lambda + API Gateway (via Mangum)
- Ingestion on ECS Fargate tasks (long-running)
- RDS for PostgreSQL, ElastiCache for Redis

### 6.4 Self-hosted Single Binary

- Package as a single Docker image with embedded SQLite
- `docker run -p 8000:8000 eidos:latest`
- Zero external dependencies

---

## 7. Integration Ideas

### 7.1 Slack / Teams Bot

```
/eidos explain OrderService.PlaceOrder
/eidos review <paste diff>
/eidos status my-project
```

### 7.2 Confluence / Notion Export

Auto-publish generated docs to Confluence or Notion pages,
with scheduled regeneration on each indexing.

### 7.3 Jira / Linear Ticket Enrichment

When creating a ticket that references code, Eidos could
auto-attach relevant symbols, dependencies, and risk assessment.

### 7.4 Grafana Dashboard

Expose Prometheus metrics:

- Symbols per snapshot
- Indexing duration
- Hallucination scores over time
- Review risk score trends

---

*This document is a living plan.  Priorities will shift based on
user feedback and deployment experience.*
