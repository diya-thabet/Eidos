"""API endpoints for incremental health analysis and finding diffs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.incremental_health import (
    compute_health_diff,
    persist_findings,
)
from app.api.dependencies import verify_snapshot
from app.auth.scopes import require_scope
from app.storage.database import get_db
from app.storage.models import HealthFindingPersisted, RepoSnapshot

router = APIRouter(dependencies=[Depends(require_scope("read:analysis"))])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FindingOut(BaseModel):
    rule_id: str
    severity: str
    symbol_fq_name: str
    file_path: str
    line: int
    message: str
    fingerprint: str


class HealthDiffOut(BaseModel):
    new_snapshot_id: str
    prev_snapshot_id: str
    added: list[FindingOut]
    fixed: list[FindingOut]
    unchanged_count: int
    new_total: int
    prev_total: int
    summary: str


class PersistFindingsRequest(BaseModel):
    findings: list[dict[str, Any]]


class PersistFindingsResult(BaseModel):
    persisted: int
    snapshot_id: str


class FindingsListOut(BaseModel):
    snapshot_id: str
    total: int
    findings: list[FindingOut]


# ---------------------------------------------------------------------------
# Diff endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/health/diff/{prev_snapshot_id}",
    response_model=HealthDiffOut,
    summary="Health findings diff between two snapshots",
)
async def health_diff(
    repo_id: str,
    snapshot_id: str,
    prev_snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> HealthDiffOut:
    """Compare health findings between two snapshots.

    Returns added (new issues) and fixed (resolved issues).
    Useful for PR reviews: "this PR introduced 3 new errors and fixed 2".
    """
    # Verify prev snapshot exists
    prev = await db.get(RepoSnapshot, prev_snapshot_id)
    if prev is None or prev.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Previous snapshot not found")

    diff = await compute_health_diff(db, snapshot_id, prev_snapshot_id)

    added_count = len(diff.added)
    fixed_count = len(diff.fixed)
    summary = f"+{added_count} new, -{fixed_count} fixed, {diff.unchanged_count} unchanged"

    return HealthDiffOut(
        new_snapshot_id=diff.new_snapshot_id,
        prev_snapshot_id=diff.prev_snapshot_id,
        added=[FindingOut(**f) for f in diff.added],
        fixed=[FindingOut(**f) for f in diff.fixed],
        unchanged_count=diff.unchanged_count,
        new_total=diff.new_total,
        prev_total=diff.prev_total,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Persist findings
# ---------------------------------------------------------------------------


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/health/findings",
    response_model=PersistFindingsResult,
    status_code=201,
    summary="Persist health findings for a snapshot",
    dependencies=[Depends(require_scope("write:snapshots"))],
)
async def store_findings(
    repo_id: str,
    snapshot_id: str,
    body: PersistFindingsRequest,
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> PersistFindingsResult:
    """Store health findings for later diff comparison."""
    count = await persist_findings(db, snapshot_id, body.findings)
    await db.commit()
    return PersistFindingsResult(persisted=count, snapshot_id=snapshot_id)


# ---------------------------------------------------------------------------
# List persisted findings
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/health/findings",
    response_model=FindingsListOut,
    summary="List persisted health findings",
)
async def list_findings(
    repo_id: str,
    snapshot_id: str,
    severity: str | None = Query(None, description="Filter by severity"),
    file_path: str | None = Query(None, description="Filter by file path"),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> FindingsListOut:
    """List persisted health findings for a snapshot."""
    stmt = select(HealthFindingPersisted).where(
        HealthFindingPersisted.snapshot_id == snapshot_id,
    )
    if severity:
        stmt = stmt.where(HealthFindingPersisted.severity == severity)
    if file_path:
        stmt = stmt.where(HealthFindingPersisted.file_path == file_path)
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    findings = result.scalars().all()

    # Total count
    count_stmt = select(func.count(HealthFindingPersisted.id)).where(
        HealthFindingPersisted.snapshot_id == snapshot_id,
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return FindingsListOut(
        snapshot_id=snapshot_id,
        total=total,
        findings=[
            FindingOut(
                rule_id=f.rule_id,
                severity=f.severity,
                symbol_fq_name=f.symbol_fq_name,
                file_path=f.file_path,
                line=f.line,
                message=f.message,
                fingerprint=f.fingerprint,
            )
            for f in findings
        ],
    )
