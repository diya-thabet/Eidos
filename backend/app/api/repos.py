from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.core.tasks import run_ingestion
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotStatus, User
from app.storage.schemas import (
    FileOut,
    IngestOut,
    IngestRequest,
    RepoCreate,
    RepoOut,
    RepoStatus,
    SnapshotDetail,
    SnapshotOut,
)

router = APIRouter()


@router.post("", response_model=RepoOut, status_code=201)
async def create_repo(
    body: RepoCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    repo = Repo(
        id=uuid.uuid4().hex[:12],
        owner_id=user.id if user.id != "anonymous" else None,
        name=body.name,
        url=str(body.url),
        default_branch=body.default_branch,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return RepoOut(
        id=repo.id,
        name=repo.name,
        url=repo.url,
        default_branch=repo.default_branch,
        created_at=repo.created_at.isoformat(),
        last_indexed_at=repo.last_indexed_at.isoformat() if repo.last_indexed_at else None,
    )


@router.post("/{repo_id}/ingest", response_model=IngestOut, status_code=202)
async def ingest_repo(
    repo_id: str,
    background: BackgroundTasks,
    body: IngestRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    snapshot = RepoSnapshot(
        id=uuid.uuid4().hex[:12],
        repo_id=repo_id,
        commit_sha=body.commit_sha if body else None,
    )
    db.add(snapshot)
    await db.commit()

    background.add_task(_run_ingestion_wrapper, snapshot.id)

    return IngestOut(snapshot_id=snapshot.id, status=SnapshotStatus.pending)


async def _run_ingestion_wrapper(snapshot_id: str) -> None:
    """Wrapper so background task runs with its own session."""
    await run_ingestion(snapshot_id)


@router.get("/{repo_id}/status", response_model=RepoStatus)
async def repo_status(repo_id: str, db: AsyncSession = Depends(get_db)) -> Any:
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    result = await db.execute(
        select(RepoSnapshot)
        .where(RepoSnapshot.repo_id == repo_id)
        .order_by(RepoSnapshot.created_at.desc())
    )
    snapshots = result.scalars().all()

    return RepoStatus(
        repo_id=repo_id,
        name=repo.name,
        snapshots=[
            SnapshotOut(
                id=s.id,
                repo_id=s.repo_id,
                commit_sha=s.commit_sha,
                status=s.status,
                file_count=s.file_count,
                error_message=s.error_message,
                created_at=s.created_at.isoformat(),
            )
            for s in snapshots
        ],
    )


@router.get("/{repo_id}/snapshots/{snapshot_id}", response_model=SnapshotDetail)
async def snapshot_detail(
    repo_id: str, snapshot_id: str, db: AsyncSession = Depends(get_db)
) -> Any:
    result = await db.execute(
        select(RepoSnapshot)
        .options(selectinload(RepoSnapshot.files))
        .where(RepoSnapshot.id == snapshot_id, RepoSnapshot.repo_id == repo_id)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return SnapshotDetail(
        id=snapshot.id,
        repo_id=snapshot.repo_id,
        commit_sha=snapshot.commit_sha,
        status=snapshot.status,
        file_count=snapshot.file_count,
        created_at=snapshot.created_at.isoformat(),
        files=[
            FileOut(
                id=f.id,
                path=f.path,
                language=f.language,
                hash=f.hash,
                size_bytes=f.size_bytes,
            )
            for f in snapshot.files
        ],
    )
