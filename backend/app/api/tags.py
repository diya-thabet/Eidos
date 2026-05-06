"""API endpoints for snapshot tagging and search."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_db
from app.storage.models import RepoSnapshot, SnapshotTag

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TagCreate(BaseModel):
    tag: str


class TagOut(BaseModel):
    id: int
    snapshot_id: str
    tag: str
    created_by: str | None
    created_at: str


class TagStatsOut(BaseModel):
    tag: str
    count: int


class SnapshotWithTagsOut(BaseModel):
    id: str
    repo_id: str
    commit_sha: str
    status: str
    file_count: int
    created_at: str
    tags: list[str]


# ---------------------------------------------------------------------------
# Add tag
# ---------------------------------------------------------------------------


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/tags",
    response_model=TagOut,
    status_code=201,
    summary="Add a tag to a snapshot",
)
async def add_tag(
    repo_id: str,
    snapshot_id: str,
    body: TagCreate,
    db: AsyncSession = Depends(get_db),
) -> TagOut:
    """Add a tag to a snapshot. Duplicate tags are rejected (409)."""
    snapshot = await db.get(RepoSnapshot, snapshot_id)
    if snapshot is None or snapshot.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    tag_str = body.tag.strip().lower()
    if not tag_str or len(tag_str) > 128:
        raise HTTPException(status_code=400, detail="Tag must be 1-128 characters")

    # Check duplicate
    existing = await db.execute(
        select(SnapshotTag).where(
            SnapshotTag.snapshot_id == snapshot_id,
            SnapshotTag.tag == tag_str,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Tag already exists")

    tag_obj = SnapshotTag(snapshot_id=snapshot_id, tag=tag_str)
    db.add(tag_obj)
    await db.commit()
    await db.refresh(tag_obj)

    return TagOut(
        id=tag_obj.id,
        snapshot_id=tag_obj.snapshot_id,
        tag=tag_obj.tag,
        created_by=tag_obj.created_by,
        created_at=tag_obj.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Remove tag
# ---------------------------------------------------------------------------


@router.delete(
    "/{repo_id}/snapshots/{snapshot_id}/tags/{tag}",
    status_code=204,
    summary="Remove a tag from a snapshot",
)
async def remove_tag(
    repo_id: str,
    snapshot_id: str,
    tag: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a specific tag from a snapshot."""
    result = await db.execute(
        select(SnapshotTag).where(
            SnapshotTag.snapshot_id == snapshot_id,
            SnapshotTag.tag == tag.strip().lower(),
        )
    )
    tag_obj = result.scalar_one_or_none()
    if tag_obj is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag_obj)
    await db.commit()


# ---------------------------------------------------------------------------
# List tags for a snapshot
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/tags",
    response_model=list[TagOut],
    summary="List tags for a snapshot",
)
async def list_snapshot_tags(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[TagOut]:
    """List all tags for a specific snapshot."""
    snapshot = await db.get(RepoSnapshot, snapshot_id)
    if snapshot is None or snapshot.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    result = await db.execute(
        select(SnapshotTag)
        .where(SnapshotTag.snapshot_id == snapshot_id)
        .order_by(SnapshotTag.tag)
    )
    return [
        TagOut(
            id=t.id,
            snapshot_id=t.snapshot_id,
            tag=t.tag,
            created_by=t.created_by,
            created_at=t.created_at.isoformat(),
        )
        for t in result.scalars().all()
    ]


# ---------------------------------------------------------------------------
# Find snapshots by tag
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/by-tag/{tag}",
    response_model=list[SnapshotWithTagsOut],
    summary="Find snapshots by tag",
)
async def find_snapshots_by_tag(
    repo_id: str,
    tag: str,
    db: AsyncSession = Depends(get_db),
) -> list[SnapshotWithTagsOut]:
    """Find all snapshots in a repo that have a specific tag."""
    result = await db.execute(
        select(RepoSnapshot)
        .join(SnapshotTag, SnapshotTag.snapshot_id == RepoSnapshot.id)
        .where(
            RepoSnapshot.repo_id == repo_id,
            SnapshotTag.tag == tag.strip().lower(),
        )
        .order_by(RepoSnapshot.created_at.desc())
    )
    snapshots = result.scalars().all()

    out: list[SnapshotWithTagsOut] = []
    for s in snapshots:
        tags_result = await db.execute(
            select(SnapshotTag.tag).where(SnapshotTag.snapshot_id == s.id)
        )
        tags = [row[0] for row in tags_result.all()]
        out.append(SnapshotWithTagsOut(
            id=s.id,
            repo_id=s.repo_id,
            commit_sha=s.commit_sha or "",
            status=s.status.value if hasattr(s.status, "value") else str(s.status),
            file_count=s.file_count or 0,
            created_at=s.created_at.isoformat(),
            tags=tags,
        ))
    return out


# ---------------------------------------------------------------------------
# Global tag stats
# ---------------------------------------------------------------------------


@router.get(
    "/tags/stats",
    response_model=list[TagStatsOut],
    summary="Global tag usage statistics",
)
async def tag_stats(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[TagStatsOut]:
    """Return tag usage counts across all snapshots, sorted by most used."""
    result = await db.execute(
        select(SnapshotTag.tag, func.count(SnapshotTag.id))
        .group_by(SnapshotTag.tag)
        .order_by(func.count(SnapshotTag.id).desc())
        .limit(limit)
    )
    return [TagStatsOut(tag=row[0], count=row[1]) for row in result.all()]
