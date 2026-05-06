# RBAC System Improvement Plan

> **Date**: 2026
> **Scope**: Backend RBAC (Role-Based Access Control) enhancement
> **Current State**: Roles + API key scopes exist but are not fully connected
> **Goal**: Production-grade, easy-to-use, high-quality RBAC

---

## Current State Assessment

### What We Have

| Component | Status | Quality |
|-----------|--------|---------|
| User roles | ? 5 roles (superadmin, admin, employee, support, user) | Basic |
| `require_role()` dependency | ? Works | Not applied to most endpoints |
| API key scopes | ? 17 scopes defined | Not enforced on any endpoint yet |
| `require_scope()` dependency | ? Works | Zero endpoints use it |
| Repo ownership check | ? `require_repo_access()` | Only used on some endpoints |
| Quota system | ? `require_quota()` | Functional |

### What's Missing

| Gap | Impact | Priority |
|-----|--------|----------|
| Scopes not enforced on endpoints | API keys have full access regardless of scopes | P0 |
| No role-to-scope mapping | JWT users have no scope restrictions | P0 |
| No endpoint-level permission matrix | Can't audit "who can do what" | P0 |
| No team/org model | Can't share repos between users | P1 |
| No resource-level permissions | All-or-nothing repo access | P1 |
| No permission inheritance | Admin must manually assign everything | P2 |
| No permission caching | DB hit on every request | P2 |
| No UI for role/permission management | Admin must use raw API | P2 |

---

## Execution Plan

### Phase 1: Enforce Scopes on All Endpoints (4h) ? DONE

**Goal**: Every mutation endpoint checks scopes. Read endpoints check read scopes.

#### 1.1 Apply `require_scope()` to all 104 endpoints

```python
# Example: before
@router.delete("/{repo_id}/snapshots/{sid}", status_code=204)
async def delete_snapshot(...): ...

# After
@router.delete(
    "/{repo_id}/snapshots/{sid}",
    status_code=204,
    dependencies=[Depends(require_scope("delete:snapshots"))],
)
async def delete_snapshot(...): ...
```

#### 1.2 Endpoint ? Scope mapping table

| Endpoint Pattern | Method | Required Scope |
|-----------------|--------|----------------|
| `/repos` | GET | `read:repos` |
| `/repos` | POST | `write:repos` |
| `/repos/{id}` | PATCH/DELETE | `write:repos` |
| `/repos/{id}/ingest` | POST | `write:snapshots` |
| `/repos/{id}/snapshots` | GET | `read:snapshots` |
| `/repos/{id}/snapshots/{sid}` | GET | `read:snapshots` |
| `/repos/{id}/snapshots/{sid}` | DELETE | `delete:snapshots` |
| `/repos/{id}/snapshots/{sid}/symbols` | GET | `read:analysis` |
| `/repos/{id}/snapshots/{sid}/edges` | GET | `read:analysis` |
| `/repos/{id}/snapshots/{sid}/health` | POST | `read:analysis` |
| `/repos/{id}/snapshots/{sid}/health-score` | GET | `read:analysis` |
| `/repos/{id}/snapshots/{sid}/health/findings` | POST | `write:snapshots` |
| `/repos/{id}/snapshots/{sid}/health/diff/*` | GET | `read:analysis` |
| `/repos/{id}/snapshots/{sid}/coverage` | GET | `read:coverage` |
| `/repos/{id}/snapshots/{sid}/coverage` | POST | `write:coverage` |
| `/repos/{id}/snapshots/{sid}/export/*` | GET | `read:export` |
| `/repos/{id}/quality-gates` | GET | `read:gates` |
| `/repos/{id}/quality-gates` | POST/PATCH/DELETE | `write:gates` |
| `/repos/{id}/snapshots/{sid}/evaluate-gate/*` | POST | `write:gates` |
| `/repos/{id}/snapshots/{sid}/review` | POST | `write:reviews` |
| `/repos/{id}/snapshots/{sid}/docs` | POST | `write:docs` |
| `/repos/{id}/snapshots/bulk-*` | POST | `write:snapshots` |
| `/repos/{id}/snapshots/older-than/*` | DELETE | `delete:snapshots` |
| `/repos/bulk-delete` | POST | `admin:users` |
| `/admin/audit-log` | GET | `admin:audit` |
| `/admin/audit-log/purge` | DELETE | `admin:audit` |
| `/admin/users/*` | ALL | `admin:users` |
| `/admin/plans/*` | ALL | `admin:plans` |

#### 1.3 Deliverables
- Update all 20+ router files to add `dependencies=[Depends(require_scope(...))]`
- Add integration test verifying scoped key is rejected on wrong endpoint
- Document full matrix in `docs/PERMISSIONS.md`

---

### Phase 2: Role-to-Scope Mapping (3h) ? DONE

**Goal**: JWT users also get scope restrictions based on their role.

#### 2.1 Define role ? default scopes

```python
ROLE_SCOPES: dict[str, set[str]] = {
    "superadmin": {"*"},
    "admin": {
        "read:repos", "write:repos",
        "read:snapshots", "write:snapshots", "delete:snapshots",
        "read:analysis", "read:coverage", "write:coverage",
        "read:gates", "write:gates",
        "write:reviews", "write:docs", "read:export",
        "admin:users", "admin:plans", "admin:audit",
    },
    "employee": {
        "read:repos", "write:repos",
        "read:snapshots", "write:snapshots", "delete:snapshots",
        "read:analysis", "read:coverage", "write:coverage",
        "read:gates", "write:gates",
        "write:reviews", "write:docs", "read:export",
    },
    "support": {
        "read:repos", "read:snapshots", "read:analysis",
        "read:coverage", "read:gates", "read:export",
        "admin:audit",
    },
    "user": {
        "read:repos", "write:repos",
        "read:snapshots", "write:snapshots",
        "read:analysis", "read:coverage", "write:coverage",
        "read:gates", "write:gates",
        "write:reviews", "write:docs", "read:export",
    },
}
```

#### 2.2 Update `get_current_user` to store role scopes

```python
# After JWT validation:
request.state.api_key_scopes = ",".join(ROLE_SCOPES.get(user.role, set()))
```

#### 2.3 Update `require_scope` to work for both JWT and API key

Already works — just needs request.state populated for JWT users too.

---

### Phase 3: Permission Decorator (2h) ? DONE

**Goal**: Single decorator that combines role + scope + repo access checks.

#### 3.1 Create unified `@protected` decorator

```python
def protected(
    scope: str | None = None,
    roles: list[str] | None = None,
    require_repo_owner: bool = False,
):
    """Unified permission decorator.

    Usage:
        @router.delete(
            "/{repo_id}/snapshots/{sid}",
            dependencies=[Depends(protected(
                scope="delete:snapshots",
                roles=["admin", "employee", "user"],
                require_repo_owner=True,
            ))],
        )
    """
```

This eliminates the need to stack multiple `Depends(...)` calls.

---

### Phase 4: Resource-Level Permissions (6h) ? DONE

**Goal**: Share repos with specific users with specific access levels.

#### 4.1 New model: `RepoPermission`

```python
class RepoPermission(Base):
    __tablename__ = "repo_permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str]  # "owner", "editor", "viewer"
    granted_by: Mapped[str | None]
    granted_at: Mapped[datetime]

    __table_args__ = (
        UniqueConstraint("repo_id", "user_id"),
        Index("ix_repo_perm_user", "user_id"),
    )
```

#### 4.2 Permission levels

| Level | Can Read | Can Write | Can Delete | Can Share |
|-------|----------|-----------|------------|-----------|
| viewer | ? | ? | ? | ? |
| editor | ? | ? | ? | ? |
| owner | ? | ? | ? | ? |

#### 4.3 New endpoints

```
POST   /repos/{id}/permissions          # Grant access
GET    /repos/{id}/permissions          # List who has access
DELETE /repos/{id}/permissions/{user_id} # Revoke access
```

#### 4.4 Update `require_repo_access()`

Check `RepoPermission` table in addition to ownership.

---

### Phase 5: Team / Organization Model (6h) ? DONE

**Goal**: Group users into teams, assign team-level repo access.

#### 5.1 New models

```python
class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str]
    created_by: Mapped[str]

class TeamMember(Base):
    __tablename__ = "team_members"
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str]  # "admin", "member"

class TeamRepoAccess(Base):
    __tablename__ = "team_repo_access"
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id"))
    permission: Mapped[str]  # "viewer", "editor", "owner"
```

#### 5.2 New endpoints (8)

```
POST   /teams                         # Create team
GET    /teams                         # List my teams
GET    /teams/{id}                    # Team details
PATCH  /teams/{id}                    # Update team
DELETE /teams/{id}                    # Delete team
POST   /teams/{id}/members            # Add member
DELETE /teams/{id}/members/{user_id}  # Remove member
POST   /teams/{id}/repos              # Grant team repo access
```

---

### Phase 6: Permission Caching (3h) ? DONE

**Goal**: Avoid DB hit on every request for permission checks.

#### 6.1 In-memory TTL cache

```python
from functools import lru_cache
from cachetools import TTLCache

_perm_cache = TTLCache(maxsize=10000, ttl=300)  # 5 min TTL

async def get_user_permissions(user_id: str, db) -> set[str]:
    if user_id in _perm_cache:
        return _perm_cache[user_id]
    # ... compute from DB
    _perm_cache[user_id] = perms
    return perms
```

#### 6.2 Cache invalidation

Invalidate on:
- Role change (`PUT /admin/users/{id}/role`)
- Permission grant/revoke
- Team membership change
- API key scope update

---

### Phase 7: Audit Integration (2h) ? DONE

**Goal**: All permission denials are logged to audit trail.

#### 7.1 Log 403 responses

```python
async def _check(request: Request) -> None:
    ...
    if not has_scope(granted, scope):
        await record_audit_event(db, action="permission.denied", ...)
        raise HTTPException(403, ...)
```

#### 7.2 Permission change audit

Log all:
- `permission.granted` — who gave what to whom
- `permission.revoked` — who removed what
- `role.changed` — who changed whose role

---

### Phase 8: Documentation & Developer Experience (3h)

#### 8.1 Create `docs/PERMISSIONS.md`

Full reference:
- Complete endpoint ? scope matrix
- Role ? scope mapping table
- How to create a least-privilege API key
- Team-based access patterns

#### 8.2 Create `docs/AUTHENTICATION.md`

- JWT flow (GitHub, Google)
- API key creation with scopes
- Token refresh strategy
- Security best practices

#### 8.3 OpenAPI security schemes

Add proper security annotations to all endpoints so Swagger UI shows lock icons and required scopes.

```python
from fastapi.security import SecurityScopes

# In OpenAPI docs, each endpoint shows required scopes
```

---

## Implementation Order

```
Week 1 (12h):
  Day 1: Phase 1 — Enforce scopes on all endpoints (4h)
  Day 2: Phase 2 — Role-to-scope mapping (3h)
  Day 3: Phase 3 — Unified decorator (2h) + Phase 7 — Audit (2h)

Week 2 (15h):
  Day 1: Phase 4 — Resource-level permissions (6h)
  Day 2: Phase 5 — Team/org model (6h)
  Day 3: Phase 6 — Caching (3h) + Phase 8 — Docs (3h)
```

**Total: ~27 hours = 3.4 working days**

---

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Endpoints with scope enforcement | 0 | 104 |
| Role-to-scope mapping | None | 5 roles mapped |
| Resource-level sharing | None | viewer/editor/owner |
| Team support | None | Full CRUD + access |
| Permission audit trail | None | All denials + changes logged |
| Permission cache | None | 5-min TTL, <1ms lookups |
| Documentation | Minimal | Full matrix + guides |
| New endpoints | 0 | ~11 (permissions + teams) |
| New tests | 0 | ~60 |

---

## Design Principles

1. **Least privilege by default** — new API keys get minimal scopes, not `*`
2. **Fail closed** — if permission check fails, deny access (never allow)
3. **Backward compatible** — existing keys with `scopes="*"` keep working
4. **Auditable** — every denial and grant is logged
5. **Fast** — cache permissions, don't hit DB on every request
6. **Simple mental model** — role = what you CAN do, scope = what key is ALLOWED to do
7. **No external services** — pure Python, in-process cache (no Redis needed)

---

## Security Considerations

| Risk | Mitigation |
|------|-----------|
| Cache staleness after role change | Invalidate immediately + 5-min TTL max |
| Privilege escalation via API key | Key scopes ? user's role scopes (enforced at creation) |
| Team admin granting themselves owner | Team admin ? repo owner (separate concerns) |
| Token replay | Short JWT TTL (15 min) + refresh tokens |
| Scope confusion | Clear naming (`read:X`, `write:X`, `delete:X`, `admin:X`) |

---

## Quick Wins (Do First)

If time is limited, these 3 changes give 80% of the value:

1. **Apply `require_scope()` to all DELETE + POST endpoints** (2h) — blocks misconfigured API keys
2. **Add role-to-scope mapping** (1h) — restricts `support` role from mutations
3. **Log all 403s to audit** (30min) — instant visibility into access issues

---

*Document created as RBAC improvement plan — pure backend, no external services.*
