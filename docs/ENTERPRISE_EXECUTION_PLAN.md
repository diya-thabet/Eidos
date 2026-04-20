# Eidos -- Enterprise Execution Plan

> **Version**: 1.0
> **Date**: June 2025
> **Scope**: Complete roadmap from current state to production-grade enterprise SaaS
> **Timeline**: 12 months (4 quarters)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Snapshot](#2-current-state-snapshot)
3. [Quarter 1 -- Foundation Hardening (Weeks 1-12)](#3-quarter-1----foundation-hardening-weeks-1-12)
4. [Quarter 2 -- Multi-tenant SaaS (Weeks 13-24)](#4-quarter-2----multi-tenant-saas-weeks-13-24)
5. [Quarter 3 -- Intelligence & Integrations (Weeks 25-36)](#5-quarter-3----intelligence--integrations-weeks-25-36)
6. [Quarter 4 -- Scale & Enterprise (Weeks 37-48)](#6-quarter-4----scale--enterprise-weeks-37-48)
7. [Infrastructure Evolution](#7-infrastructure-evolution)
8. [Team Structure](#8-team-structure)
9. [Quality Gates](#9-quality-gates)
10. [Risk Register](#10-risk-register)
11. [Monetization Strategy](#11-monetization-strategy)
12. [Success Metrics (KPIs)](#12-success-metrics-kpis)
13. [Technology Decisions Log](#13-technology-decisions-log)
14. [Appendix: Dependency Map](#14-appendix-dependency-map)

---

## 1. Executive Summary

Eidos is a code intelligence platform that explains legacy codebases, generates documentation, reviews PRs, and measures code health. The system currently has a **working backend** with 9 language parsers, 40 health rules, RBAC, usage metering, and 1379 passing tests across 30,650 lines of code.

This plan transforms Eidos from a functional prototype into a **production-grade enterprise SaaS product** over 4 quarters, covering:

- **Q1**: Production hardening, real LLM integration, Alembic migrations, task queue, frontend MVP
- **Q2**: Multi-tenant SaaS, billing, SSO, team workspaces, public launch
- **Q3**: IDE extensions, CI/CD integrations, advanced analytics, AI improvements
- **Q4**: Enterprise features, SOC 2 compliance, on-premise option, scale

---

## 2. Current State Snapshot

| Area | Status | Detail |
|------|--------|--------|
| **Backend API** | 9 routers | repos, analysis, indexing, reasoning, reviews, docgen, evaluations, auth, admin |
| **Parsers** | 9 languages | C#, Java, Python, TypeScript/TSX, Go, Rust, C, C++ |
| **Code Health** | 40 rules | Clean code, SOLID, complexity, coupling, code smells, security, naming, architecture |
| **Auth** | RBAC | 5 roles (superadmin/admin/employee/support/user), GitHub + Google OAuth, JWT |
| **Metering** | Flexible | JSONB plans (time/token/scan/combo/unlimited), usage tracking |
| **Docker** | Multi-stage | Client + internal editions, compose profiles |
| **Tests** | 1379 passing | 60 test files, ruff + mypy + pytest CI |
| **Docs** | 17 files | Architecture, all phases, deployment, API guide |
| **Frontend** | None | Backend API only, no UI |
| **Database** | SQLAlchemy async | PostgreSQL primary, SQLite for tests |
| **LLM** | Stub + real | OpenAI-compatible client, stub for testing |
| **Vector store** | Client ready | Qdrant client exists, InMemory for tests |

### What's Missing for Enterprise

| Gap | Impact | Priority |
|-----|--------|----------|
| No frontend | Users can't use the product | Critical |
| No Alembic migrations | Can't upgrade DB safely | Critical |
| No async task queue | Ingestion blocks on BackgroundTasks | High |
| No billing/payments | Can't monetize | High |
| No SSO/SAML | Enterprise blockers | High |
| No incremental indexing | Re-scans everything every time | Medium |
| No IDE extensions | Developers can't use inline | Medium |
| No CI/CD webhooks | Manual trigger only | Medium |
| No audit logging | Compliance gap | Medium |
| No rate limiting middleware | Abuse risk | Medium |

---

## 3. Quarter 1 -- Foundation Hardening (Weeks 1-12)

### 3.1 Sprint 1-2: Database & Migrations (Weeks 1-4)

**Goal**: Production-safe database with versioned migrations.

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| Generate initial Alembic migration from all current models | Critical | 1d | Backend |
| Add CI check: fail if unmigrated model changes exist | Critical | 0.5d | DevOps |
| Add `created_at`/`updated_at` to all tables that lack it | High | 1d | Backend |
| Add soft-delete support (is_deleted + deleted_at columns) | High | 1d | Backend |
| Add database connection pooling configuration (PgBouncer) | Medium | 1d | DevOps |
| Write migration for RBAC tables (plans, subscriptions, usage) | Critical | 0.5d | Backend |
| Add DB backup/restore scripts for Docker | Medium | 0.5d | DevOps |

**Deliverables**:
- All tables under Alembic control
- CI gate enforcing migration coverage
- Backup/restore tested and documented

### 3.2 Sprint 3-4: Real LLM Integration (Weeks 5-8)

**Goal**: Replace stubs with production LLM calls; add fallback and caching.

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| Wire OpenAICompatibleClient into summarizer | Critical | 2d | Backend |
| Wire LLM into Q&A engine (reasoning) | Critical | 2d | Backend |
| Wire LLM into PR review narrative generation | Critical | 2d | Backend |
| Wire LLM into documentation generation | Critical | 2d | Backend |
| Add Redis-based LLM response cache (TTL configurable) | High | 1d | Backend |
| Add LLM fallback chain (primary -> secondary -> stub) | High | 1d | Backend |
| Add LLM token counting and cost tracking per user | High | 2d | Backend |
| Add streaming response support (SSE for long Q&A) | Medium | 2d | Backend |
| Add prompt templates as separate files (not hardcoded) | Medium | 1d | Backend |
| Benchmark: latency, tokens/request, cost per operation | Medium | 1d | Backend |

**Deliverables**:
- Every LLM-powered feature works with real models
- Cost tracking per user in usage_records
- Response caching reduces redundant LLM calls by >50%

### 3.3 Sprint 5-6: Task Queue & Async Processing (Weeks 9-12)

**Goal**: Replace BackgroundTasks with a proper async job queue.

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| Set up ARQ (async Redis queue) as job runner | Critical | 2d | Backend |
| Migrate repo ingestion to ARQ job | Critical | 1d | Backend |
| Migrate analysis pipeline to ARQ job | Critical | 1d | Backend |
| Migrate summarization pipeline to ARQ job | High | 1d | Backend |
| Add job status tracking (pending/running/done/failed) | High | 1d | Backend |
| Add job retry with exponential backoff | High | 0.5d | Backend |
| Add dead-letter queue for permanently failed jobs | Medium | 0.5d | Backend |
| Add worker health monitoring endpoint | Medium | 0.5d | Backend |
| Add Webhook: POST to user URL when job completes | Medium | 1d | Backend |
| Add `/jobs/{id}` status endpoint | High | 0.5d | Backend |

**Deliverables**:
- All heavy work runs in background workers
- Job status visible via API
- Failed jobs retried automatically
- Worker scaling independent of API pods

---

## 4. Quarter 2 -- Multi-tenant SaaS (Weeks 13-24)

### 4.1 Sprint 7-8: Billing & Subscription (Weeks 13-16)

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| Integrate Stripe for subscription management | Critical | 3d | Backend |
| Create pricing tiers: Free, Pro, Team, Enterprise | Critical | 1d | Product |
| Add webhook handlers for Stripe events (payment, cancel, upgrade) | Critical | 2d | Backend |
| Auto-provision plan on user signup (free tier default) | High | 1d | Backend |
| Add usage-based billing overage charges | Medium | 2d | Backend |
| Add invoice generation and history endpoint | Medium | 1d | Backend |
| Add plan comparison page data endpoint | Medium | 0.5d | Backend |
| Add coupon/promo code support | Low | 1d | Backend |

**Tier structure (adjustable via admin)**:

| Tier | Price | Repos | Scans/mo | Q&A/mo | Health checks | LLM model |
|------|-------|-------|----------|--------|---------------|-----------|
| Free | $0 | 3 | 10 | 50 | Unlimited | gpt-4o-mini |
| Pro | $29/mo | 20 | 100 | 500 | Unlimited | gpt-4o |
| Team | $99/mo | Unlimited | 500 | 2000 | Unlimited | gpt-4o |
| Enterprise | Custom | Unlimited | Unlimited | Unlimited | Unlimited | Custom |

### 4.2 Sprint 9-10: Team Workspaces & SSO (Weeks 17-20)

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| Create `organizations` table (name, billing, settings) | Critical | 1d | Backend |
| Create `memberships` table (user <-> org, role) | Critical | 1d | Backend |
| Add org-scoped repo access (repos belong to org, not user) | Critical | 2d | Backend |
| Add SAML 2.0 SSO support (enterprise requirement) | High | 3d | Backend |
| Add OIDC SSO support | High | 2d | Backend |
| Add invite system (email invite to join org) | High | 1d | Backend |
| Add org-level admin dashboard data endpoints | High | 2d | Backend |
| Add row-level security: users see only their org's data | Critical | 2d | Backend |
| Add API key management (per-org, not per-user) | Medium | 1d | Backend |
| Add org-level usage analytics aggregation | Medium | 1d | Backend |

### 4.3 Sprint 11-12: Security & Compliance (Weeks 21-24)

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| Add comprehensive audit log (who did what, when) | Critical | 2d | Backend |
| Add Redis-backed JWT blocklist (server-side logout) | High | 1d | Backend |
| Add rate limiting middleware (slowapi or custom) | High | 1d | Backend |
| Add IP allowlisting for enterprise orgs | Medium | 1d | Backend |
| Add data export endpoint (GDPR compliance) | High | 1d | Backend |
| Add account deletion with cascade (GDPR right to forget) | High | 1d | Backend |
| Add security headers middleware (CORS, CSP, HSTS) | High | 0.5d | Backend |
| Add dependency vulnerability scanning in CI (pip-audit) | Medium | 0.5d | DevOps |
| Begin SOC 2 Type I documentation | Medium | Ongoing | Compliance |
| Add encrypted-at-rest for sensitive fields | Medium | 1d | Backend |

---

## 5. Quarter 3 -- Intelligence & Integrations (Weeks 25-36)

### 5.1 Sprint 13-14: Incremental Indexing (Weeks 25-28)

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| File-hash diffing: only re-parse changed files | Critical | 3d | Backend |
| Symbol-level diffing: only re-summarize changed symbols | High | 2d | Backend |
| Vector store upsert-by-delta (not full rebuild) | High | 2d | Backend |
| Git blame integration: who changed what, when | Medium | 2d | Backend |
| Change frequency analysis (hotspot detection from history) | Medium | 2d | Backend |
| Temporal coupling detection (files that always change together) | Medium | 2d | Backend |

### 5.2 Sprint 15-16: CI/CD Integrations (Weeks 29-32)

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| GitHub webhook endpoint (push, PR events) | Critical | 2d | Backend |
| Auto-trigger ingestion on push to default branch | Critical | 1d | Backend |
| Auto-trigger PR review on PR open/update | Critical | 2d | Backend |
| Post review findings as GitHub PR comments | High | 2d | Backend |
| GitLab webhook endpoint | High | 2d | Backend |
| Azure DevOps webhook endpoint | Medium | 2d | Backend |
| Bitbucket webhook endpoint | Medium | 2d | Backend |
| GitHub App creation (marketplace-ready) | High | 3d | Backend |
| Merge gating: block merge if health score < threshold | Medium | 1d | Backend |
| GitHub Actions reusable workflow for Eidos | Medium | 1d | DevOps |

### 5.3 Sprint 17-18: IDE Extensions (Weeks 33-36)

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| VS Code extension: ask questions inline | High | 5d | Frontend |
| VS Code extension: view code health findings inline | High | 3d | Frontend |
| VS Code extension: view generated docs in hover | Medium | 2d | Frontend |
| JetBrains plugin: same features as VS Code | Medium | 5d | Frontend |
| CLI tool: `eidos scan`, `eidos health`, `eidos ask` | Medium | 3d | Backend |

---

## 6. Quarter 4 -- Scale & Enterprise (Weeks 37-48)

### 6.1 Sprint 19-20: Performance & Scale (Weeks 37-40)

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| Horizontal pod autoscaling for API pods | Critical | 1d | DevOps |
| Separate worker deployment (scale independently) | Critical | 1d | DevOps |
| Add connection pooling proxy (PgBouncer) | High | 1d | DevOps |
| Qdrant sharding for large repos (>100k symbols) | High | 2d | Backend |
| Add read replicas for analytics queries | Medium | 1d | DevOps |
| Benchmark: 100 concurrent users, 50 repos, 1M symbols | Medium | 2d | QA |
| Add CDN for frontend assets | Medium | 0.5d | DevOps |
| Add response compression middleware | Medium | 0.5d | Backend |
| Database query optimization (EXPLAIN ANALYZE audit) | Medium | 2d | Backend |
| Add APM monitoring (Datadog, New Relic, or OpenTelemetry) | High | 2d | DevOps |

### 6.2 Sprint 21-22: Enterprise Features (Weeks 41-44)

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| On-premise deployment option (Helm chart) | High | 5d | DevOps |
| Air-gapped mode (Ollama/vLLM only, no cloud LLM) | High | 2d | Backend |
| Custom rule authoring (user-defined health rules) | Medium | 3d | Backend |
| White-label option (custom branding, domain) | Medium | 2d | Frontend |
| Data residency options (EU, US, APAC regions) | Medium | 2d | DevOps |
| Admin dashboard: org management, usage, billing | High | 5d | Frontend |
| Export reports as PDF/HTML | Medium | 2d | Backend |
| Scheduled scans (cron-based auto-ingestion) | Medium | 1d | Backend |

### 6.3 Sprint 23-24: AI & Code Generation (Weeks 45-48)

| Task | Priority | Est. | Owner |
|------|----------|------|-------|
| Unit test skeleton generation from code analysis | High | 3d | Backend |
| Refactoring suggestions with code diffs | High | 3d | Backend |
| Migration guide generation (framework upgrade paths) | Medium | 3d | Backend |
| Architecture diagram generation (Mermaid/PlantUML) | Medium | 2d | Backend |
| Code complexity trend tracking over time | Medium | 2d | Backend |
| Technical debt scoring and prioritization | Medium | 2d | Backend |
| Natural language codebase search | Medium | 2d | Backend |

---

## 7. Infrastructure Evolution

### Phase 1 (Current): Docker Compose

```
Docker Compose
??? PostgreSQL
??? Redis
??? Qdrant
??? Eidos API (single container)
```

### Phase 2 (Q1): Separated Workers

```
Docker Compose / K8s
??? PostgreSQL
??? Redis (cache + queue)
??? Qdrant
??? Eidos API (N replicas)
??? Eidos Worker (M replicas)
??? Next.js Frontend
```

### Phase 3 (Q2): Production K8s

```
Kubernetes Cluster
??? Ingress (nginx / Traefik)
?   ??? api.eidos.dev ? API Service
?   ??? app.eidos.dev ? Frontend Service
??? API Deployment (HPA, 2-10 pods)
??? Worker Deployment (HPA, 1-5 pods)
??? PostgreSQL (managed: RDS / Cloud SQL)
??? Redis (managed: ElastiCache / Memorystore)
??? Qdrant (StatefulSet, 3 replicas)
??? Stripe webhooks ? API
??? GitHub webhooks ? API
??? Monitoring (Prometheus + Grafana)
```

### Phase 4 (Q4): Enterprise / Multi-region

```
Multi-region
??? Region US-East
?   ??? K8s cluster (API + Workers)
?   ??? PostgreSQL primary
?   ??? Qdrant primary
??? Region EU-West
?   ??? K8s cluster (API + Workers)
?   ??? PostgreSQL replica
?   ??? Qdrant replica
??? Global
?   ??? CloudFront CDN (frontend)
?   ??? Global Load Balancer
?   ??? Stripe (global)
```

---

## 8. Team Structure

### Minimum Viable Team (Q1)

| Role | Count | Responsibility |
|------|-------|----------------|
| Backend Engineer | 1-2 | API, LLM integration, task queue |
| Frontend Engineer | 1 | Next.js dashboard |
| DevOps | 0.5 | Docker, CI/CD, K8s |

### Growth Team (Q2-Q3)

| Role | Count | Responsibility |
|------|-------|----------------|
| Backend Engineer | 2-3 | API, billing, SSO, integrations |
| Frontend Engineer | 2 | Dashboard + IDE extensions |
| DevOps/SRE | 1 | Infrastructure, monitoring |
| Product Manager | 1 | Roadmap, user research |
| QA Engineer | 1 | Test automation, load testing |

### Enterprise Team (Q4)

| Role | Count | Responsibility |
|------|-------|----------------|
| Backend Engineer | 3-4 | Platform, AI, enterprise features |
| Frontend Engineer | 2-3 | Dashboard, IDE extensions, white-label |
| DevOps/SRE | 1-2 | Multi-region, compliance, on-prem |
| Product Manager | 1 | Roadmap, enterprise sales support |
| QA Engineer | 1-2 | E2E, performance, security testing |
| Solutions Engineer | 1 | Enterprise onboarding, custom integrations |

---

## 9. Quality Gates

Every feature must pass these gates before merge:

| Gate | Tool | Threshold |
|------|------|-----------|
| Lint | ruff | Zero errors |
| Type check | mypy (strict) | Zero errors |
| Unit tests | pytest | 100% pass, no regressions |
| Coverage | pytest-cov | >= 80% for new code |
| API contract | OpenAPI schema validation | No breaking changes |
| Performance | Benchmark suite | No P95 latency regression > 10% |
| Security | pip-audit + bandit | Zero high/critical CVEs |
| Docker build | Multi-stage build | Both targets build successfully |
| Migration | Alembic | Upgrade + downgrade tested |
| Docs | Updated | All new features documented |

### Release Process

```
Feature branch ? PR ? CI (all gates) ? Code review ? Merge to main
                                                          ?
                                                    Auto-deploy to staging
                                                          ?
                                                    Manual promote to production
                                                          ?
                                                    Tag release (vX.Y.Z)
```

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM costs exceed budget | High | High | Token budgets per plan, caching, smaller models for low-tier |
| Database migration breaks production | Medium | Critical | Alembic up/down tested, blue-green deployment |
| Single point of failure (monolith) | Medium | High | Worker separation, health checks, auto-restart |
| Security breach (data leak) | Low | Critical | Encryption at rest, audit logs, SOC 2, penetration testing |
| LLM provider outage | Medium | Medium | Fallback chain: primary -> secondary -> stub |
| Qdrant data loss | Low | High | Snapshot backups, replication |
| Team key-person dependency | Medium | High | Documentation, pair programming, code reviews |
| Feature scope creep | High | Medium | Quarterly planning, strict sprint goals |
| Enterprise deal delays | Medium | Medium | Self-serve SaaS first, enterprise as add-on |
| Compliance requirements change | Low | Medium | SOC 2 framework covers most requirements |

---

## 11. Monetization Strategy

### Revenue Model: Subscription + Usage

| Component | Model |
|-----------|-------|
| **Base subscription** | Monthly/annual per-seat pricing |
| **Usage overage** | Per-scan and per-LLM-token beyond plan limits |
| **Enterprise** | Custom pricing, annual contracts |
| **Marketplace** | GitHub/VS Code marketplace listing (free tier for discovery) |

### Growth Funnel

```
Free tier (3 repos, 10 scans)
        ? value demonstrated
Pro ($29/mo, 20 repos)
        ? team adoption
Team ($99/mo, unlimited)
        ? org-wide rollout
Enterprise (custom, SSO, on-prem)
```

### Revenue Targets

| Quarter | MRR Target | Users | Repos |
|---------|-----------|-------|-------|
| Q1 | $0 (pre-launch) | 50 beta | 200 |
| Q2 | $5K | 200 | 1,000 |
| Q3 | $25K | 1,000 | 5,000 |
| Q4 | $100K | 5,000 | 25,000 |

---

## 12. Success Metrics (KPIs)

### Product Metrics

| Metric | Target (Q2) | Target (Q4) |
|--------|-------------|-------------|
| Monthly active users | 200 | 5,000 |
| Repos analyzed | 1,000 | 25,000 |
| Daily scans | 100 | 5,000 |
| Q&A questions/day | 200 | 10,000 |
| Health checks/day | 50 | 2,000 |
| PR reviews/day | 20 | 1,000 |

### Engineering Metrics

| Metric | Target |
|--------|--------|
| Test count | > 2,000 by Q2, > 3,000 by Q4 |
| API P95 latency | < 200ms (non-LLM endpoints) |
| LLM P95 latency | < 10s |
| Uptime | 99.9% |
| Deploy frequency | Daily |
| Mean time to recovery | < 30 min |

### Business Metrics

| Metric | Target (Q4) |
|--------|-------------|
| MRR | $100K |
| Churn rate | < 5%/month |
| NPS | > 40 |
| Enterprise deals | 5+ |
| GitHub stars | 1,000+ |

---

## 13. Technology Decisions Log

| Decision | Choice | Rationale | Date |
|----------|--------|-----------|------|
| Backend framework | FastAPI | Async, type-safe, OpenAPI auto-gen | Phase 0 |
| Database | PostgreSQL | Mature, JSONB support, extensions | Phase 0 |
| ORM | SQLAlchemy async | Best Python async ORM, migration support | Phase 0 |
| Parsers | tree-sitter | Universal, fast, all languages | Phase 2 |
| Vector store | Qdrant | Purpose-built, filtering, horizontal scaling | Phase 3 |
| LLM client | OpenAI-compatible | Works with all providers | Phase 4 |
| Frontend | Next.js 14+ | React ecosystem, SSR, App Router | Q1 |
| Task queue | ARQ (async Redis) | Native async, lightweight, Redis-backed | Q1 |
| Billing | Stripe | Industry standard, webhooks, subscriptions | Q2 |
| SSO | SAML 2.0 + OIDC | Enterprise requirement | Q2 |
| Monitoring | OpenTelemetry + Grafana | Vendor-neutral, comprehensive | Q2 |
| IDE extension | VS Code Extension API | Largest market share | Q3 |
| On-premise | Helm chart | Kubernetes standard for enterprise | Q4 |

---

## 14. Appendix: Dependency Map

```
Q1 Foundation
??? Alembic Migrations ? (no dependencies)
??? Real LLM Integration ? (no dependencies)
??? Task Queue ? Redis
??? Frontend MVP ? (see FRONTEND_DEV_PLAN.md)
?
Q2 Multi-tenant
??? Billing ? Stripe API
??? Team Workspaces ? Alembic Migrations
??? SSO ? Organizations model
??? Security/Compliance ? Audit logging
?
Q3 Intelligence
??? Incremental Indexing ? Task Queue
??? CI/CD Integrations ? Webhook endpoints
??? IDE Extensions ? Frontend auth, API client
?
Q4 Enterprise
??? On-premise ? Helm charts, air-gapped LLM
??? Custom Rules ? Code health engine
??? Multi-region ? Kubernetes, managed DB
??? AI Generation ? Real LLM + vector store
```
