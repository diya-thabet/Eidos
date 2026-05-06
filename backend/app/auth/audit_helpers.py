"""
Audit logging helpers for permission events.

Provides fire-and-forget audit logging for permission denials,
grants, and revocations without blocking the request.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from app.storage.models import AuditEvent


def build_permission_denied_event(
    request: Request,
    user_id: str | None,
    reason: str,
    scope: str | None = None,
) -> AuditEvent:
    """Build an audit event for a permission denial (403)."""
    metadata = {"reason": reason}
    if scope:
        metadata["required_scope"] = scope

    return AuditEvent(
        user_id=user_id,
        user_email="",
        action="permission.denied",
        resource_type="endpoint",
        resource_id=request.url.path,
        method=request.method,
        path=str(request.url),
        status_code=403,
        ip_address=request.client.host if request.client else "",
        metadata_json=json.dumps(metadata),
        success=False,
    )


def build_permission_change_event(
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Build an audit event for permission grant/revoke/role change."""
    return AuditEvent(
        user_id=user_id,
        user_email="",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        method="POST",
        path="",
        status_code=200,
        ip_address="",
        metadata_json=json.dumps(metadata or {}),
        success=True,
    )
