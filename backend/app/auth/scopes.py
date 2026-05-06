"""
API key scope definitions and enforcement.

Scopes control what an API key can do. Each endpoint can declare
required scopes via `require_scope("read:analysis")`.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request

# ---------------------------------------------------------------------------
# Scope catalog
# ---------------------------------------------------------------------------

SCOPES: dict[str, str] = {
    "read:repos": "List and view repos",
    "write:repos": "Create, update, delete repos",
    "read:snapshots": "List and view snapshots",
    "write:snapshots": "Create snapshots (ingest)",
    "delete:snapshots": "Delete snapshots",
    "read:analysis": "View symbols, edges, health, graphs",
    "read:coverage": "View coverage reports",
    "write:coverage": "Upload coverage reports",
    "read:gates": "View quality gates",
    "write:gates": "Create, update, delete quality gates",
    "write:reviews": "Submit PR reviews",
    "write:docs": "Generate documentation",
    "read:export": "Download exports (JSON, CSV, SARIF, SBOM)",
    "admin:users": "Manage users and roles",
    "admin:plans": "Manage subscription plans",
    "admin:audit": "View and manage audit log",
    "*": "Full access (all scopes)",
}

# ---------------------------------------------------------------------------
# Role-to-Scope mapping
# ---------------------------------------------------------------------------

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
        "read:snapshots", "write:snapshots", "delete:snapshots",
        "read:analysis", "read:coverage", "write:coverage",
        "read:gates", "write:gates",
        "write:reviews", "write:docs", "read:export",
    },
}


def get_role_scopes(role: str) -> str:
    """Get comma-separated scopes for a role."""
    scopes = ROLE_SCOPES.get(role, ROLE_SCOPES["user"])
    if "*" in scopes:
        return "*"
    return ",".join(sorted(scopes))


def parse_scopes(scopes_str: str | None) -> set[str]:
    """Parse a comma-separated scopes string into a set."""
    if not scopes_str or scopes_str.strip() == "*":
        return {"*"}
    return {s.strip() for s in scopes_str.split(",") if s.strip()}


def has_scope(granted: set[str], required: str) -> bool:
    """Check if the granted scopes include the required scope."""
    if "*" in granted:
        return True
    return required in granted


def validate_scopes(scopes: list[str]) -> list[str]:
    """Validate that all scopes are recognized. Returns invalid ones."""
    return [s for s in scopes if s not in SCOPES]


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def require_scope(scope: str) -> Any:
    """FastAPI dependency that enforces a scope on the current request.

    For API key auth: checks the key's assigned scopes.
    For JWT auth: checks the user's role-based scopes.
    Superadmins and anonymous (auth disabled) bypass all checks.

    Usage:
        @router.delete(
            "/{repo_id}/snapshots/{sid}",
            dependencies=[Depends(require_scope("delete:snapshots"))],
        )
    """
    from app.auth.dependencies import get_current_user
    from app.storage.models import User

    async def _check(
        request: Request,
        _user: Any = Depends(get_current_user),
    ) -> None:
        # Determine granted scopes
        granted_str = getattr(request.state, "api_key_scopes", None)

        if granted_str is None:
            # JWT user — apply role-based scopes
            if isinstance(_user, User) and hasattr(_user, "role"):
                granted_str = get_role_scopes(_user.role)
            else:
                return  # Unknown user type, allow (safety fallback)

        granted = parse_scopes(granted_str)
        if not has_scope(granted, scope):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions: requires scope '{scope}'",
            )

    return _check


# ---------------------------------------------------------------------------
# Unified permission decorator
# ---------------------------------------------------------------------------


def protected(
    scope: str | None = None,
    roles: list[str] | None = None,
    require_repo_owner: bool = False,
) -> Any:
    """Unified permission dependency combining scope, role, and repo ownership.

    Combines three checks in one dependency:
    1. Scope check (role-based for JWT, key-based for API keys)
    2. Role whitelist (optional — only allow specific roles)
    3. Repo ownership (optional — verify user owns the repo)

    Usage:
        @router.delete(
            "/{repo_id}/snapshots/{sid}",
            dependencies=[Depends(protected(
                scope="delete:snapshots",
                roles=["admin", "employee", "user"],
                require_repo_owner=True,
            ))],
        )

    Args:
        scope: Required scope string (e.g. "write:repos"). None = no scope check.
        roles: Allowed roles. None = all roles allowed (scope still checked).
        require_repo_owner: If True, verify user owns the repo (repo_id path param).
    """
    from app.auth.dependencies import get_current_user
    from app.storage.database import get_db
    from app.storage.models import User

    async def _check(
        request: Request,
        _user: Any = Depends(get_current_user),
        _db: Any = Depends(get_db),
    ) -> None:
        # 1. Role whitelist check
        if roles is not None:
            user_role = getattr(_user, "role", "user")
            if user_role not in roles and user_role != "superadmin":
                raise HTTPException(
                    status_code=403,
                    detail="Insufficient role permissions",
                )

        # 2. Scope check
        if scope is not None:
            granted_str = getattr(request.state, "api_key_scopes", None)
            if granted_str is None:
                if isinstance(_user, User) and hasattr(_user, "role"):
                    granted_str = get_role_scopes(_user.role)
                else:
                    granted_str = "*"

            granted = parse_scopes(granted_str)
            if not has_scope(granted, scope):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions: requires scope '{scope}'",
                )

        # 3. Repo ownership check
        if require_repo_owner:
            from app.core.config import settings as app_settings

            if not app_settings.auth_enabled:
                return

            user_role = getattr(_user, "role", "user")
            # Admins+ bypass ownership check
            if user_role in ("superadmin", "admin"):
                return

            # Extract repo_id from path params
            repo_id = request.path_params.get("repo_id")
            if repo_id:
                from sqlalchemy import select

                from app.storage.models import Repo

                result = await _db.execute(
                    select(Repo).where(
                        Repo.id == repo_id,
                        Repo.owner_id == _user.id,
                    )
                )
                if result.scalar_one_or_none() is None:
                    raise HTTPException(
                        status_code=404, detail="Repo not found",
                    )

    return _check
