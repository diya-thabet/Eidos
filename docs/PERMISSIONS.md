# Permissions Reference

Complete endpoint ? scope mapping for the Eidos API.

---

## Scope Catalog (17 scopes)

| Scope | Description |
|-------|-------------|
| `read:repos` | List and view repos |
| `write:repos` | Create, update, delete repos |
| `read:snapshots` | List and view snapshots |
| `write:snapshots` | Create snapshots (ingest), persist findings, tag |
| `delete:snapshots` | Delete snapshots |
| `read:analysis` | View symbols, edges, health, graphs, diagrams |
| `read:coverage` | View coverage reports |
| `write:coverage` | Upload/delete coverage reports |
| `read:gates` | View quality gates |
| `write:gates` | Create, update, delete, evaluate quality gates |
| `write:reviews` | Submit PR reviews |
| `write:docs` | Generate documentation |
| `read:export` | Download exports (JSON, CSV, SARIF, SBOM, .eidos) |
| `admin:users` | Manage users and roles |
| `admin:plans` | Manage subscription plans |
| `admin:audit` | View and manage audit log |
| `*` | Full access (all scopes) |

---

## Endpoint ? Scope Matrix

### Repos (`/repos`)

| Method | Path | Scope | Notes |
|--------|------|-------|-------|
| GET | `/repos` | `read:repos` | List all repos |
| POST | `/repos` | `write:repos` | Create repo |
| GET | `/repos/{id}/status` | `read:repos` | Repo status |
| PATCH | `/repos/{id}` | `write:repos` | Update repo |
| DELETE | `/repos/{id}` | `write:repos` | Delete repo |
| POST | `/repos/{id}/ingest` | `write:snapshots` | Trigger ingestion |

### Snapshots

| Method | Path | Scope |
|--------|------|-------|
| GET | `/repos/{id}/snapshots` | `read:snapshots` |
| GET | `/repos/{id}/snapshots/{sid}` | `read:snapshots` |
| DELETE | `/repos/{id}/snapshots/{sid}` | `delete:snapshots` |
| GET | `/repos/{id}/snapshots/{sid}/files` | `read:analysis` |

### Analysis

| Method | Path | Scope |
|--------|------|-------|
| GET | `/repos/{id}/snapshots/{sid}/symbols` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/symbols/{fq}/detail` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/edges` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/overview` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/callgraph/{fq}` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/symbols/{fq}/callers` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/call-cycles` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/dead-code` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/clones` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/coupling` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/dependencies` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/blame/{path}` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/diagram` | `read:analysis` |
| GET | `/repos/{id}/health-trend` | `read:analysis` |

### Health Score

| Method | Path | Scope |
|--------|------|-------|
| GET | `/repos/{id}/snapshots/{sid}/health-score` | `read:analysis` |
| GET | `/repos/{id}/health-history` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/health/findings` | `read:analysis` |
| POST | `/repos/{id}/snapshots/{sid}/health/findings` | `write:snapshots` |
| GET | `/repos/{id}/snapshots/{sid}/health/diff/{prev}` | `read:analysis` |

### Coverage

| Method | Path | Scope |
|--------|------|-------|
| GET | `/repos/{id}/snapshots/{sid}/coverage` | `read:coverage` |
| POST | `/repos/{id}/snapshots/{sid}/coverage` | `write:coverage` |
| DELETE | `/repos/{id}/snapshots/{sid}/coverage` | `write:coverage` |
| GET | `/repos/{id}/coverage/history` | `read:coverage` |

### Quality Gates

| Method | Path | Scope |
|--------|------|-------|
| GET | `/repos/{id}/quality-gates` | `read:gates` |
| GET | `/repos/{id}/quality-gates/{gid}` | `read:gates` |
| POST | `/repos/{id}/quality-gates` | `write:gates` |
| PATCH | `/repos/{id}/quality-gates/{gid}` | `write:gates` |
| DELETE | `/repos/{id}/quality-gates/{gid}` | `write:gates` |
| POST | `/repos/{id}/snapshots/{sid}/evaluate-gate/{gid}` | `write:gates` |
| GET | `/repos/quality-gates/schema` | `read:gates` |

### Tags

| Method | Path | Scope |
|--------|------|-------|
| GET | `/repos/{id}/snapshots/{sid}/tags` | `read:snapshots` |
| POST | `/repos/{id}/snapshots/{sid}/tags` | `write:snapshots` |
| DELETE | `/repos/{id}/snapshots/{sid}/tags/{tag}` | `write:snapshots` |
| GET | `/repos/{id}/snapshots/by-tag/{tag}` | `read:snapshots` |
| GET | `/repos/tags/stats` | `read:snapshots` |

### Bulk Operations

| Method | Path | Scope |
|--------|------|-------|
| POST | `/repos/{id}/snapshots/bulk-delete` | `write:snapshots` |
| POST | `/repos/{id}/snapshots/bulk-tag` | `write:snapshots` |
| DELETE | `/repos/{id}/snapshots/older-than/{days}` | `delete:snapshots` |
| POST | `/repos/bulk-delete` | `admin:users` |

### Exports

| Method | Path | Scope |
|--------|------|-------|
| GET | `/repos/{id}/snapshots/{sid}/export/json` | `read:export` |
| GET | `/repos/{id}/snapshots/{sid}/export/sarif` | `read:export` |
| GET | `/repos/{id}/snapshots/{sid}/export/sbom` | `read:export` |
| GET | `/repos/{id}/export` | `read:export` |
| POST | `/repos/{id}/import` | `write:repos` |

### Reviews & Docs

| Method | Path | Scope |
|--------|------|-------|
| POST | `/repos/{id}/snapshots/{sid}/review` | `write:reviews` |
| GET | `/repos/{id}/snapshots/{sid}/reviews` | `write:reviews` |
| POST | `/repos/{id}/snapshots/{sid}/docs/generate` | `write:docs` |
| GET | `/repos/{id}/snapshots/{sid}/docs` | `write:docs` |
| GET | `/repos/{id}/snapshots/{sid}/docs/{did}` | `write:docs` |

### Search & Q&A

| Method | Path | Scope |
|--------|------|-------|
| GET | `/repos/{id}/snapshots/{sid}/search` | `read:analysis` |
| GET | `/repos/{id}/snapshots/{sid}/search/fulltext` | `read:analysis` |
| POST | `/repos/{id}/snapshots/{sid}/ask` | `read:analysis` |

### Indexing

| Method | Path | Scope |
|--------|------|-------|
| POST | `/repos/{id}/snapshots/{sid}/index` | `write:snapshots` |
| GET | `/repos/{id}/snapshots/{sid}/summaries` | `write:snapshots` |

### Admin

| Method | Path | Scope |
|--------|------|-------|
| GET | `/admin/users` | `admin:users` |
| GET | `/admin/users/{id}` | `admin:users` |
| PUT | `/admin/users/{id}/role` | `admin:users` |
| GET | `/admin/plans` | `admin:users` |
| POST | `/admin/plans` | `admin:users` |
| GET | `/admin/usage` | `admin:users` |
| GET | `/admin/system` | `admin:users` |

### Audit Log

| Method | Path | Scope |
|--------|------|-------|
| GET | `/admin/audit-log` | `admin:audit` |
| GET | `/admin/audit-log/export` | `admin:audit` |
| GET | `/admin/audit-log/stats` | `admin:audit` |
| DELETE | `/admin/audit-log/purge` | `admin:audit` |

### Auth (no scope required — auth endpoints)

| Method | Path | Scope |
|--------|------|-------|
| GET | `/auth/login` | — |
| GET | `/auth/callback` | — |
| GET | `/auth/google/login` | — |
| GET | `/auth/google/callback` | — |
| GET | `/auth/me` | — |
| POST | `/auth/logout` | — |
| POST | `/auth/api-keys` | — |
| GET | `/auth/api-keys` | — |
| DELETE | `/auth/api-keys/{id}` | — |
| GET | `/auth/api-keys/scopes` | — |

---

## How Scopes Work

1. **JWT users**: Scopes determined by role (see Role?Scope table below)
2. **API key users**: Only scopes assigned at key creation are allowed
3. **Auth disabled**: Anonymous user gets superadmin role = all scopes

## Role ? Scope Mapping

| Role | Scopes |
|------|--------|
| `superadmin` | `*` (all) |
| `admin` | All 16 scopes (read/write/delete + admin) |
| `employee` | All non-admin scopes (read/write/delete) |
| `support` | `read:repos`, `read:snapshots`, `read:analysis`, `read:coverage`, `read:gates`, `read:export`, `admin:audit` |
| `user` | All non-admin scopes (same as employee) |

### Creating a Least-Privilege API Key

```bash
# CI pipeline key: can only read repos and trigger ingestion
curl -X POST "/auth/api-keys?name=CI&scopes=read:repos,write:snapshots"

# Read-only dashboard key
curl -X POST "/auth/api-keys?name=Dashboard&scopes=read:repos,read:analysis,read:coverage"

# Export-only key for compliance
curl -X POST "/auth/api-keys?name=Compliance&scopes=read:export"
```

---

## Enforcement Implementation

- **Router-level**: Applied to routers where all endpoints share the same scope (14 routers)
- **Per-endpoint**: Applied via `dependencies=[Depends(require_scope("..."))]` for mixed routers (8 routers)
- **`protected()` decorator**: Combines scope + role + repo ownership in one dependency
- **Mechanism**: `require_scope()` depends on `get_current_user` ? reads role or `request.state.api_key_scopes`
- **Caching**: `require_repo_access()` caches results in a 5-min TTL in-memory cache (10K entries)
- **Audit**: All 403 denials are logged to the audit trail automatically

## Resource-Level Permissions

| Level | Read | Write | Delete | Share |
|-------|------|-------|--------|-------|
| `viewer` | ? | ? | ? | ? |
| `editor` | ? | ? | ? | ? |
| `owner` | ? | ? | ? | ? |

### Endpoints

```
POST   /repos/{id}/permissions           # Grant access
GET    /repos/{id}/permissions           # List who has access
DELETE /repos/{id}/permissions/{user_id} # Revoke access
```

## Team Access

Teams provide group-based repo access:

```
POST   /teams                    # Create team
GET    /teams                    # List my teams
GET    /teams/{id}               # Team details
PATCH  /teams/{id}               # Update team
DELETE /teams/{id}               # Delete team
GET    /teams/{id}/members       # List members
POST   /teams/{id}/members       # Add member
DELETE /teams/{id}/members/{uid} # Remove member
POST   /teams/{id}/repos         # Grant team repo access
GET    /teams/{id}/repos         # List team repos
```
