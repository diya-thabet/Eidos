# Frontend Changelog

All notable changes to the Eidos frontend.

---

## Backend API: 98 endpoints (Phase 31)

**New endpoints (Bulk Operations):**
- `POST /repos/{id}/snapshots/bulk-delete` — delete multiple snapshots
- `POST /repos/{id}/snapshots/bulk-tag` — tag multiple snapshots
- `DELETE /repos/{id}/snapshots/older-than/{days}` — cleanup old snapshots
- `POST /repos/bulk-delete` — delete multiple repos (admin)

**Suggested UI:**
- Multi-select checkboxes on snapshot list
- "Delete Selected" + "Tag Selected" buttons in toolbar
- "Cleanup" modal with days slider for older-than deletion
- Confirmation dialogs for destructive actions

## Backend API: 94 endpoints (Phase 30)

**New endpoints (Snapshot Tags):**
- `POST /repos/{id}/snapshots/{sid}/tags` — add tag
- `DELETE /repos/{id}/snapshots/{sid}/tags/{tag}` — remove tag
- `GET /repos/{id}/snapshots/{sid}/tags` — list snapshot tags
- `GET /repos/{id}/snapshots/by-tag/{tag}` — find snapshots by tag
- `GET /repos/tags/stats` — tag usage stats

**Suggested UI:**
- Tag chips on snapshot cards (colored badges)
- Tag input with autocomplete (from /tags/stats)
- Filter snapshots by tag in the snapshot list
- Tag management modal on snapshot detail page

## Backend API: 89 endpoints (Phase 29)

**New endpoint (Call Cycle Detection):**
- `GET /repos/{id}/snapshots/{sid}/call-cycles` — detect function-level cycles

**Suggested UI:**
- Add **Call Cycles** section on the Graph/Architecture tab
- Cycle list with expandable members, highlight files involved
- Cycle path visualized as a circular arrow diagram
- Direct recursion listed separately (badge count)
- Filter by min cycle size

## Backend API: 88 endpoints (Phase 28)

**Updated endpoints (API Key Scopes):**
- `POST /auth/api-keys` — now accepts `scopes` (comma-separated) and `expires_in_days` params
- `GET /auth/api-keys` — now returns scopes[], expires_at, last_used_at, usage_count
- `GET /auth/api-keys/scopes` — **NEW** returns scope catalog for dynamic form

**Suggested UI:**
- Update API key creation form: multi-select for scopes (from /scopes endpoint), optional expiration date picker
- API key list table: add columns for scopes (badge chips), expires_at, last_used, usage count
- Scope chips with tooltips showing description

## Backend API: 87 endpoints (Phase 27)

**New endpoints to integrate (Audit Log):**
- `GET /admin/audit-log` — paginated query with filters (user_id, action, resource_type, success, method)
- `GET /admin/audit-log/export` — CSV download
- `GET /admin/audit-log/stats` — total events, unique users, top actions, failures
- `DELETE /admin/audit-log/purge?older_than_days=90` — retention management

**Suggested UI:**
- Add **Audit Log** page under admin section
- Filterable table with columns: timestamp, user, action, resource, method, status (success/fail badge)
- CSV export button
- Stats cards at top (total events, unique users, recent failures)
- Purge form with days input + confirmation dialog

## Backend API: 83 endpoints (Phase 26)

**New endpoints to integrate (Quality Gates):**
- `POST /repos/{id}/quality-gates` — create with configurable thresholds
- `GET /repos/{id}/quality-gates` — list (filter by active_only)
- `GET /repos/{id}/quality-gates/{gid}` — gate detail
- `PATCH /repos/{id}/quality-gates/{gid}` — update
- `DELETE /repos/{id}/quality-gates/{gid}` — delete
- `POST /repos/{id}/snapshots/{sid}/evaluate-gate/{gid}` — evaluate
- `GET /repos/quality-gates/schema` — dynamic config form builder

**Suggested UI:**
- Add a **Quality Gates** page under repo settings
- Dynamic form from `/quality-gates/schema` for config (renders input per available check)
- Big pass/fail badge on evaluation result
- Per-check breakdown table with green/red indicators
- "Run Gate" button on snapshot detail page

## Backend API: 76 endpoints (Phase 25)

**New endpoints to integrate:**
- `POST /repos/{id}/snapshots/{sid}/coverage` — upload pytest-cov JSON
- `GET /repos/{id}/snapshots/{sid}/coverage` — file-level coverage report
- `DELETE /repos/{id}/snapshots/{sid}/coverage` — delete report
- `GET /repos/{id}/coverage/history` — trend across snapshots

**Suggested UI:**
- Add a **Coverage** tab on the snapshot detail page
- Drag-and-drop upload zone for `coverage.json`
- File-level table sorted by lowest coverage first (already pre-sorted by API)
- Per-file expandable row showing missing line numbers
- Grade badge: A (?0.9), B (?0.8), C (?0.7), D (?0.6), F (<0.6)
- Coverage history chart on the repo overview page (line chart over time)

## [0.2.0] - 2025-06-XX - Initial Scaffold

### Added

- **Project setup**: Next.js 14 with App Router, TypeScript strict mode, Tailwind CSS + shadcn/ui design system
- **Design system**: Light/dark mode with CSS custom properties, Inter + JetBrains Mono fonts, health-specific colors (critical/error/warning/info/good)
- **Root layout**: Font loading, theme provider, React Query provider, Sonner toast notifications
- **Global pages**: Loading spinner, error boundary with retry, 404 page

- **Authentication**:
  - Login page with GitHub + Google OAuth buttons
  - Auth middleware protecting dashboard routes
  - Session token cookie check

- **Dashboard layout**:
  - Collapsible sidebar with main nav (Dashboard, Repos) + admin nav (System, Users, Plans, Usage)
  - Top bar with search input, notifications bell, dark mode toggle, user avatar
  - Responsive layout with sidebar state persisted in localStorage

- **Repository management**:
  - Repo list page with empty state + "Add Repository" CTA
  - Add repo form (name, URL, branch, provider selection)
  - Repo detail page with stats cards (branch, last scan, files) + scan history

- **Snapshot analysis**:
  - Snapshot layout with 7-tab navigation (Overview, Symbols, Graph, Health, Q&A, Review, Docs)
  - Overview page with stats cards (symbols, edges, modules, entry points) + kind breakdown
  - Symbol browser with search, kind filter, table with empty state
  - Graph visualization page with React Flow placeholder
  - **Code health page**: Full configuration panel (category toggles, threshold sliders, LLM toggle), score gauge, category scores grid, findings table with severity filtering
  - **Q&A chat**: Message bubbles (user/assistant), typing indicator, suggested questions, evidence citations, confidence badges
  - PR review page with diff paste textarea, clipboard paste button
  - Generated docs page with generate CTA

- **Admin pages**:
  - System dashboard with stats cards + system info (edition, version, auth, languages)
  - User management table skeleton
  - Plan management with 4-tier card grid
  - Usage analytics with chart placeholders

- **Settings**:
  - Profile settings (name, email, save, delete account)
  - Billing page with current plan display + upgrade CTA

- **Marketing**:
  - Landing page with hero, feature grid (6 features), navbar, footer
  - Marketing layout wrapper

- **API client** (`lib/api-client.ts`):
  - Typed fetch wrapper with auth header injection, error handling
  - Full endpoint coverage for all 55 backend endpoints:
    - Repos: create, status, detail, update, delete, ingest
    - Analysis: symbols (paginated), symbol detail, edges, callgraph, overview
    - Health: POST health check (with config), GET rules list
    - Search: keyword search, fulltext search (PG tsvector + ILIKE fallback)
    - Q&A: POST ask
    - Reviews: POST review, GET review history
    - Docs: POST generate, GET list, GET single doc
    - Evaluations: POST evaluate, GET evaluation history
    - Diagrams: GET diagram (class/module type param)
    - Trends: GET health trend across snapshots
    - Portable: GET .eidos export, POST .eidos import
    - Indexing: POST index, GET summaries
    - Export: GET JSON export, GET snapshot diff
    - Auth: login, callback (GitHub + Google), me, logout, API keys CRUD
    - Admin: users list/detail/role, plans list/create, usage stats
    - Monitoring: GET /health, GET /health/ready, GET /metrics
    - Webhooks: POST github/gitlab/push (server-to-server, not frontend)
  - All TypeScript interfaces matching backend Pydantic schemas

- **React Query hooks**:
  - `use-repos.ts`: list, get, status, detail, create, update, delete, ingest
  - `use-analysis.ts`: symbols (paginated), symbol detail, edges, overview, callgraph
  - `use-health.ts`: rules list, health check mutation, health trend
  - `use-search.ts`: keyword search, fulltext search
  - `use-chat.ts`: stateful chat with send/clear, error handling
  - `use-reviews.ts`: submit review, list reviews
  - `use-docs.ts`: generate docs, list docs, get doc
  - `use-evaluations.ts`: run evaluation, list evaluations
  - `use-diagrams.ts`: class diagram, module diagram
  - `use-portable.ts`: export .eidos, import .eidos
  - `use-export.ts`: JSON export, snapshot diff
  - `use-admin.ts`: system, users, plans, usage
  - `use-api-keys.ts`: create, list, revoke API keys
  - `use-debounce.ts`: generic debounce hook

- **Stores** (Zustand):
  - Sidebar collapse state (persisted)
  - Filter state (symbol kind, file path, search query)

- **UI components** (shadcn/ui pattern):
  - Button (6 variants, 4 sizes, asChild support)
  - Input
  - Card (Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter)
  - Badge (6 variants including success/warning)
  - Skeleton (shimmer animation)

- **Configuration**:
  - `tailwind.config.ts` with full design token system, health colors, animations
  - `globals.css` with light + dark mode CSS custom properties
  - `next.config.ts` with standalone output, image domains, API rewrite proxy
  - `tsconfig.json` with strict mode, path aliases
  - `.env.example` with all required environment variables
  - ESLint + Prettier config
  - Dockerfile (multi-stage: deps ? build ? standalone runner)
  - Auth middleware

### File count: 55+ files
### Lines of code: ~3,500+
### Backend endpoints covered: 55/55
