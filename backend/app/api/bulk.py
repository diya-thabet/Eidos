"""API endpoints for bulk operations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotTag

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BulkDeleteSnapshotsRequest(BaseModel):
    snapshot_ids: list[str]


class BulkDeleteResult(BaseModel):
    deleted: int
    failed: list[str]


class BulkTagRequest(BaseModel):
    snapshot_ids: list[str]
    tag: str


class BulkTagResult(BaseModel):
    tagged: int
    skipped: int


class OlderThanResult(BaseModel):
    deleted_count: int
    remaining_count: int


class BulkDeleteReposRequest(BaseModel):
    repo_ids: list[str]


# ---------------------------------------------------------------------------
# Bulk delete snapshots
# ---------------------------------------------------------------------------


@router.post(
    "/{repo_id}/snapshots/bulk-delete",
    response_model=BulkDeleteResult,
    summary="Bulk delete snapshots",
)
async def bulk_delete_snapshots(
    repo_id: str,
    body: BulkDeleteSnapshotsRequest,
    db: AsyncSession = Depends(get_db),
) -> BulkDeleteResult:
    """Delete multiple snapshots at once. Maximum 100 per request."""
    if len(body.snapshot_ids) > 100:
        raise HTTPException(
            status_code=400, detail="Maximum 100 snapshots per request",
        )

    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    deleted = 0
    failed: list[str] = []

    for sid in body.snapshot_ids:
        snapshot = await db.get(RepoSnapshot, sid)
        if snapshot is None or snapshot.repo_id != repo_id:
            failed.append(sid)
            continue
        await db.delete(snapshot)
        deleted += 1

    await db.commit()
    return BulkDeleteResult(deleted=deleted, failed=failed)


# ---------------------------------------------------------------------------
# Bulk tag snapshots
# ---------------------------------------------------------------------------


@router.post(
    "/{repo_id}/snapshots/bulk-tag",
    response_model=BulkTagResult,
    summary="Add a tag to multiple snapshots",
)
async def bulk_tag_snapshots(
    repo_id: str,
    body: BulkTagRequest,
    db: AsyncSession = Depends(get_db),
) -> BulkTagResult:
    """Add the same tag to multiple snapshots. Skips duplicates."""
    if len(body.snapshot_ids) > 100:
        raise HTTPException(
            status_code=400, detail="Maximum 100 snapshots per request",
        )

    tag = body.tag.strip().lower()
    if not tag:
        raise HTTPException(status_code=400, detail="Tag must not be empty")

    tagged = 0
    skipped = 0

    for sid in body.snapshot_ids:
        snapshot = await db.get(RepoSnapshot, sid)
        if snapshot is None or snapshot.repo_id != repo_id:
            skipped += 1
            continue

        # Check existing
        existing = await db.execute(
            select(SnapshotTag).where(
                SnapshotTag.snapshot_id == sid,
                SnapshotTag.tag == tag,
            )
        )
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue

        db.add(SnapshotTag(snapshot_id=sid, tag=tag))
        tagged += 1

    await db.commit()
    return BulkTagResult(tagged=tagged, skipped=skipped)


# ---------------------------------------------------------------------------
# Delete snapshots older than N days
# ---------------------------------------------------------------------------


@router.delete(
    "/{repo_id}/snapshots/older-than/{days}",
    response_model=OlderThanResult,
    summary="Delete snapshots older than N days",
)
async def delete_older_than(
    repo_id: str,
    days: int,
    db: AsyncSession = Depends(get_db),
) -> OlderThanResult:
    """Delete all snapshots older than N days for a repo."""
    if days < 1:
        raise HTTPException(status_code=400, detail="Days must be >= 1")

    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    cutoff = datetime.now(UTC) - timedelta(days=days)

    # Find old snapshots
    result = await db.execute(
        select(RepoSnapshot).where(
            RepoSnapshot.repo_id == repo_id,
            RepoSnapshot.created_at < cutoff,
        )
    )
    old_snapshots = result.scalars().all()
    deleted_count = len(old_snapshots)

    for s in old_snapshots:
        await db.delete(s)

    # Count remaining
    remaining_count_result = await db.execute(
        select(func.count(RepoSnapshot.id)).where(
            RepoSnapshot.repo_id == repo_id,
            RepoSnapshot.created_at >= cutoff,
        )
    )
    remaining_count = remaining_count_result.scalar() or 0

    await db.commit()
    return OlderThanResult(
        deleted_count=deleted_count, remaining_count=remaining_count,
    )


# ---------------------------------------------------------------------------
# Bulk delete repos (admin)
# ---------------------------------------------------------------------------


@router.post(
    "/bulk-delete",
    response_model=BulkDeleteResult,
    summary="Bulk delete repos (admin)",
)
async def bulk_delete_repos(
    body: BulkDeleteReposRequest,
    db: AsyncSession = Depends(get_db),
) -> BulkDeleteResult:
    """Delete multiple repos. Maximum 50 per request."""
    if len(body.repo_ids) > 50:
        raise HTTPException(
            status_code=400, detail="Maximum 50 repos per request",
        )

    deleted = 0
    failed: list[str] = []

    for rid in body.repo_ids:
        repo = await db.get(Repo, rid)
        if repo is None:
            failed.append(rid)
            continue
        await db.delete(repo)
        deleted += 1

    await db.commit()
    return BulkDeleteResult(deleted=deleted, failed=failed)
