# RBAC Integration & Cinematic Loading — Execution Plan

## Overview

This document covers two independent features to implement:

1. **RBAC System Integration** — Connect the existing backend auth/permissions system to the frontend UI
2. **Cinematic Logo Loading Screen** — An animated Eidos logo draw-on effect during app initialization

---

## Part 1: RBAC System Integration

### What Already Exists (Backend)

The backend has a **complete, production-grade RBAC system** already built. Here is what is available:

| Component | File | What It Does |
|---|---|---|
| User Model | `backend/app/storage/models.py` | `User` with `id`, `role`, `github_login`, `email`, `avatar_url`, `auth_provider` |
| Roles | `backend/app/storage/models.py` | `UserRole` enum: `superadmin`, `admin`, `employee`, `support`, `user` |
| Scopes | `backend/app/auth/scopes.py` | 15 granular scopes: `read:repos`, `write:repos`, `read:analysis`, `admin:users`, etc. |
| Role?Scope Mapping | `backend/app/auth/scopes.py` | `ROLE_SCOPES` dict maps each role to allowed scopes |
| JWT Tokens | `backend/app/auth/token_service.py` | `create_access_token()`, `decode_access_token()` using HS256 |
| GitHub OAuth | `backend/app/auth/github_oauth.py` | Full OAuth2 flow with code exchange and profile fetch |
| Google OAuth | `backend/app/auth/google_oauth.py` | Full OAuth2 flow (alternative provider) |
| Auth Dependencies | `backend/app/auth/dependencies.py` | `get_current_user`, `require_role()`, `require_quota()`, `require_repo_access()` |
| Scope Enforcement | `backend/app/auth/scopes.py` | `require_scope("write:repos")` decorator for endpoints |
| Protected Decorator | `backend/app/auth/scopes.py` | `protected(scope=..., roles=[...], require_repo_owner=True)` — compound check |
| API Keys | `backend/app/storage/models.py` | `ApiKey` model with hash, scopes, expiration, usage tracking |
| API Key Auth | `backend/app/auth/dependencies.py` | `X-API-Key` header validation with scope extraction |
| Permission Cache | `backend/app/auth/permission_cache.py` | In-memory TTL cache (300s, 10K entries) |
| Usage Metering | `backend/app/auth/metering.py` | Plan-based quotas: unlimited, time-based, token-based, scan-based |
| Plans/Subscriptions | `backend/app/storage/models.py` | `Plan`, `UserSubscription` models |
| Teams | `backend/app/api/teams.py` | Team CRUD, member management, repo access granting |
| Repo Permissions | `backend/app/api/permissions.py` | Per-repo `viewer`/`editor`/`owner` grants |
| Admin Panel | `backend/app/api/admin.py` | User list, role update, plan management, subscription assignment |
| Audit Log | `backend/app/api/audit.py` | Event history with filters, stats, CSV export |
| Auth Toggle | `backend/app/core/config.py` | `auth_enabled: bool = False` — when False, anonymous = superadmin |

### What the Frontend Needs

The frontend currently runs in **demo mode** (no auth, anonymous = superadmin). To integrate RBAC, we need:

---

### 1.1 — Login / Auth Flow

**What to build**

- Login page with GitHub OAuth button (and Google as alt)
- Token storage in `localStorage` or `sessionStorage`
- Auto-redirect to login when receiving 401
- Token refresh or re-login prompt on expiry
- Logout button in settings/sidebar

**Why**

Without login, there is no user identity. The entire RBAC system depends on knowing who the user is.

**Backend endpoints used**

- `GET /auth/login` ? redirects to GitHub
- `GET /auth/callback?code=...` ? returns JWT
- `GET /auth/google/login` ? redirects to Google
- `GET /auth/google/callback?code=...` ? returns JWT
- `GET /auth/me` ? returns current user info
- `POST /auth/logout` ? client-side token removal

**What you will see**

1. First visit ? redirected to a login page with "Sign in with GitHub" and "Sign in with Google" buttons
2. Click GitHub ? redirected to GitHub OAuth ? back to Eidos with a session
3. User avatar and name appear in the sidebar/status bar
4. Token stored securely; auto-refreshes or prompts re-login on expiry

---

### 1.2 — User Profile & Session Display

**What to build**

- Display current user avatar, name, and role in the sidebar bottom
- Show role badge (color-coded: superadmin=purple, admin=blue, employee=green, support=yellow, user=grey)
- Add "My Profile" section in Settings showing permissions summary

**Why**

Users need to know who they are logged in as and what they can do. This builds trust and avoids confusion when actions are denied.

**Backend endpoints used**

- `GET /auth/me` ? `{ id, github_login, name, email, avatar_url, role }`

**What you will see**

1. Sidebar bottom shows your avatar circle + name + role badge
2. Settings page has a "My Account" card showing: name, email, provider, role, scopes summary
3. If role is `user` ? "Standard access" label; if `admin` ? "Administrator" with special badge

---

### 1.3 — Permission-Aware UI

**What to build**

- Hide or disable UI elements the current user cannot access based on their role/scopes
- Read-only mode for `support` role (can view but not write)
- Hide admin features (user management, plan management) for non-admin roles
- Disable "Delete Snapshot", "Re-ingest", and "Create Repo" for users without write scopes

**Why**

Showing buttons that will return 403 is bad UX. The interface should adapt to what the user can actually do.

**Scope?UI mapping**

| Scope | UI Elements Affected |
|---|---|
| `write:repos` | Create repo button, delete repo |
| `write:snapshots` | Ingest button, re-ingest |
| `delete:snapshots` | Delete snapshot button |
| `read:analysis` | All analysis pages (everyone has this) |
| `write:reviews` | PR Review page submit button |
| `write:docs` | Doc generation button |
| `read:export` | Export page access |
| `admin:users` | Admin panel in settings |
| `admin:audit` | Audit log viewer |

**What you will see**

1. As `user`: All analysis pages work, you can create/delete your own repos and snapshots
2. As `support`: Everything is read-only; write buttons are hidden
3. As `admin`: Full access + "Admin" section in settings with user management
4. As `superadmin`: Everything + system info panel

---

### 1.4 — API Key Management UI

**What to build**

- Section in Settings to create, list, and revoke API keys
- Key creation form: name, scopes (checkboxes), expiration
- Display key only once on creation (masked afterward)
- Usage stats per key

**Why**

API keys are critical for CI/CD integration. Managing them through the UI is expected.

**Backend endpoints used**

- `POST /auth/api-keys` ? create key (returns raw key once)
- `GET /auth/api-keys` ? list user's active keys
- `DELETE /auth/api-keys/{id}` ? revoke

**What you will see**

1. Settings ? "API Keys" section
2. Click "Create Key" ? modal with name, scope checkboxes, expiration picker
3. Key shown once in a copyable monospace box with warning
4. Table showing: name, prefix, scopes, last used, usage count, revoke button

---

### 1.5 — Admin Panel (for admin/superadmin)

**What to build**

- Admin section accessible from Settings or a dedicated nav item (only for admin+)
- User management: list users, change roles
- Plan management: create plans, assign subscriptions
- System info: edition, version, user count, repo count
- Audit log viewer: filterable event history with severity and export

**Why**

Admins need to manage the platform without touching the database directly.

**Backend endpoints used**

- `GET /admin/system` ? system overview
- `GET /admin/users` ? user list
- `PUT /admin/users/{id}/role` ? change role
- `GET /admin/plans` ? plan list
- `POST /admin/plans` ? create plan
- `POST /admin/users/{id}/subscription` ? assign plan
- `GET /audit/events` ? audit log
- `GET /audit/stats` ? summary counts
- `GET /audit/export/csv` ? CSV download

**What you will see**

1. Admin badge in sidebar for admin/superadmin users
2. Admin ? Users: table with all users, role dropdown to change
3. Admin ? Plans: create/edit subscription plans
4. Admin ? Audit: searchable log with filters (action, user, date range)

---

### 1.6 — Team Management UI

**What to build**

- Teams page: create teams, manage members, assign repo access
- Team member list with role (owner/admin/member)
- Repo permission grants from the team level

**Why**

Teams enable collaborative usage. Without team UI, the backend team features are unused.

**Backend endpoints used**

- `GET /teams` ? list user's teams
- `POST /teams` ? create team
- `POST /teams/{id}/members` ? add member
- `DELETE /teams/{id}/members/{user_id}` ? remove member
- `POST /teams/{id}/repos` ? grant repo access
- `DELETE /teams/{id}/repos/{repo_id}` ? revoke access

**What you will see**

1. New "Teams" nav item under Workspace
2. Team page: create team, invite by GitHub username
3. Team members table with role badges and remove button
4. Team repos: which repos the team can access and at what level

---

### 1.7 — Request Interceptor & Token Management

**What to build**

- Modify `API.req()` in `core.js` to attach `Authorization: Bearer <token>` header
- Handle 401 responses globally ? redirect to login
- Handle 403 responses ? show permission denied toast
- Store token in `localStorage` with expiry check

**Why**

Every API call must carry the auth token. Global interceptors prevent duplicating auth logic across every request.

**Implementation**

```javascript
// In API.req():
if (token) opts.headers['Authorization'] = 'Bearer ' + token;

// On response:
if (r.status === 401) { clearToken(); navigate('login'); }
if (r.status === 403) { toast('Permission denied', false); }
```

**What you will see**

1. All API calls automatically include the auth header
2. If the token expires mid-session ? you see a "Session expired, please log in again" message and redirect
3. If you try an action you don't have permission for ? "Permission denied" toast appears

---

### Integration Order (RBAC)

| Step | Feature | Effort | Depends On |
|---:|---|---|---|
| 1 | Token management & API interceptor | 1 day | — |
| 2 | Login page (GitHub + Google OAuth) | 1 day | Step 1 |
| 3 | User profile display in sidebar | 0.5 day | Step 2 |
| 4 | Permission-aware UI (hide/disable elements) | 1.5 days | Step 2 |
| 5 | API Key management in Settings | 1 day | Step 2 |
| 6 | Admin panel (users, plans, system) | 2 days | Step 4 |
| 7 | Audit log viewer | 1 day | Step 6 |
| 8 | Team management | 1.5 days | Step 4 |

**Total estimated effort: ~10 days**

---

### Auth Mode Toggle

The system supports a clean auth toggle:

- `EIDOS_AUTH_ENABLED=false` (current default): Anonymous user gets `superadmin` role, all scopes granted, no login needed
- `EIDOS_AUTH_ENABLED=true`: Full RBAC enforcement, login required, scopes checked per request

The frontend must detect this mode via `GET /auth/me` or a config endpoint and adapt:
- Auth disabled ? skip login, hide user management, show "Demo Mode" indicator
- Auth enabled ? require login, show full RBAC UI

---

## Part 2: Cinematic Logo Loading Screen

### What to Build

A full-screen loading overlay that appears on initial page load, featuring the Eidos logo being "drawn" with an animated stroke/reveal effect before fading out to reveal the app.

### Design Concept

**The Effect:**

1. Screen is dark (matches dark theme background)
2. The Eidos logo outline begins drawing itself with a smooth SVG stroke animation (like a pen tracing the shape)
3. Once the outline is complete (~1.5s), the fill fades in with a subtle glow
4. The text "Eidos" appears below with a letter-by-letter reveal
5. A subtle "code intelligence" tagline fades in
6. The entire splash fades up/out revealing the app (~0.3s)

**Total duration:** ~2.5–3 seconds (or until the app is ready, whichever is later)

### Why

- **First impression** — The loading screen is the first thing users see. A cinematic reveal communicates quality and confidence.
- **Perceived performance** — A beautiful loading animation makes the initial wait feel intentional rather than broken.
- **Brand reinforcement** — The logo drawn in real-time creates a memorable brand moment.
- **Professional polish** — Tools like Figma, Linear, and Vercel all have branded loading sequences. It signals "premium software."

### Technical Approach

**Step 1: SVG Logo Trace**

The `Eidos.png` (1.4MB source) needs to be traced to SVG paths. This gives us:
- Clean vector geometry
- Animatable `stroke-dasharray` / `stroke-dashoffset` for the draw-on effect
- Scalable at any resolution

Options:
- Manually trace the key shapes using a path editor
- Use the PNG as a background and create a simplified SVG overlay that represents the logo form

**Step 2: CSS Animation**

```css
.splash-logo path {
    stroke-dasharray: 1000;
    stroke-dashoffset: 1000;
    animation: draw 1.5s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

@keyframes draw {
    to { stroke-dashoffset: 0; }
}

.splash-logo .fill {
    opacity: 0;
    animation: fill-in 0.6s ease 1.4s forwards;
}

@keyframes fill-in {
    to { opacity: 1; }
}
```

**Step 3: Loading Logic**

```javascript
// Show splash immediately
// Once DOMContentLoaded + first API response (or timeout):
//   - Add 'loaded' class to splash
//   - After transition, remove splash from DOM
```

**Step 4: Graceful Fallback**

- If the app loads faster than the animation ? wait for animation to finish (min display time)
- If the app takes longer ? extend with a subtle pulsing state
- Respect `prefers-reduced-motion` ? show static logo briefly then fade out

### Implementation Steps

| Step | Task | Details |
|---:|---|---|
| 1 | Create SVG version of Eidos logo | Trace from PNG or create simplified vector |
| 2 | Build splash HTML overlay | Fixed overlay with centered logo SVG + text |
| 3 | Add CSS stroke animation | `stroke-dasharray` draw-on effect |
| 4 | Add fill + glow keyframes | Logo fills in after stroke completes |
| 5 | Add text reveal animation | "Eidos" text appears letter-by-letter |
| 6 | Add JavaScript dismiss logic | Remove splash when app is ready |
| 7 | Add reduced-motion fallback | Static display for accessibility |
| 8 | Add theme-aware colors | Works in both light and dark mode |

### What You Will See

1. **Open Eidos** ? Dark screen appears
2. **0.0–1.5s** ? The Eidos logo outline draws itself from left to right (like a pen tracing)
3. **1.5–2.0s** ? The logo fills with color, a subtle glow radiates outward
4. **2.0–2.5s** ? "Eidos" text reveals character by character below the logo; tagline fades in
5. **2.5–3.0s** ? Everything slides up slightly and fades out
6. **App is revealed** ? Full UI is ready and interactive

### Files to Create/Modify

| File | Purpose |
|---|---|
| `frontend-lite/images/logo.svg` | SVG vector version of logo with animatable paths |
| `frontend-lite/css/splash.css` | All splash screen animations and styles |
| `frontend-lite/index.html` | Add splash overlay markup before `<main>` |
| `frontend-lite/js/core.js` | Add splash dismiss logic after app initialization |

---

## Execution Priority

| Priority | Feature | Why First |
|---:|---|---|
| 1 | Cinematic Loading Screen | Quick visual impact, no backend changes needed, sets professional tone |
| 2 | Token management + API interceptor | Foundation for all RBAC features |
| 3 | Login page | Gate to the authenticated experience |
| 4 | User profile in sidebar | Confirms identity |
| 5 | Permission-aware UI | Makes the app adapt to the user |
| 6 | Admin panel | Enables platform management |
| 7 | API keys + Teams | Power features for production use |

---

## Success Criteria

### Loading Screen
- Logo animation completes without jank at 60 FPS
- Works in both dark and light themes
- Respects `prefers-reduced-motion`
- App is never blocked by the animation (content loads behind it)
- Total time: max 3 seconds unless app genuinely isn't ready

### RBAC Integration
- Demo mode (`auth_enabled=false`) still works exactly as before — zero regression
- Logged-in users see their identity in the UI
- Unauthorized actions are prevented before the request (disabled buttons)
- 401/403 responses are handled gracefully with user feedback
- Admin panel is only visible to admin/superadmin
- API keys can be created and used from the UI
- Audit log is queryable for compliance

---

## Non-Negotiable Rules

1. **Demo mode must never break.** Auth disabled = everything works as before.
2. **Never store tokens in cookies** (XSS-safe localStorage with secure handling).
3. **Never show a raw 403 error.** Always translate to human-friendly text.
4. **Never block the UI on auth checks.** Load optimistically, restrict reactively.
5. **The loading screen must not delay the app.** It runs in parallel with initialization.
6. **Logo animation must be SVG-based** for scalability and performance.
7. **Every RBAC decision in the frontend is advisory** — the backend is the source of truth.
