"""
Shared API dependencies.

Reusable FastAPI dependencies for common operations like
snapshot verification and repo access checks.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_db
from app.storage.models import RepoSnapshot


async def verify_snapshot(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
) -> RepoSnapshot:
    """
    FastAPI dependency that verifies a snapshot exists and belongs to the repo.

    Raises 404 if not found.  Returns the snapshot ORM object.
    """
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
