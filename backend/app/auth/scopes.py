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
