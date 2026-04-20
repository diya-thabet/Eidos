# Eidos Frontend Development Plan -- Next.js

> **Framework**: Next.js 14+ (App Router)
> **Language**: TypeScript (strict mode)
> **Timeline**: Parallel with backend quarters, MVP in Q1

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Phase 1: MVP Dashboard (Weeks 1-6)](#4-phase-1-mvp-dashboard-weeks-1-6)
5. [Phase 2: Core Features (Weeks 7-12)](#5-phase-2-core-features-weeks-7-12)
6. [Phase 3: Advanced UI (Weeks 13-20)](#6-phase-3-advanced-ui-weeks-13-20)
7. [Phase 4: Enterprise UI (Weeks 21-28)](#7-phase-4-enterprise-ui-weeks-21-28)
8. [Phase 5: IDE & Embeddable (Weeks 29-36)](#8-phase-5-ide--embeddable-weeks-29-36)
9. [Page-by-Page Specification](#9-page-by-page-specification)
10. [Component Library](#10-component-library)
11. [State Management](#11-state-management)
12. [API Client Layer](#12-api-client-layer)
13. [Authentication Flow](#13-authentication-flow)
14. [Real-time Features](#14-real-time-features)
15. [Testing Strategy](#15-testing-strategy)
16. [Performance Budget](#16-performance-budget)
17. [Accessibility Requirements](#17-accessibility-requirements)
18. [Design System](#18-design-system)
19. [Deployment](#19-deployment)
20. [Development Workflow](#20-development-workflow)

---

## 1. Architecture Overview

```
Browser
  ??? Next.js App (SSR + Client)
  ?   ??? App Router (file-based routing)
  ?   ??? Server Components (data fetching)
  ?   ??? Client Components (interactivity)
  ?   ??? Server Actions (mutations)
  ?   ??? Middleware (auth, redirects)
  ?
  ??? API calls ? Eidos Backend (FastAPI)
  ?   ??? REST API (repos, analysis, health, admin)
  ?   ??? SSE (streaming Q&A responses)
  ?   ??? WebSocket (job status updates)
  ?
  ??? External
      ??? GitHub OAuth (login)
      ??? Google OAuth (login)
      ??? Stripe (billing portal)
```

### Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Rendering | Server Components by default | Faster initial load, SEO for marketing pages |
| Data fetching | Server Components + React Query | Server for initial load, React Query for mutations/polling |
| Styling | Tailwind CSS + shadcn/ui | Fast development, consistent design, accessible |
| Charts | Recharts | Lightweight, React-native, good for dashboards |
| Graph visualization | React Flow | Best for code graph / dependency visualization |
| Code display | Monaco Editor (read-only) | Same as VS Code, syntax highlighting |
| State management | Zustand (minimal) | Simple, no boilerplate, works with Server Components |
| Forms | React Hook Form + Zod | Type-safe validation, matches backend Pydantic schemas |
| Auth | NextAuth.js v5 | Built-in OAuth, session management, middleware |

---

## 2. Tech Stack

### Core

| Package | Version | Purpose |
|---------|---------|---------|
| `next` | 14.2+ | Framework |
| `react` | 18.3+ | UI library |
| `typescript` | 5.4+ | Type safety |
| `tailwindcss` | 3.4+ | Utility CSS |

### UI Components

| Package | Purpose |
|---------|---------|
| `@shadcn/ui` | Pre-built accessible components (dialog, dropdown, table, etc.) |
| `@radix-ui/*` | Primitives behind shadcn/ui |
| `lucide-react` | Icon set |
| `recharts` | Charts and graphs |
| `@xyflow/react` | Code graph visualization |
| `@monaco-editor/react` | Code display with syntax highlighting |
| `react-markdown` | Render generated docs / Q&A responses |
| `sonner` | Toast notifications |

### Data & State

| Package | Purpose |
|---------|---------|
| `@tanstack/react-query` | Server state, caching, mutations |
| `zustand` | Client state (theme, sidebar, filters) |
| `next-auth` | OAuth authentication |
| `zod` | Schema validation |
| `react-hook-form` | Form handling |
| `@hookform/resolvers` | Zod integration with react-hook-form |

### Dev Tooling

| Package | Purpose |
|---------|---------|
| `eslint` + `prettier` | Lint + format |
| `vitest` | Unit tests |
| `@testing-library/react` | Component tests |
| `playwright` | E2E tests |
| `@storybook/react` | Component development |
| `msw` | API mocking |

---

## 3. Project Structure

```
frontend/
??? public/
?   ??? logo.svg
?   ??? favicon.ico
?   ??? og-image.png
?
??? src/
?   ??? app/                          # Next.js App Router
?   ?   ??? (auth)/                   # Auth group (no layout chrome)
?   ?   ?   ??? login/page.tsx
?   ?   ?   ??? signup/page.tsx
?   ?   ?   ??? callback/page.tsx
?   ?   ?
?   ?   ??? (marketing)/              # Public pages (SSR, SEO)
?   ?   ?   ??? page.tsx              # Landing page
?   ?   ?   ??? pricing/page.tsx
?   ?   ?   ??? docs/page.tsx
?   ?   ?   ??? layout.tsx            # Marketing layout (navbar + footer)
?   ?   ?
?   ?   ??? (dashboard)/              # Authenticated area
?   ?   ?   ??? layout.tsx            # Dashboard layout (sidebar + topbar)
?   ?   ?   ??? page.tsx              # Dashboard home (repo list)
?   ?   ?   ?
?   ?   ?   ??? repos/
?   ?   ?   ?   ??? page.tsx          # All repos list
?   ?   ?   ?   ??? new/page.tsx      # Add repo form
?   ?   ?   ?   ??? [repoId]/
?   ?   ?   ?       ??? page.tsx      # Repo overview (snapshots, status)
?   ?   ?   ?       ??? snapshots/[snapId]/
?   ?   ?   ?       ?   ??? page.tsx          # Snapshot detail
?   ?   ?   ?       ?   ??? symbols/page.tsx  # Symbol browser
?   ?   ?   ?       ?   ??? graph/page.tsx    # Code graph visualization
?   ?   ?   ?       ?   ??? health/page.tsx   # Code health report
?   ?   ?   ?       ?   ??? ask/page.tsx      # Q&A chat interface
?   ?   ?   ?       ?   ??? review/page.tsx   # PR review
?   ?   ?   ?       ?   ??? docs/page.tsx     # Generated docs
?   ?   ?   ?       ?   ??? layout.tsx        # Snapshot sub-navigation
?   ?   ?   ?       ??? settings/page.tsx     # Repo settings
?   ?   ?   ?
?   ?   ?   ??? admin/                # Admin area (role-gated)
?   ?   ?   ?   ??? page.tsx          # System overview
?   ?   ?   ?   ??? users/page.tsx    # User management
?   ?   ?   ?   ??? plans/page.tsx    # Plan management
?   ?   ?   ?   ??? usage/page.tsx    # Usage analytics
?   ?   ?   ?
?   ?   ?   ??? settings/
?   ?   ?   ?   ??? page.tsx          # User profile
?   ?   ?   ?   ??? billing/page.tsx  # Subscription management
?   ?   ?   ?   ??? tokens/page.tsx   # API key management
?   ?   ?   ?
?   ?   ?   ??? team/                 # Team management (Q2)
?   ?   ?       ??? page.tsx          # Team members
?   ?   ?       ??? invite/page.tsx   # Invite members
?   ?   ?
?   ?   ??? api/                      # Next.js API routes (minimal)
?   ?   ?   ??? auth/[...nextauth]/route.ts
?   ?   ?
?   ?   ??? layout.tsx                # Root layout
?   ?   ??? loading.tsx               # Global loading
?   ?   ??? error.tsx                 # Global error boundary
?   ?   ??? not-found.tsx             # 404 page
?   ?
?   ??? components/
?   ?   ??? ui/                       # shadcn/ui components
?   ?   ?   ??? button.tsx
?   ?   ?   ??? input.tsx
?   ?   ?   ??? dialog.tsx
?   ?   ?   ??? table.tsx
?   ?   ?   ??? badge.tsx
?   ?   ?   ??? card.tsx
?   ?   ?   ??? tabs.tsx
?   ?   ?   ??? dropdown-menu.tsx
?   ?   ?   ??? command.tsx           # Command palette (Cmd+K)
?   ?   ?   ??? sheet.tsx             # Mobile sidebar
?   ?   ?   ??? ... (20+ components)
?   ?   ?
?   ?   ??? layout/
?   ?   ?   ??? sidebar.tsx           # Dashboard sidebar navigation
?   ?   ?   ??? topbar.tsx            # Top navigation bar
?   ?   ?   ??? breadcrumb.tsx        # Dynamic breadcrumbs
?   ?   ?   ??? command-palette.tsx   # Global search (Cmd+K)
?   ?   ?   ??? mobile-nav.tsx        # Responsive navigation
?   ?   ?
?   ?   ??? repos/
?   ?   ?   ??? repo-card.tsx         # Repo list card
?   ?   ?   ??? repo-form.tsx         # Create/edit repo form
?   ?   ?   ??? snapshot-timeline.tsx # Snapshot history timeline
?   ?   ?   ??? ingest-button.tsx     # Trigger ingestion with status
?   ?   ?
?   ?   ??? analysis/
?   ?   ?   ??? symbol-table.tsx      # Filterable symbol table
?   ?   ?   ??? symbol-detail.tsx     # Symbol detail panel
?   ?   ?   ??? code-graph.tsx        # React Flow graph visualization
?   ?   ?   ??? code-viewer.tsx       # Monaco editor (read-only)
?   ?   ?   ??? overview-cards.tsx    # Analysis stats cards
?   ?   ?
?   ?   ??? health/
?   ?   ?   ??? health-dashboard.tsx  # Score gauge + category breakdown
?   ?   ?   ??? findings-table.tsx    # Sortable findings list
?   ?   ?   ??? rule-config.tsx       # Rule toggle + threshold config
?   ?   ?   ??? category-chart.tsx    # Radar chart per category
?   ?   ?   ??? trend-chart.tsx       # Health score over time
?   ?   ?
?   ?   ??? chat/
?   ?   ?   ??? chat-interface.tsx    # Q&A chat with streaming
?   ?   ?   ??? chat-message.tsx      # Single message (user/assistant)
?   ?   ?   ??? citation-link.tsx     # Click-to-navigate code citation
?   ?   ?   ??? suggested-questions.tsx # Quick-ask buttons
?   ?   ?
?   ?   ??? reviews/
?   ?   ?   ??? review-form.tsx       # Paste diff + trigger review
?   ?   ?   ??? review-result.tsx     # Review findings with severity
?   ?   ?   ??? diff-viewer.tsx       # Side-by-side diff with annotations
?   ?   ?   ??? review-history.tsx    # Past reviews list
?   ?   ?
?   ?   ??? docs/
?   ?   ?   ??? doc-viewer.tsx        # Markdown rendered doc
?   ?   ?   ??? doc-generator.tsx     # Doc generation form
?   ?   ?   ??? doc-list.tsx          # List of generated docs
?   ?   ?
?   ?   ??? admin/
?   ?       ??? user-table.tsx        # User management table
?   ?       ??? plan-editor.tsx       # JSON plan limits editor
?   ?       ??? usage-charts.tsx      # Usage analytics charts
?   ?       ??? system-info.tsx       # System status panel
?   ?
?   ??? lib/
?   ?   ??? api-client.ts            # Typed API client (generated from OpenAPI)
?   ?   ??? auth.ts                   # NextAuth configuration
?   ?   ??? utils.ts                  # Utility functions (cn, formatDate, etc.)
?   ?   ??? constants.ts              # App-wide constants
?   ?
?   ??? hooks/
?   ?   ??? use-repos.ts             # React Query hooks for repos
?   ?   ??? use-analysis.ts          # React Query hooks for analysis
?   ?   ??? use-health.ts            # React Query hooks for health
?   ?   ??? use-chat.ts              # Streaming Q&A hook
?   ?   ??? use-admin.ts             # Admin API hooks
?   ?   ??? use-debounce.ts          # Debounce utility hook
?   ?
?   ??? stores/
?   ?   ??? theme-store.ts           # Dark/light mode
?   ?   ??? sidebar-store.ts         # Sidebar collapse state
?   ?   ??? filter-store.ts          # Global filter state (kind, language)
?   ?
?   ??? types/
?       ??? api.ts                    # TypeScript types matching backend schemas
?       ??? auth.ts                   # Auth/session types
?       ??? ui.ts                     # UI-specific types
?
??? tests/
?   ??? unit/                         # Vitest component tests
?   ??? integration/                  # API integration tests (msw)
?   ??? e2e/                          # Playwright E2E tests
?
??? .storybook/                       # Storybook config
??? next.config.ts
??? tailwind.config.ts
??? tsconfig.json
??? package.json
??? Dockerfile
??? .env.example
```

---

## 4. Phase 1: MVP Dashboard (Weeks 1-6)

### Week 1-2: Project Setup + Auth

| Task | Est. | Detail |
|------|------|--------|
| Initialize Next.js 14 with TypeScript | 0.5d | App Router, strict TS, path aliases |
| Set up Tailwind CSS + shadcn/ui | 0.5d | Install, configure theme, add base components |
| Set up ESLint + Prettier | 0.5d | Strict config matching backend style |
| Configure NextAuth.js v5 | 1d | GitHub + Google providers, JWT session |
| Build login page | 1d | OAuth buttons, redirect flow |
| Build auth callback handler | 0.5d | Exchange code for JWT, store in session |
| Build auth middleware | 0.5d | Protect dashboard routes, redirect unauthenticated |
| Build user menu (topbar) | 0.5d | Avatar, name, logout, settings link |
| Set up API client | 1d | Typed fetch wrapper, auth header injection, error handling |
| Set up React Query provider | 0.5d | QueryClient config, devtools |

**Deliverable**: User can log in with GitHub/Google, see empty dashboard.

### Week 3-4: Repo Management

| Task | Est. | Detail |
|------|------|--------|
| Build dashboard layout (sidebar + topbar + breadcrumbs) | 2d | Responsive, collapsible sidebar, mobile nav |
| Build repo list page | 1d | Card grid, status badges, last indexed date |
| Build "Add Repo" form | 1d | URL validation, provider select, branch, token |
| Build repo detail page | 1d | Snapshot timeline, status, settings |
| Build ingest trigger button with progress | 1d | POST /ingest, poll status, show progress |
| Build snapshot detail page | 1d | File list, symbol count, status |
| Build global loading skeleton | 0.5d | Consistent loading states across pages |
| Build error boundary UI | 0.5d | Friendly error page with retry |

**Deliverable**: User can add repos, trigger ingestion, see results.

### Week 5-6: Analysis + Health

| Task | Est. | Detail |
|------|------|--------|
| Build analysis overview page | 1d | Stats cards (symbols, edges, modules), kind breakdown chart |
| Build symbol browser table | 2d | Filterable, sortable, paginated, click-to-detail |
| Build symbol detail panel | 1d | Name, kind, location, callers, callees |
| Build code health dashboard | 2d | Score gauge, category radar chart, findings table |
| Build health rule configuration panel | 1d | Category toggles, threshold sliders, disabled rules |
| Build findings detail view | 1d | Rule ID, severity badge, suggestion, code link |
| Deploy to Vercel (preview) | 0.5d | Auto-deploy on push, preview URLs |

**Deliverable**: Full analysis + code health UI. MVP is usable.

---

## 5. Phase 2: Core Features (Weeks 7-12)

### Week 7-8: Code Graph Visualization

| Task | Est. | Detail |
|------|------|--------|
| Build code graph page with React Flow | 3d | Nodes = symbols, edges = calls/inherits/contains |
| Add graph layout algorithms (dagre) | 1d | Hierarchical for inheritance, force for calls |
| Add node click: show symbol detail panel | 1d | Side panel with callers, callees, metrics |
| Add graph filtering (by kind, namespace, file) | 1d | Toolbar with filter dropdowns |
| Add graph search (find symbol by name) | 0.5d | Cmd+F within graph |
| Add graph export (SVG/PNG) | 0.5d | Download button |
| Add mini-map for large graphs | 0.5d | React Flow MiniMap component |

### Week 9-10: Q&A Chat Interface

| Task | Est. | Detail |
|------|------|--------|
| Build chat interface (message list + input) | 2d | Streaming SSE responses, markdown rendering |
| Build citation links (click to navigate to code) | 1d | Parse [file:line] citations, link to symbol browser |
| Build suggested questions (context-aware) | 1d | Pre-built questions based on repo analysis |
| Build chat history (persist conversations) | 1d | Local storage + optional server-side |
| Add code block rendering with syntax highlighting | 0.5d | React-markdown + rehype-highlight |
| Add copy-to-clipboard for code blocks | 0.5d | Button in code block header |

### Week 11-12: PR Review + Docs

| Task | Est. | Detail |
|------|------|--------|
| Build PR review page (paste diff) | 1d | Textarea for diff paste, trigger review |
| Build review results view | 2d | Findings with severity, file, line, suggestion |
| Build side-by-side diff viewer with annotations | 2d | Highlight reviewed lines, inline findings |
| Build review history page | 1d | Past reviews list with dates, scores |
| Build doc generation form | 1d | Select scope, format, trigger |
| Build doc viewer (markdown render) | 1d | Full rendered doc with table of contents |
| Build doc list page | 0.5d | Generated docs history |

---

## 6. Phase 3: Advanced UI (Weeks 13-20)

### Week 13-14: Admin Dashboard

| Task | Est. | Detail |
|------|------|--------|
| Build admin layout (role-gated) | 1d | Only superadmin/admin/support see admin nav |
| Build user management table | 2d | List, search, filter, role dropdown, actions |
| Build plan management page | 2d | CRUD plans, JSON limits editor with preview |
| Build usage analytics dashboard | 2d | Charts: scans/day, tokens/day, top users, per-plan |
| Build system info page | 1d | Version, edition, counts, health status |

### Week 15-16: Settings + Billing

| Task | Est. | Detail |
|------|------|--------|
| Build user profile settings | 1d | Name, email, avatar, notification preferences |
| Build Stripe billing portal integration | 2d | Plan selection, payment method, invoices |
| Build plan comparison page | 1d | Feature matrix, CTA buttons |
| Build API key management page | 1d | Create, list, revoke, copy |
| Build notification preferences | 1d | Email/in-app notification toggles |

### Week 17-18: Real-time Features

| Task | Est. | Detail |
|------|------|--------|
| Build WebSocket connection for job status | 2d | Live ingestion progress, analysis status |
| Build toast notification system | 1d | Success/error/warning/info toasts |
| Build activity feed (recent actions) | 1d | Timeline of recent scans, reviews, docs |
| Build real-time health score badge (per repo) | 1d | Auto-refresh after new scan |

### Week 19-20: Polish + Performance

| Task | Est. | Detail |
|------|------|--------|
| Add command palette (Cmd+K) | 2d | Search repos, symbols, navigate pages |
| Add keyboard shortcuts throughout | 1d | Navigation, actions, dismiss |
| Add dark/light mode toggle | 1d | System preference detection, manual override |
| Performance audit (Lighthouse) | 1d | Core Web Vitals, bundle size |
| Add skeleton loading states everywhere | 1d | Consistent shimmer animations |
| Add empty states for all pages | 0.5d | Illustrations + CTA when no data |
| Responsive audit (mobile + tablet) | 1d | Test all pages at 375px, 768px, 1024px |

---

## 7. Phase 4: Enterprise UI (Weeks 21-28)

| Task | Est. | Detail |
|------|------|--------|
| Build team/org management pages | 3d | Members, roles, invite, remove |
| Build org-level dashboard | 2d | Aggregated stats across all repos |
| Build org settings (SSO config, billing) | 2d | SAML/OIDC configuration forms |
| Build white-label configuration | 2d | Custom logo, colors, domain |
| Build data export UI (GDPR) | 1d | Request export, download link |
| Build audit log viewer | 2d | Filterable log of all admin actions |
| Build report export (PDF/HTML) | 2d | Health report, review report as downloadable |
| Build scheduled scan configuration | 1d | Cron expression builder, enable/disable |

---

## 8. Phase 5: IDE & Embeddable (Weeks 29-36)

| Task | Est. | Detail |
|------|------|--------|
| Build VS Code extension (webview panels) | 5d | Q&A chat, health findings, doc hover |
| Build VS Code tree view (symbol browser) | 2d | Sidebar panel with symbols from Eidos |
| Build VS Code status bar (health score) | 1d | Repo health score in status bar |
| Build JetBrains plugin (same features) | 5d | IntelliJ platform, Rider users |
| Build embeddable widget (health badge) | 2d | `<iframe>` or `<script>` tag for README |
| Build public API documentation site | 2d | Auto-generated from OpenAPI spec |

---

## 9. Page-by-Page Specification

### 9.1 Dashboard Home (`/`)

```
????????????????????????????????????????????????????
?  Sidebar  ?  Welcome back, {name}                ?
?           ?                                      ?
?  Repos    ?  ???????? ???????? ????????        ?
?  Health   ?  ?Repo 1? ?Repo 2? ?Repo 3?        ?
?  Q&A      ?  ? ?75  ? ? ?92  ? ? ?--  ?        ?
?  Reviews  ?  ? 3d   ? ? 1h   ? ? new  ?        ?
?  Docs     ?  ???????? ???????? ????????        ?
?  Admin    ?                                      ?
?           ?  Recent Activity                     ?
?  ???????  ?  • Scanned myapp/backend  (2h ago)  ?
?  Settings ?  • Health check: 75/100   (3h ago)  ?
?  Billing  ?  • PR Review: 3 findings  (1d ago)  ?
????????????????????????????????????????????????????
```

### 9.2 Code Health Page (`/repos/[id]/snapshots/[sid]/health`)

```
????????????????????????????????????????????????????
?  Overall Score: 78/100  [??????????]            ?
?                                                    ?
?  ???????????  ???????????  ???????????          ?
?  ?Clean 92 ?  ?SOLID 85 ?  ?Cplx  70 ?          ?
?  ?Code     ?  ?         ?  ?         ?          ?
?  ???????????  ???????????  ???????????          ?
?  ???????????  ???????????  ???????????          ?
?  ?Name  95 ?  ?Sec  100 ?  ?Dsgn  60 ?          ?
?  ???????????  ???????????  ???????????          ?
?                                                    ?
?  [Configure Rules]  [Export PDF]  [Re-scan]       ?
?                                                    ?
?  Findings (23)          Filter: [All] [Critical]  ?
?  ???????????????????????????????????????????????  ?
?  ? ? SEC001 hardcoded_secret    Config.cs:15   ?  ?
?  ? ? SOLID001 god_class         UserSvc.cs:1   ?  ?
?  ? ? CC001 long_method          Repo.cs:45     ?  ?
?  ? ? SM002 feature_envy         Auth.cs:102    ?  ?
?  ? ? NM001 short_name           X.cs:1         ?  ?
?  ???????????????????????????????????????????????  ?
????????????????????????????????????????????????????
```

### 9.3 Q&A Chat (`/repos/[id]/snapshots/[sid]/ask`)

```
????????????????????????????????????????????????????
?  Ask about: myapp/backend (snapshot #3)           ?
?                                                    ?
?  ?? User ???????????????????????????????????????  ?
?  ? How does authentication work in this app?    ?  ?
?  ???????????????????????????????????????????????  ?
?                                                    ?
?  ?? Eidos ??????????????????????????????????????  ?
?  ? The authentication system uses JWT tokens    ?  ?
?  ? with OAuth2 providers...                     ?  ?
?  ?                                              ?  ?
?  ? **Evidence:**                                ?  ?
?  ? - [AuthController.cs:25-40] Login flow      ?  ?
?  ? - [TokenService.cs:12] Token generation     ?  ?
?  ?                                              ?  ?
?  ? **Confidence:** High                         ?  ?
?  ???????????????????????????????????????????????  ?
?                                                    ?
?  Suggested: [What patterns are used?]             ?
?             [Show me the entry points]            ?
?                                                    ?
?  ???????????????????????????????????????? [Send]  ?
?  ? Type your question...                          ?
?  ??????????????????????????????????????????????? ?
????????????????????????????????????????????????????
```

---

## 10. Component Library

Build these reusable components first (via shadcn/ui + custom):

| Component | Source | Priority |
|-----------|--------|----------|
| `Button` | shadcn/ui | P0 |
| `Input`, `Textarea` | shadcn/ui | P0 |
| `Card`, `CardHeader`, `CardContent` | shadcn/ui | P0 |
| `Table`, `TableHeader`, `TableRow` | shadcn/ui | P0 |
| `Badge` | shadcn/ui | P0 |
| `Dialog`, `Sheet` | shadcn/ui | P0 |
| `DropdownMenu`, `Select` | shadcn/ui | P0 |
| `Tabs` | shadcn/ui | P0 |
| `Toast` (via Sonner) | shadcn/ui | P0 |
| `Command` (Cmd+K) | shadcn/ui | P1 |
| `ScoreGauge` | Custom | P0 |
| `SeverityBadge` | Custom | P0 |
| `CodeBlock` | Custom (Monaco) | P1 |
| `GraphCanvas` | Custom (React Flow) | P1 |
| `ChatMessage` | Custom | P1 |
| `StreamingText` | Custom | P1 |
| `EmptyState` | Custom | P1 |
| `StatusDot` | Custom | P0 |

---

## 11. State Management

### Server State (React Query)

```typescript
// hooks/use-repos.ts
export function useRepos() {
  return useQuery({ queryKey: ['repos'], queryFn: api.repos.list });
}

export function useRepo(id: string) {
  return useQuery({ queryKey: ['repos', id], queryFn: () => api.repos.get(id) });
}

export function useIngest(repoId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: IngestRequest) => api.repos.ingest(repoId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['repos', repoId] }),
  });
}
```

### Client State (Zustand)

```typescript
// stores/theme-store.ts
export const useThemeStore = create<ThemeStore>((set) => ({
  theme: 'system',
  setTheme: (theme) => set({ theme }),
}));

// stores/sidebar-store.ts
export const useSidebarStore = create<SidebarStore>((set) => ({
  collapsed: false,
  toggle: () => set((s) => ({ collapsed: !s.collapsed })),
}));
```

---

## 12. API Client Layer

Auto-generate TypeScript types from the FastAPI OpenAPI schema:

```typescript
// lib/api-client.ts
const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
  private token: string | null = null;

  setToken(token: string) { this.token = token; }

  private async fetch<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
        ...options?.headers,
      },
    });
    if (!res.ok) throw new ApiError(res.status, await res.json());
    return res.json();
  }

  repos = {
    list: () => this.fetch<RepoOut[]>('/repos'),
    create: (body: RepoCreate) => this.fetch<RepoOut>('/repos', { method: 'POST', body: JSON.stringify(body) }),
    ingest: (id: string, body: IngestRequest) => this.fetch<IngestOut>(`/repos/${id}/ingest`, { method: 'POST', body: JSON.stringify(body) }),
    // ... all endpoints
  };

  health = {
    rules: (repoId: string, snapId: string) => this.fetch<RuleMetadata[]>(`/repos/${repoId}/snapshots/${snapId}/health/rules`),
    check: (repoId: string, snapId: string, body: HealthCheckRequest) => this.fetch<HealthReport>(`/repos/${repoId}/snapshots/${snapId}/health`, { method: 'POST', body: JSON.stringify(body) }),
  };
}

export const api = new ApiClient();
```

---

## 13. Authentication Flow

```
User clicks "Login with GitHub"
    ? NextAuth redirects to GitHub OAuth
    ? GitHub redirects to /api/auth/callback/github
    ? NextAuth receives GitHub access token
    ? NextAuth calls Eidos backend: POST /auth/callback (GitHub token)
    ? Backend returns Eidos JWT
    ? NextAuth stores Eidos JWT in session
    ? All subsequent API calls include: Authorization: Bearer {eidos_jwt}
```

### Middleware (route protection)

```typescript
// middleware.ts
export function middleware(request: NextRequest) {
  const session = request.cookies.get('next-auth.session-token');
  if (!session && request.nextUrl.pathname.startsWith('/(dashboard)')) {
    return NextResponse.redirect(new URL('/login', request.url));
  }
}
```

---

## 14. Real-time Features

### Job Status (WebSocket or SSE polling)

```typescript
// hooks/use-job-status.ts
export function useJobStatus(jobId: string) {
  return useQuery({
    queryKey: ['jobs', jobId],
    queryFn: () => api.jobs.get(jobId),
    refetchInterval: (query) =>
      query.state.data?.status === 'completed' ? false : 2000,
  });
}
```

### Streaming Q&A (SSE)

```typescript
// hooks/use-chat.ts
export function useStreamingChat() {
  const [messages, setMessages] = useState<Message[]>([]);

  const send = async (question: string) => {
    setMessages(prev => [...prev, { role: 'user', content: question }]);
    const response = await fetch(`${BASE_URL}/repos/${repoId}/snapshots/${snapId}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ question }),
    });
    // Handle streaming response
    const reader = response.body?.getReader();
    // ... stream chunks into messages state
  };

  return { messages, send };
}
```

---

## 15. Testing Strategy

| Layer | Tool | Target | Coverage |
|-------|------|--------|----------|
| Unit tests | Vitest | Utility functions, hooks, stores | > 90% |
| Component tests | Vitest + Testing Library | All components in isolation | > 80% |
| Integration tests | Vitest + MSW | API flows (login, CRUD, health check) | > 70% |
| E2E tests | Playwright | Critical user journeys (10-15 tests) | Key paths |
| Visual tests | Storybook + Chromatic | Component appearance, responsive | All components |

### Critical E2E Test Cases

1. Login with GitHub -> see dashboard
2. Add repo -> trigger ingestion -> see completed
3. View analysis overview -> browse symbols
4. Run health check with custom config -> see findings
5. Ask a question -> see streaming response with citations
6. Submit PR diff for review -> see findings
7. Generate documentation -> view rendered doc
8. Admin: change user role
9. Admin: create plan with custom limits
10. Settings: update profile

---

## 16. Performance Budget

| Metric | Target | Measurement |
|--------|--------|-------------|
| First Contentful Paint | < 1.2s | Lighthouse |
| Largest Contentful Paint | < 2.5s | Lighthouse |
| Cumulative Layout Shift | < 0.1 | Lighthouse |
| Time to Interactive | < 3.5s | Lighthouse |
| JS bundle (initial) | < 150KB gzipped | `next build` output |
| API response (P95) | < 200ms | React Query devtools |
| Graph render (1000 nodes) | < 2s | Custom benchmark |

---

## 17. Accessibility Requirements

| Requirement | Standard | Implementation |
|-------------|----------|----------------|
| Keyboard navigation | WCAG 2.1 AA | All interactive elements focusable, visible focus ring |
| Screen reader | WCAG 2.1 AA | ARIA labels on all controls, semantic HTML |
| Color contrast | WCAG 2.1 AA | 4.5:1 minimum ratio (enforced by Tailwind config) |
| Reduced motion | WCAG 2.1 AA | `prefers-reduced-motion` respected |
| Focus management | WCAG 2.1 AA | Focus trapped in dialogs, returned on close |
| Text scaling | WCAG 2.1 AA | Works at 200% zoom |

---

## 18. Design System

### Colors (Tailwind)

```
Primary:    hsl(221, 83%, 53%)  -- blue-600
Secondary:  hsl(215, 20%, 65%)  -- slate-400
Success:    hsl(142, 71%, 45%)  -- green-500
Warning:    hsl(38, 92%, 50%)   -- amber-500
Error:      hsl(0, 84%, 60%)    -- red-500
Critical:   hsl(0, 84%, 40%)    -- red-800

Background: hsl(0, 0%, 100%)    -- white (light)
            hsl(222, 47%, 11%)   -- slate-950 (dark)
```

### Typography

```
Font:       Inter (Google Fonts)
Code font:  JetBrains Mono (Google Fonts)

Headings:   font-semibold
Body:       font-normal
Code:       font-mono
```

### Spacing

```
Base unit:  4px (Tailwind default)
Card padding: p-6
Section gap: space-y-6
Page max-width: max-w-7xl (1280px)
```

---

## 19. Deployment

### Vercel (recommended for Next.js)

```yaml
# vercel.json
{
  "framework": "nextjs",
  "buildCommand": "next build",
  "env": {
    "NEXT_PUBLIC_API_URL": "https://api.eidos.dev",
    "NEXTAUTH_URL": "https://app.eidos.dev",
    "NEXTAUTH_SECRET": "@nextauth-secret"
  }
}
```

### Docker (for self-hosted / enterprise)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM node:20-alpine AS runner
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static .next/static
COPY --from=builder /app/public public
ENV NODE_ENV=production
EXPOSE 3000
CMD ["node", "server.js"]
```

### URL Structure

| Environment | Frontend | Backend API |
|-------------|----------|-------------|
| Local | http://localhost:3000 | http://localhost:8000 |
| Staging | https://staging.eidos.dev | https://api-staging.eidos.dev |
| Production | https://app.eidos.dev | https://api.eidos.dev |

---

## 20. Development Workflow

### Getting Started

```bash
# Clone and setup
cd frontend
corepack enable
pnpm install

# Environment
cp .env.example .env.local
# Edit: NEXT_PUBLIC_API_URL=http://localhost:8000

# Development
pnpm dev          # Start dev server (port 3000)
pnpm build        # Production build
pnpm test         # Run Vitest
pnpm test:e2e     # Run Playwright
pnpm storybook    # Component development
pnpm lint         # ESLint + Prettier check
```

### Git Workflow

```
feature/frontend-{feature-name}
    ? PR ? CI (lint + type-check + test + build) ? Review ? Merge
```

### CI Pipeline

```yaml
Frontend CI:
  - pnpm install --frozen-lockfile
  - pnpm lint
  - pnpm type-check     # tsc --noEmit
  - pnpm test --coverage
  - pnpm build
  - pnpm test:e2e       # Playwright against staging API
```
