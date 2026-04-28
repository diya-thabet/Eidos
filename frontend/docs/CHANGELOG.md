# Frontend Changelog

All notable changes to the Eidos frontend.

---

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
