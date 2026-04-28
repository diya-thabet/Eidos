# Frontend Architecture

> See also: [API_RESPONSE_REFERENCE.md](API_RESPONSE_REFERENCE.md) for every JSON shape, TypeScript interfaces, and copy-paste-ready types.

## Backend API — 55 Endpoints

The frontend consumes the Eidos backend REST API. Below is the complete endpoint map grouped by feature.

### Health & Monitoring

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| GET | `/health` | Connection check on app load |
| GET | `/health/ready` | Readiness indicator in admin dashboard |
| GET | `/metrics` | Prometheus metrics (admin monitoring page) |

### Authentication

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| GET | `/auth/login` | Redirect to GitHub OAuth |
| GET | `/auth/callback` | Handle OAuth callback, store JWT |
| GET | `/auth/google/login` | Redirect to Google OAuth |
| GET | `/auth/google/callback` | Handle Google callback, store JWT |
| GET | `/auth/me` | Fetch current user profile |
| POST | `/auth/logout` | Clear session |
| POST | `/auth/api-keys?name=...` | Create API key (settings page) |
| GET | `/auth/api-keys` | List API keys (settings page) |
| DELETE | `/auth/api-keys/{key_id}` | Revoke API key (settings page) |

### Repository Management

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| POST | `/repos` | Add repository form |
| GET | `/repos/{id}/status` | Repo detail page, polling for ingestion |
| GET | `/repos/{id}/detail` | Repo detail with snapshot history |
| PATCH | `/repos/{id}` | Edit repo settings |
| DELETE | `/repos/{id}` | Delete repo confirmation dialog |
| POST | `/repos/{id}/ingest` | Trigger scan button |

### Code Analysis

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| GET | `/repos/{id}/snapshots/{sid}/symbols` | Symbol browser table (paginated) |
| GET | `/repos/{id}/snapshots/{sid}/symbols/{fq}` | Symbol detail panel |
| GET | `/repos/{id}/snapshots/{sid}/edges` | Graph visualization data |
| GET | `/repos/{id}/snapshots/{sid}/callgraph/{fq}` | Call graph neighborhood view |
| GET | `/repos/{id}/snapshots/{sid}/overview` | Overview stats cards |
| POST | `/repos/{id}/snapshots/{sid}/health` | Code health page (score + findings) |
| GET | `/repos/{id}/snapshots/{sid}/health/rules` | Health config panel (rule list) |

### Search

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| GET | `/repos/{id}/snapshots/{sid}/search?q=...` | Global search bar |
| GET | `/repos/{id}/snapshots/{sid}/fulltext?q=...` | Advanced full-text search page |
| GET | `/repos/{id}/snapshots/{sid}/diff/{other}` | Snapshot comparison view |
| GET | `/repos/{id}/snapshots/{sid}/export` | Download JSON export button |

### Q&A

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| POST | `/repos/{id}/snapshots/{sid}/ask` | Chat interface send message |

### Code Reviews

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| POST | `/repos/{id}/snapshots/{sid}/review` | PR review page (paste diff) |
| GET | `/repos/{id}/snapshots/{sid}/reviews` | Review history list |

### Documentation

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| POST | `/repos/{id}/snapshots/{sid}/docs` | Generate docs button |
| GET | `/repos/{id}/snapshots/{sid}/docs` | Docs list page |
| GET | `/repos/{id}/snapshots/{sid}/docs/{doc_id}` | Single doc viewer |

### Evaluations

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| POST | `/repos/{id}/snapshots/{sid}/evaluate` | Run quality check button |
| GET | `/repos/{id}/snapshots/{sid}/evaluations` | Evaluation history |

### Diagrams

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| GET | `/repos/{id}/snapshots/{sid}/diagram?type=class` | Class diagram tab |
| GET | `/repos/{id}/snapshots/{sid}/diagram?type=module` | Module diagram tab |

### Trends

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| GET | `/repos/{id}/health/trend` | Health trend chart |

### Portable Export/Import

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| GET | `/repos/{id}/snapshots/{sid}/portable` | Download .eidos file button |
| POST | `/repos/{id}/import` | Upload .eidos file dialog |

### Indexing

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| POST | `/repos/{id}/snapshots/{sid}/index` | Trigger indexing button |
| GET | `/repos/{id}/snapshots/{sid}/summaries` | Summary browser |

### Webhooks

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| POST | `/webhooks/github` | Not consumed by frontend (server-to-server) |
| POST | `/webhooks/gitlab` | Not consumed by frontend (server-to-server) |
| POST | `/webhooks/push` | Not consumed by frontend (server-to-server) |

### Admin

| Method | Endpoint | Frontend Usage |
|--------|----------|---------------|
| GET | `/admin/users` | User management table |
| GET | `/admin/users/{uid}` | User detail panel |
| PATCH | `/admin/users/{uid}/role` | Role change dropdown |
| GET | `/admin/plans` | Plan management cards |
| POST | `/admin/plans` | Create plan form |
| GET | `/admin/usage` | Usage analytics dashboard |

---

## Rendering Strategy

| Route Group | Rendering | Reason |
|-------------|-----------|--------|
| `(marketing)` | Server (SSR) | SEO for landing, pricing pages |
| `(auth)` | Server | Minimal JS, fast load |
| `(dashboard)` | Client-heavy | Interactive dashboards, real-time updates |

## Data Flow

```
Server Component (initial data) -> React Query (mutations, polling) -> Zustand (UI state)
```

## Key Patterns

1. **Server Components by default** — data fetching at the component level
2. **"use client" only when needed** — interactivity, hooks, browser APIs
3. **React Query for server state** — caching, invalidation, optimistic updates
4. **Zustand for client state** — sidebar, theme, filters (minimal)
5. **Typed API client** — single source of truth matching backend schemas
6. **shadcn/ui components** — accessible, customizable, consistent

## Route Map

| Path | Purpose | Backend Endpoints Used |
|------|---------|----------------------|
| `/` | Landing page (marketing) | none |
| `/login` | OAuth login | `/auth/login`, `/auth/google/login` |
| `/repos` | Repository list | `/repos/{id}/status` (per repo) |
| `/repos/new` | Add repository | `POST /repos` |
| `/repos/[id]` | Repository detail | `/repos/{id}/detail`, `/repos/{id}/status` |
| `/repos/[id]/snapshots/[sid]` | Snapshot overview | `/overview` |
| `/repos/[id]/snapshots/[sid]/symbols` | Symbol browser | `/symbols`, `/symbols/{fq}` |
| `/repos/[id]/snapshots/[sid]/graph` | Code graph | `/edges`, `/callgraph/{fq}` |
| `/repos/[id]/snapshots/[sid]/health` | Code health | `POST /health`, `/health/rules` |
| `/repos/[id]/snapshots/[sid]/search` | Search | `/search`, `/fulltext` |
| `/repos/[id]/snapshots/[sid]/ask` | Q&A chat | `POST /ask` |
| `/repos/[id]/snapshots/[sid]/review` | PR review | `POST /review`, `/reviews` |
| `/repos/[id]/snapshots/[sid]/docs` | Generated docs | `POST /docs`, `GET /docs`, `/docs/{id}` |
| `/repos/[id]/snapshots/[sid]/eval` | Evaluations | `POST /evaluate`, `/evaluations` |
| `/repos/[id]/snapshots/[sid]/diagrams` | Diagrams | `/diagram?type=class`, `?type=module` |
| `/repos/[id]/snapshots/[sid]/diff/[other]` | Snapshot diff | `/diff/{other}` |
| `/repos/[id]/health/trend` | Health trend | `/health/trend` |
| `/repos/[id]/export` | Export/import | `/export`, `/portable`, `POST /import` |
| `/admin` | System admin | `/admin/usage` |
| `/admin/users` | User management | `/admin/users`, `/admin/users/{id}/role` |
| `/admin/plans` | Plan management | `/admin/plans`, `POST /admin/plans` |
| `/admin/usage` | Usage analytics | `/admin/usage` |
| `/settings` | User profile | `/auth/me` |
| `/settings/api-keys` | API key management | `/auth/api-keys` |
| `/settings/billing` | Billing management | (Stripe integration, future) |
