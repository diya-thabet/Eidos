"""
API endpoints for summaries and semantic retrieval.

Provides access to persisted summaries (symbol, module, file level)
and vector-based similarity search.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_db
from app.storage.models import RepoSnapshot, Summary
from app.storage.schemas import PaginatedResponse, SummaryOut

router = APIRouter()


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/summaries",
    response_model=PaginatedResponse,
    summary="List summaries for a snapshot",
)
async def list_summaries(
    repo_id: str,
    snapshot_id: str,
    scope_type: str | None = Query(None, description="Filter: symbol, module, or file"),
    scope_id: str | None = Query(
        None, description="Filter by scope ID (fq_name, module name, path)"
    ),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Any:
    await _verify_snapshot(db, repo_id, snapshot_id)

    base = select(Summary).where(Summary.snapshot_id == snapshot_id)
    if scope_type:
        base = base.where(Summary.scope_type == scope_type)
    if scope_id:
        base = base.where(Summary.scope_id == scope_id)

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    stmt = base.order_by(Summary.scope_type, Summary.scope_id).offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    items = [
        SummaryOut(
            id=row.id,
            snapshot_id=row.snapshot_id,
            scope_type=row.scope_type,
            scope_id=row.scope_id,
            summary=json.loads(row.summary_json),
            created_at=row.created_at.isoformat() if row.created_at else "",
        )
        for row in rows
    ]
    return PaginatedResponse(
        items=items, total=total, limit=limit, offset=offset, has_more=(offset + limit < total)
    )


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/summaries/{scope_type}/{scope_id:path}",
    response_model=SummaryOut,
    summary="Get a specific summary",
)
async def get_summary(
    repo_id: str,
    snapshot_id: str,
    scope_type: str,
    scope_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    await _verify_snapshot(db, repo_id, snapshot_id)

    result = await db.execute(
        select(Summary).where(
            Summary.snapshot_id == snapshot_id,
            Summary.scope_type == scope_type,
            Summary.scope_id == scope_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Summary not found: {scope_type}/{scope_id}")

    return SummaryOut(
        id=row.id,
        snapshot_id=row.snapshot_id,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        summary=json.loads(row.summary_json),
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _verify_snapshot(db: AsyncSession, repo_id: str, snapshot_id: str) -> RepoSnapshot:
    """Verify snapshot exists and belongs to the repo."""
    result = await db.execute(
        select(RepoSnapshot).where(
            RepoSnapshot.id == snapshot_id,
            RepoSnapshot.repo_id == repo_id,
        )
    )
    snap = result.scalar_one_or_none()
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snap
