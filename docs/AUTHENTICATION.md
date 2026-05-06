# Authentication Guide

Complete guide to authentication and authorization in Eidos.

---

## Authentication Methods

### 1. JWT (JSON Web Token) via OAuth

**GitHub OAuth:**
```
GET /auth/login ? redirects to GitHub
GET /auth/callback ? exchanges code, returns JWT
```

**Google OAuth:**
```
GET /auth/google/login ? redirects to Google
GET /auth/google/callback ? exchanges code, returns JWT
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "gh-12345",
    "login": "username",
    "name": "Full Name",
    "email": "user@example.com",
    "avatar_url": "https://..."
  }
}
```

**Usage:**
```
Authorization: Bearer eyJ...
```

### 2. API Keys (for CI/CD & programmatic access)

**Create:**
```bash
POST /auth/api-keys?name=CI&scopes=read:repos,write:snapshots&expires_in_days=90
```

**Response (key shown once):**
```json
{
  "id": "abc123",
  "name": "CI",
  "key": "eidos_aBcDeFgHiJkLmNoPqRsTuVwXyZ...",
  "prefix": "eidos_aBcDe",
  "scopes": ["read:repos", "write:snapshots"],
  "expires_at": "2026-08-01T00:00:00Z"
}
```

**Usage:**
```
X-API-Key: eidos_aBcDeFgHiJkLmNoPqRsTuVwXyZ...
```

---

## Authorization Model

### Layers (checked in order)

```
1. Authentication   ? WHO are you? (JWT or API key)
2. Scope check      ? WHAT can you do? (role-based or key-based)
3. Role check       ? Optional whitelist of allowed roles
4. Repo ownership   ? Optional: do you own/have access to this repo?
```

### Roles

| Role | Description | Scope Set |
|------|-------------|-----------|
| `superadmin` | Platform operator | `*` (all) |
| `admin` | Organization admin | All 16 scopes |
| `employee` | Internal developer | All non-admin scopes |
| `user` | External user | All non-admin scopes |
| `support` | Read-only support | Read scopes + `admin:audit` |

### Scopes (17 total)

| Category | Scope | Description |
|----------|-------|-------------|
| Repos | `read:repos` | List and view repos |
| | `write:repos` | Create, update, delete repos |
| Snapshots | `read:snapshots` | List and view snapshots |
| | `write:snapshots` | Create snapshots, persist findings |
| | `delete:snapshots` | Delete snapshots |
| Analysis | `read:analysis` | View symbols, edges, health, graphs |
| Coverage | `read:coverage` | View coverage reports |
| | `write:coverage` | Upload/delete coverage |
| Gates | `read:gates` | View quality gates |
| | `write:gates` | Manage quality gates |
| Actions | `write:reviews` | Submit PR reviews |
| | `write:docs` | Generate documentation |
| Export | `read:export` | Download exports |
| Admin | `admin:users` | Manage users/roles |
| | `admin:plans` | Manage plans |
| | `admin:audit` | View/manage audit log |
| Special | `*` | Full access |

### Resource-Level Access

Repos can be shared with specific users:

```
POST /repos/{id}/permissions
{
  "user_id": "user123",
  "level": "editor"    // viewer | editor | owner
}
```

Access resolution chain:
```
Admin/Superadmin role? ? Allow all repos
?
Repo owner_id matches user? ? Allow
?
RepoPermission entry exists? ? Allow (level determines write/delete)
?
Team has TeamRepoAccess? ? Allow
?
Deny (404)
```

### Teams

```bash
POST /teams                          # Create team
POST /teams/{id}/members             # Add user to team
POST /teams/{id}/repos               # Grant team repo access
```

Team members inherit repo access from team-level grants.

---

## Security Best Practices

1. **Use least-privilege API keys** — only grant scopes the key actually needs
2. **Set expiration** — use `expires_in_days` for CI keys
3. **Rotate keys** — revoke and recreate keys periodically
4. **Use JWT for interactive** — API keys for automation only
5. **Monitor audit log** — `GET /admin/audit-log` shows all access denials

---

## Development Mode

Set `EIDOS_AUTH_ENABLED=false` to disable all auth checks.
An anonymous superadmin user is returned for all requests.

---

## Token Lifecycle

| Token Type | Lifetime | Refresh |
|------------|----------|---------|
| JWT | 24 hours | Re-authenticate via OAuth |
| API Key | Configurable (1-365 days or never) | Create new key, revoke old |

---

## Error Responses

| Code | Meaning |
|------|---------|
| 401 | Not authenticated (no token, expired, invalid) |
| 403 | Authenticated but insufficient permissions |
| 404 | Resource not found OR no access (prevents leaking existence) |
| 429 | Quota exceeded |
