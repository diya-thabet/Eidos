"""API endpoints for test coverage tracking."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.coverage_parser import (
    CoverageData,
    coverage_grade,
    parse_coverage_json,
)
from app.api.dependencies import verify_snapshot
from app.storage.database import get_db
from app.storage.models import CoverageReport, RepoSnapshot

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FileCoverageOut(BaseModel):
    path: str
    percent: float
    covered_lines: int
    missing_lines: int
    num_statements: int
    branch_percent: float
    missing_line_numbers: list[int] = []


class CoverageReportOut(BaseModel):
    snapshot_id: str
    overall_percent: float
    branch_percent: float
    grade: str
    covered_lines: int
    missing_lines: int
    num_statements: int
    num_branches: int
    covered_branches: int
    file_count: int
    uploaded_at: str
    files: list[FileCoverageOut] = []


class CoverageSummaryOut(BaseModel):
    snapshot_id: str
    overall_percent: float
    branch_percent: float
    grade: str
    covered_lines: int
    missing_lines: int
    file_count: int
    uploaded_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_summary(report: CoverageReport) -> CoverageSummaryOut:
    return CoverageSummaryOut(
        snapshot_id=report.snapshot_id,
        overall_percent=report.overall_percent,
        branch_percent=report.branch_percent,
        grade=coverage_grade(report.overall_percent),
        covered_lines=report.covered_lines,
        missing_lines=report.missing_lines,
        file_count=report.file_count,
        uploaded_at=report.uploaded_at.isoformat(),
    )


def _persist_coverage(
    db: AsyncSession,
    snapshot_id: str,
    parsed: CoverageData,
    existing: CoverageReport | None,
) -> CoverageReport:
    """Create or update a coverage report row."""
    files_json = json.dumps([
        {
            "path": f.path,
            "percent": f.percent,
            "covered_lines": f.covered_lines,
            "missing_lines": f.missing_lines,
            "num_statements": f.num_statements,
            "branch_percent": f.branch_percent,
            "missing_line_numbers": f.missing_line_numbers,
        }
        for f in parsed.files
    ])

    if existing is None:
        report = CoverageReport(
            snapshot_id=snapshot_id,
            overall_percent=parsed.overall_percent,
            branch_percent=parsed.branch_percent,
            covered_lines=parsed.covered_lines,
            missing_lines=parsed.missing_lines,
            num_statements=parsed.num_statements,
            num_branches=parsed.num_branches,
            covered_branches=parsed.covered_branches,
            file_count=parsed.file_count,
            files_json=files_json,
        )
        db.add(report)
        return report

    existing.overall_percent = parsed.overall_percent
    existing.branch_percent = parsed.branch_percent
    existing.covered_lines = parsed.covered_lines
    existing.missing_lines = parsed.missing_lines
    existing.num_statements = parsed.num_statements
    existing.num_branches = parsed.num_branches
    existing.covered_branches = parsed.covered_branches
    existing.file_count = parsed.file_count
    existing.files_json = files_json
    return existing


# ---------------------------------------------------------------------------
# Upload coverage report
# ---------------------------------------------------------------------------


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/coverage",
    response_model=CoverageSummaryOut,
    summary="Upload a coverage.py JSON report",
    status_code=201,
)
async def upload_coverage(
    repo_id: str,
    snapshot_id: str,
    coverage_json: dict[str, Any] = Body(
        ..., description="The full coverage.py JSON dict",
    ),
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> CoverageSummaryOut:
    """Upload a coverage.json file produced by coverage.py / pytest-cov.

    The body must be the JSON object emitted by:
        pytest --cov=app --cov-report=json
        coverage json -o coverage.json
    """
    try:
        parsed = parse_coverage_json(coverage_json)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    existing_result = await db.execute(
        select(CoverageReport).where(
            CoverageReport.snapshot_id == snapshot_id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    report = _persist_coverage(db, snapshot_id, parsed, existing)
    await db.commit()
    await db.refresh(report)

    return _to_summary(report)


# ---------------------------------------------------------------------------
# Get coverage report
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/coverage",
    response_model=CoverageReportOut,
    summary="Get the coverage report for a snapshot",
)
async def get_coverage(
    repo_id: str,
    snapshot_id: str,
    include_files: bool = Query(
        True, description="Include per-file breakdown",
    ),
    min_percent: float | None = Query(
        None, ge=0, le=100,
        description="Filter files with coverage below this threshold",
    ),
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> CoverageReportOut:
    """Get the coverage report for a snapshot."""
    result = await db.execute(
        select(CoverageReport).where(
            CoverageReport.snapshot_id == snapshot_id,
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No coverage report uploaded for this snapshot",
        )

    files: list[FileCoverageOut] = []
    if include_files:
        try:
            files_data = json.loads(report.files_json or "[]")
        except json.JSONDecodeError:
            files_data = []
        for f in files_data:
            if min_percent is not None and f.get("percent", 0) >= min_percent:
                continue
            files.append(FileCoverageOut(**f))

    return CoverageReportOut(
        snapshot_id=report.snapshot_id,
        overall_percent=report.overall_percent,
        branch_percent=report.branch_percent,
        grade=coverage_grade(report.overall_percent),
        covered_lines=report.covered_lines,
        missing_lines=report.missing_lines,
        num_statements=report.num_statements,
        num_branches=report.num_branches,
        covered_branches=report.covered_branches,
        file_count=report.file_count,
        uploaded_at=report.uploaded_at.isoformat(),
        files=files,
    )


# ---------------------------------------------------------------------------
# Delete coverage report
# ---------------------------------------------------------------------------


@router.delete(
    "/{repo_id}/snapshots/{snapshot_id}/coverage",
    status_code=204,
    summary="Delete the coverage report for a snapshot",
)
async def delete_coverage(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> None:
    """Delete the coverage report for a snapshot."""
    result = await db.execute(
        select(CoverageReport).where(
            CoverageReport.snapshot_id == snapshot_id,
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="No coverage report")

    await db.delete(report)
    await db.commit()


# ---------------------------------------------------------------------------
# Coverage history (per repo)
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/coverage/history",
    response_model=list[CoverageSummaryOut],
    summary="Coverage history across all snapshots in a repo",
)
async def coverage_history(
    repo_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[CoverageSummaryOut]:
    """Return coverage summaries for all snapshots in a repo, newest first."""
    result = await db.execute(
        select(CoverageReport, RepoSnapshot)
        .join(
            RepoSnapshot,
            RepoSnapshot.id == CoverageReport.snapshot_id,
        )
        .where(RepoSnapshot.repo_id == repo_id)
        .order_by(RepoSnapshot.created_at.desc())
        .limit(limit)
    )
    return [_to_summary(report) for report, _ in result.all()]
