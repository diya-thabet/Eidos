"""
API key scope definitions and enforcement.

Scopes control what an API key can do. Each endpoint can declare
required scopes via `require_scope("read:analysis")`.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

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

    If the request came via JWT (not API key), all scopes are granted.
    If via API key, check the key's scopes.

    Usage:
        @router.delete(
            "/{repo_id}/snapshots/{sid}",
            dependencies=[Depends(require_scope("delete:snapshots"))],
        )
    """

    async def _check(request: Request) -> None:
        # If no scopes are set on request (JWT auth), allow everything
        granted_str = getattr(request.state, "api_key_scopes", None)
        if granted_str is None:
            return  # JWT users have full access

        granted = parse_scopes(granted_str)
        if not has_scope(granted, scope):
            raise HTTPException(
                status_code=403,
                detail=f"API key missing required scope: {scope}",
            )

    return _check
