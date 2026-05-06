"""
Audit logging middleware and helpers.

Records all mutation requests (POST, PUT, PATCH, DELETE) to the audit_events table.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import AuditEvent

# Routes that are too noisy or sensitive to audit
_SKIP_PATHS = {
    "/health",
    "/health/ready",
    "/metrics",
    "/docs",
    "/openapi.json",
}

# Map path patterns to (action, resource_type, resource_id_group)
_PATH_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"^/repos/([^/]+)/snapshots/([^/]+)/evaluate-gate/"), "gate.evaluate", "snapshot"),
    (re.compile(r"^/repos/([^/]+)/snapshots/([^/]+)/coverage"), "coverage", "snapshot"),
    (re.compile(r"^/repos/([^/]+)/snapshots/([^/]+)"), "snapshot", "snapshot"),
    (re.compile(r"^/repos/([^/]+)/quality-gates/([^/]+)"), "gate", "gate"),
    (re.compile(r"^/repos/([^/]+)/quality-gates"), "gate.create", "repo"),
    (re.compile(r"^/repos/([^/]+)/ingest"), "repo.ingest", "repo"),
    (re.compile(r"^/repos/([^/]+)"), "repo", "repo"),
    (re.compile(r"^/repos$"), "repo.create", "repo"),
    (re.compile(r"^/auth/api-keys/([^/]+)"), "api_key", "api_key"),
    (re.compile(r"^/auth/api-keys"), "api_key.create", "api_key"),
    (re.compile(r"^/auth/logout"), "auth.logout", "user"),
    (re.compile(r"^/admin/users/([^/]+)"), "admin.user", "user"),
    (re.compile(r"^/admin/plans/([^/]+)"), "admin.plan", "plan"),
    (re.compile(r"^/admin/plans"), "admin.plan.create", "plan"),
    (re.compile(r"^/webhooks/"), "webhook", "webhook"),
]


def _classify_request(method: str, path: str) -> tuple[str, str, str]:
    """Classify a request into (action, resource_type, resource_id)."""
    for pattern, base_action, resource_type in _PATH_PATTERNS:
        match = pattern.search(path)
        if match:
            # Build action from method
            if base_action.endswith(".create"):
                action = base_action
            elif method == "POST":
                action = f"{base_action}.create"
            elif method == "DELETE":
                action = f"{base_action}.delete"
            elif method == "PATCH" or method == "PUT":
                action = f"{base_action}.update"
            else:
                action = base_action

            # Extract resource_id from path groups
            groups = match.groups()
            resource_id = groups[-1] if groups else ""
            return action, resource_type, resource_id

    return f"unknown.{method.lower()}", "unknown", ""


async def record_audit_event(
    db: AsyncSession,
    *,
    request: Request | None = None,
    user_id: str | None = None,
    user_email: str = "",
    action: str = "",
    resource_type: str = "",
    resource_id: str = "",
    method: str = "",
    path: str = "",
    status_code: int = 200,
    ip_address: str = "",
    user_agent: str = "",
    metadata: dict[str, Any] | None = None,
    success: bool = True,
) -> AuditEvent:
    """Record an audit event to the database."""
    if request is not None:
        method = method or request.method
        path = path or str(request.url.path)
        ip_address = ip_address or (request.client.host if request.client else "")
        user_agent = user_agent or request.headers.get("user-agent", "")[:500]

        # Try to get user from request state
        if user_id is None and hasattr(request.state, "user"):
            user = request.state.user
            if user:
                user_id = getattr(user, "id", None)
                user_email = user_email or getattr(user, "email", "") or ""

    if not action:
        action, resource_type, resource_id = _classify_request(method, path)

    event = AuditEvent(
        user_id=user_id,
        user_email=user_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        method=method,
        path=path,
        status_code=status_code,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata_json=json.dumps(metadata or {}),
        success=success,
    )
    db.add(event)
    await db.flush()
    return event


def should_audit(method: str, path: str) -> bool:
    """Determine if a request should be audited."""
    if method in ("GET", "HEAD", "OPTIONS"):
        return False
    if path in _SKIP_PATHS:
        return False
    return True
