"""API endpoints for querying and exporting the audit log."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.scopes import require_scope
from app.storage.database import get_db
from app.storage.models import AuditEvent

router = APIRouter(dependencies=[Depends(require_scope("admin:audit"))])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AuditEventOut(BaseModel):
    id: int
    timestamp: str
    user_id: str | None
    user_email: str
    action: str
    resource_type: str
    resource_id: str
    method: str
    path: str
    status_code: int
    ip_address: str
    success: bool
    metadata: dict[str, Any]


class AuditLogResponse(BaseModel):
    total: int
    offset: int
    limit: int
    events: list[AuditEventOut]


class AuditStatsOut(BaseModel):
    total_events: int
    unique_users: int
    actions: dict[str, int]
    recent_failures: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_to_out(event: AuditEvent) -> AuditEventOut:
    try:
        meta = json.loads(event.metadata_json or "{}")
    except (json.JSONDecodeError, TypeError):
        meta = {}
    return AuditEventOut(
        id=event.id,
        timestamp=event.timestamp.isoformat(),
        user_id=event.user_id,
        user_email=event.user_email,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        method=event.method,
        path=event.path,
        status_code=event.status_code,
        ip_address=event.ip_address,
        success=event.success,
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# Query endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/admin/audit-log",
    response_model=AuditLogResponse,
    summary="Query audit events (admin)",
)
async def query_audit_log(
    user_id: str | None = Query(None, description="Filter by user ID"),
    action: str | None = Query(None, description="Filter by action"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    resource_id: str | None = Query(None, description="Filter by resource ID"),
    success: bool | None = Query(None, description="Filter by success status"),
    method: str | None = Query(None, description="Filter by HTTP method"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AuditLogResponse:
    """Query audit events with filters. Newest first."""
    conditions = []
    if user_id is not None:
        conditions.append(AuditEvent.user_id == user_id)
    if action is not None:
        conditions.append(AuditEvent.action == action)
    if resource_type is not None:
        conditions.append(AuditEvent.resource_type == resource_type)
    if resource_id is not None:
        conditions.append(AuditEvent.resource_id == resource_id)
    if success is not None:
        conditions.append(AuditEvent.success == success)
    if method is not None:
        conditions.append(AuditEvent.method == method.upper())

    # Count
    count_stmt = select(func.count(AuditEvent.id))
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Fetch
    stmt = (
        select(AuditEvent)
        .order_by(AuditEvent.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    if conditions:
        stmt = stmt.where(and_(*conditions))
    result = await db.execute(stmt)
    events = [_event_to_out(e) for e in result.scalars().all()]

    return AuditLogResponse(
        total=total, offset=offset, limit=limit, events=events,
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.get(
    "/admin/audit-log/export",
    summary="Export audit log as CSV",
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_audit_log(
    user_id: str | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export audit events as CSV for compliance reporting."""
    conditions = []
    if user_id:
        conditions.append(AuditEvent.user_id == user_id)
    if action:
        conditions.append(AuditEvent.action == action)
    if resource_type:
        conditions.append(AuditEvent.resource_type == resource_type)

    stmt = (
        select(AuditEvent)
        .order_by(AuditEvent.timestamp.desc())
        .limit(limit)
    )
    if conditions:
        stmt = stmt.where(and_(*conditions))
    result = await db.execute(stmt)
    events = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "timestamp", "user_id", "user_email", "action",
        "resource_type", "resource_id", "method", "path",
        "status_code", "ip_address", "success",
    ])
    for e in events:
        writer.writerow([
            e.id, e.timestamp.isoformat(), e.user_id or "",
            e.user_email, e.action, e.resource_type, e.resource_id,
            e.method, e.path, e.status_code, e.ip_address, e.success,
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get(
    "/admin/audit-log/stats",
    response_model=AuditStatsOut,
    summary="Audit log statistics",
)
async def audit_stats(
    db: AsyncSession = Depends(get_db),
) -> AuditStatsOut:
    """Get audit log statistics."""
    total_result = await db.execute(select(func.count(AuditEvent.id)))
    total = total_result.scalar() or 0

    users_result = await db.execute(
        select(func.count(func.distinct(AuditEvent.user_id)))
    )
    unique_users = users_result.scalar() or 0

    failures_result = await db.execute(
        select(func.count(AuditEvent.id)).where(AuditEvent.success.is_(False))
    )
    recent_failures = failures_result.scalar() or 0

    # Top actions
    actions_result = await db.execute(
        select(AuditEvent.action, func.count(AuditEvent.id))
        .group_by(AuditEvent.action)
        .order_by(func.count(AuditEvent.id).desc())
        .limit(20)
    )
    actions = {row[0]: row[1] for row in actions_result.all()}

    return AuditStatsOut(
        total_events=total,
        unique_users=unique_users,
        actions=actions,
        recent_failures=recent_failures,
    )


# ---------------------------------------------------------------------------
# Purge (retention management)
# ---------------------------------------------------------------------------


@router.delete(
    "/admin/audit-log/purge",
    status_code=200,
    summary="Purge old audit events",
)
async def purge_audit_log(
    older_than_days: int = Query(90, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Delete audit events older than N days."""
    from datetime import datetime as dt
    from datetime import timedelta
    cutoff = dt.now(tz=None) - timedelta(days=older_than_days)

    # Count first
    count_result = await db.execute(
        select(func.count(AuditEvent.id)).where(
            AuditEvent.timestamp < cutoff,
        )
    )
    count = count_result.scalar() or 0

    if count > 0:
        from sqlalchemy import delete
        await db.execute(
            delete(AuditEvent).where(AuditEvent.timestamp < cutoff)
        )
        await db.commit()

    return {"purged": count, "older_than_days": older_than_days}
