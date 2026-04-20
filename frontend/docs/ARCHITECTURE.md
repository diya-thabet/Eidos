# Frontend Architecture

## Rendering Strategy

| Route Group | Rendering | Reason |
|-------------|-----------|--------|
| `(marketing)` | Server (SSR) | SEO for landing, pricing pages |
| `(auth)` | Server | Minimal JS, fast load |
| `(dashboard)` | Client-heavy | Interactive dashboards, real-time updates |

## Data Flow

```
Server Component (initial data) ? React Query (mutations, polling) ? Zustand (UI state)
```

## Key Patterns

1. **Server Components by default** — data fetching at the component level
2. **"use client" only when needed** — interactivity, hooks, browser APIs
3. **React Query for server state** — caching, invalidation, optimistic updates
4. **Zustand for client state** — sidebar, theme, filters (minimal)
5. **Typed API client** — single source of truth matching backend schemas
6. **shadcn/ui components** — accessible, customizable, consistent

## Route Map

| Path | Purpose |
|------|---------|
| `/` | Landing page (marketing) |
| `/login` | OAuth login |
| `/repos` | Repository list |
| `/repos/new` | Add repository |
| `/repos/[id]` | Repository detail |
| `/repos/[id]/snapshots/[sid]` | Snapshot overview |
| `/repos/[id]/snapshots/[sid]/symbols` | Symbol browser |
| `/repos/[id]/snapshots/[sid]/graph` | Code graph |
| `/repos/[id]/snapshots/[sid]/health` | Code health |
| `/repos/[id]/snapshots/[sid]/ask` | Q&A chat |
| `/repos/[id]/snapshots/[sid]/review` | PR review |
| `/repos/[id]/snapshots/[sid]/docs` | Generated docs |
| `/admin` | System admin |
| `/admin/users` | User management |
| `/admin/plans` | Plan management |
| `/admin/usage` | Usage analytics |
| `/settings` | User profile |
| `/settings/billing` | Billing management |
