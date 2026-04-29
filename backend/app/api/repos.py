from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.crypto import encrypt
from app.auth.dependencies import get_current_user
from app.core.tasks import run_ingestion
from app.storage.database import get_db
from app.storage.models import (
    Edge,
    File,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
    SymbolNote,
    User,
)
from app.storage.schemas import (
    CallerOut,
    CallersResponse,
    FileOut,
    IngestOut,
    IngestRequest,
    RepoCreate,
    RepoOut,
    RepoStatus,
    RepoUpdate,
    SnapshotDetail,
    SnapshotOut,
    SymbolNoteCreate,
    SymbolNoteOut,
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
        git_provider=body.git_provider,
        git_token_enc=encrypt(body.git_token) if body.git_token else "",
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
                progress_percent=s.progress_percent,
                progress_message=s.progress_message,
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
        progress_percent=snapshot.progress_percent,
        progress_message=snapshot.progress_message,
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


@router.delete("/{repo_id}", status_code=204)
async def delete_repo(
    repo_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a repo and all associated snapshots, symbols, edges, summaries, reviews, and docs."""
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    await db.delete(repo)
    await db.commit()


@router.patch("/{repo_id}", response_model=RepoOut)
async def update_repo(
    repo_id: str,
    body: RepoUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """Update repo fields (name, default_branch, git_token). Only provided fields are changed."""
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    if body.name is not None:
        repo.name = body.name.strip()
    if body.default_branch is not None:
        repo.default_branch = body.default_branch.strip()
    if body.git_token is not None:
        repo.git_token_enc = encrypt(body.git_token) if body.git_token else ""
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


# ---------------------------------------------------------------------------
# 8.1 List all repos
# ---------------------------------------------------------------------------


@router.get("", response_model=list[RepoOut])
async def list_repos(
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List all repositories."""
    result = await db.execute(select(Repo).order_by(Repo.created_at.desc()))
    repos = result.scalars().all()
    return [
        RepoOut(
            id=r.id,
            name=r.name,
            url=r.url,
            default_branch=r.default_branch,
            created_at=r.created_at.isoformat(),
            last_indexed_at=(
                r.last_indexed_at.isoformat() if r.last_indexed_at else None
            ),
        )
        for r in repos
    ]


# ---------------------------------------------------------------------------
# 8.2 List snapshots (paginated)
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots",
    response_model=list[SnapshotOut],
    summary="List snapshots for a repo",
)
async def list_snapshots(
    repo_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return all snapshots for a repo, newest first."""
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    result = await db.execute(
        select(RepoSnapshot)
        .where(RepoSnapshot.repo_id == repo_id)
        .order_by(RepoSnapshot.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    snapshots = result.scalars().all()
    return [
        SnapshotOut(
            id=s.id,
            repo_id=s.repo_id,
            commit_sha=s.commit_sha or "",
            status=s.status,
            file_count=s.file_count or 0,
            created_at=s.created_at.isoformat(),
            progress_percent=s.progress_percent or 0,
            progress_message=s.progress_message or "",
        )
        for s in snapshots
    ]


# ---------------------------------------------------------------------------
# 8.3 Delete a snapshot
# ---------------------------------------------------------------------------


@router.delete("/{repo_id}/snapshots/{snapshot_id}", status_code=204)
async def delete_snapshot(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a snapshot and all associated data."""
    snapshot = await db.get(RepoSnapshot, snapshot_id)
    if snapshot is None or snapshot.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    await db.delete(snapshot)
    await db.commit()


# ---------------------------------------------------------------------------
# 8.4 List files in a snapshot
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/files",
    response_model=list[FileOut],
    summary="List all files in a snapshot",
)
async def list_files(
    repo_id: str,
    snapshot_id: str,
    language: str | None = Query(None, description="Filter by language"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return all files in a snapshot with language, size, hash."""
    snapshot = await db.get(RepoSnapshot, snapshot_id)
    if snapshot is None or snapshot.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    stmt = select(File).where(File.snapshot_id == snapshot_id)
    if language:
        stmt = stmt.where(File.language == language)
    stmt = stmt.order_by(File.path)
    result = await db.execute(stmt)
    files = result.scalars().all()
    return [
        FileOut(
            id=f.id,
            path=f.path, language=f.language or "",
            size_bytes=f.size_bytes, hash=f.hash,
        )
        for f in files
    ]


# ---------------------------------------------------------------------------
# 8.5 Get callers of a symbol
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/symbols/{fq_name:path}/callers",
    response_model=CallersResponse,
    summary="Get all callers of a symbol",
)
async def get_callers(
    repo_id: str,
    snapshot_id: str,
    fq_name: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return all symbols that call the given symbol."""
    snapshot = await db.get(RepoSnapshot, snapshot_id)
    if snapshot is None or snapshot.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    result = await db.execute(
        select(Edge).where(
            Edge.snapshot_id == snapshot_id,
            Edge.target_fq_name == fq_name,
            Edge.edge_type == "calls",
        )
    )
    edges = result.scalars().all()
    caller_fqs = list({e.source_fq_name for e in edges})

    callers: list[CallerOut] = []
    if caller_fqs:
        sym_result = await db.execute(
            select(Symbol).where(
                Symbol.snapshot_id == snapshot_id,
                Symbol.fq_name.in_(caller_fqs),
            )
        )
        for s in sym_result.scalars().all():
            callers.append(CallerOut(
                fq_name=s.fq_name, name=s.name, kind=s.kind,
                file_path=s.file_path, start_line=s.start_line,
            ))

    return CallersResponse(
        target_fq_name=fq_name, callers=callers, total=len(callers),
    )


# ---------------------------------------------------------------------------
# 8.6 Symbol notes (CRUD)
# ---------------------------------------------------------------------------


@router.patch(
    "/{repo_id}/snapshots/{snapshot_id}/symbols/{fq_name:path}/notes",
    response_model=SymbolNoteOut,
    summary="Add or update a note on a symbol",
)
async def upsert_symbol_note(
    repo_id: str,
    snapshot_id: str,
    fq_name: str,
    body: SymbolNoteCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create or update a user annotation on a symbol."""
    snapshot = await db.get(RepoSnapshot, snapshot_id)
    if snapshot is None or snapshot.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    result = await db.execute(
        select(SymbolNote).where(
            SymbolNote.snapshot_id == snapshot_id,
            SymbolNote.symbol_fq_name == fq_name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        existing = SymbolNote(
            snapshot_id=snapshot_id,
            symbol_fq_name=fq_name,
            note=body.note,
            author=body.author,
        )
        db.add(existing)
    else:
        existing.note = body.note
        if body.author:
            existing.author = body.author
    await db.commit()
    await db.refresh(existing)
    return SymbolNoteOut(
        id=existing.id,
        snapshot_id=existing.snapshot_id,
        symbol_fq_name=existing.symbol_fq_name,
        note=existing.note,
        author=existing.author,
        created_at=existing.created_at.isoformat(),
        updated_at=existing.updated_at.isoformat(),
    )


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/symbols/{fq_name:path}/notes",
    response_model=list[SymbolNoteOut],
    summary="Get notes for a symbol",
)
async def get_symbol_notes(
    repo_id: str,
    snapshot_id: str,
    fq_name: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return all notes for a symbol."""
    result = await db.execute(
        select(SymbolNote).where(
            SymbolNote.snapshot_id == snapshot_id,
            SymbolNote.symbol_fq_name == fq_name,
        )
    )
    notes = result.scalars().all()
    return [
        SymbolNoteOut(
            id=n.id, snapshot_id=n.snapshot_id,
            symbol_fq_name=n.symbol_fq_name,
            note=n.note, author=n.author,
            created_at=n.created_at.isoformat(),
            updated_at=n.updated_at.isoformat(),
        )
        for n in notes
    ]
