"""API endpoints for health score and history."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.health_score import compute_health_score
from app.api.dependencies import verify_snapshot
from app.auth.scopes import require_scope
from app.storage.database import get_db
from app.storage.models import (
    CoverageReport,
    HealthScoreHistory,
    RepoSnapshot,
    Symbol,
)

router = APIRouter(dependencies=[Depends(require_scope("read:analysis"))])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CategoryScoreOut(BaseModel):
    category: str
    score: float
    weight: int
    weighted_score: float
    details: str


class HealthScoreOut(BaseModel):
    snapshot_id: str
    overall: float
    grade: str
    categories: list[CategoryScoreOut]
    total_findings: int
    error_count: int
    warning_count: int
    computed_at: str


class HealthHistoryItem(BaseModel):
    snapshot_id: str
    overall: float
    grade: str
    total_findings: int
    computed_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _gather_metrics(db: AsyncSession, snapshot_id: str) -> dict[str, Any]:
    """Gather metrics from DB for health score computation."""
    sym_result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id)
    )
    symbols = sym_result.scalars().all()

    methods = [s for s in symbols if s.kind in ("method", "constructor", "function")]
    cc_values = [s.cyclomatic_complexity or 0 for s in methods]
    avg_cc = sum(cc_values) / len(cc_values) if cc_values else 0.0
    max_cc = max(cc_values) if cc_values else 0
    long_funcs = sum(
        1 for s in methods
        if (s.end_line or 0) - (s.start_line or 0) > 30
    )

    # Coverage
    cov_result = await db.execute(
        select(CoverageReport).where(CoverageReport.snapshot_id == snapshot_id)
    )
    cov = cov_result.scalar_one_or_none()

    return {
        "avg_cyclomatic_complexity": round(avg_cc, 2),
        "max_cyclomatic_complexity": max_cc,
        "long_function_count": long_funcs,
        "total_methods": len(methods),
        "error_count": 0,
        "warning_count": 0,
        "total_findings": 0,
        "clone_group_count": 0,
        "dead_function_count": 0,
        "undocumented_public_count": 0,
        "total_public_count": max(len([s for s in symbols if s.kind != "field"]), 1),
        "naming_violations": 0,
        "security_findings": 0,
        "dependency_issues": 0,
        "has_tests": False,
        "coverage_percent": cov.overall_percent if cov else 0.0,
    }


# ---------------------------------------------------------------------------
# Compute / Get health score
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/health-score",
    response_model=HealthScoreOut,
    summary="Get or compute health score for a snapshot",
)
async def get_health_score(
    repo_id: str,
    snapshot_id: str,
    recompute: bool = Query(False, description="Force recomputation"),
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> HealthScoreOut:
    """Get the health score. Computes and persists if not already stored."""
    # Check existing
    if not recompute:
        result = await db.execute(
            select(HealthScoreHistory).where(
                HealthScoreHistory.snapshot_id == snapshot_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            try:
                cats = json.loads(existing.category_scores_json or "[]")
            except (json.JSONDecodeError, TypeError):
                cats = []
            return HealthScoreOut(
                snapshot_id=snapshot_id,
                overall=existing.overall,
                grade=existing.grade,
                categories=[CategoryScoreOut(**c) for c in cats],
                total_findings=existing.total_findings,
                error_count=existing.error_count,
                warning_count=existing.warning_count,
                computed_at=existing.computed_at.isoformat(),
            )

    # Compute
    metrics = await _gather_metrics(db, snapshot_id)
    score = compute_health_score(metrics)

    cats_json = json.dumps([
        {
            "category": c.category,
            "score": c.score,
            "weight": c.weight,
            "weighted_score": c.weighted_score,
            "details": c.details,
        }
        for c in score.categories
    ])

    # Upsert
    result = await db.execute(
        select(HealthScoreHistory).where(
            HealthScoreHistory.snapshot_id == snapshot_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.overall = score.overall
        existing.grade = score.grade
        existing.category_scores_json = cats_json
        existing.total_findings = score.total_findings
        existing.error_count = score.error_count
        existing.warning_count = score.warning_count
    else:
        db.add(HealthScoreHistory(
            snapshot_id=snapshot_id,
            overall=score.overall,
            grade=score.grade,
            category_scores_json=cats_json,
            total_findings=score.total_findings,
            error_count=score.error_count,
            warning_count=score.warning_count,
        ))
    await db.commit()

    from datetime import UTC, datetime
    return HealthScoreOut(
        snapshot_id=snapshot_id,
        overall=score.overall,
        grade=score.grade,
        categories=[
            CategoryScoreOut(
                category=c.category, score=c.score,
                weight=c.weight, weighted_score=c.weighted_score,
                details=c.details,
            )
            for c in score.categories
        ],
        total_findings=score.total_findings,
        error_count=score.error_count,
        warning_count=score.warning_count,
        computed_at=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Health history
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/health-history",
    response_model=list[HealthHistoryItem],
    summary="Health score history across snapshots",
)
async def health_history(
    repo_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[HealthHistoryItem]:
    """Return health scores for all snapshots in a repo, newest first."""
    result = await db.execute(
        select(HealthScoreHistory, RepoSnapshot)
        .join(RepoSnapshot, RepoSnapshot.id == HealthScoreHistory.snapshot_id)
        .where(RepoSnapshot.repo_id == repo_id)
        .order_by(RepoSnapshot.created_at.desc())
        .limit(limit)
    )
    return [
        HealthHistoryItem(
            snapshot_id=h.snapshot_id,
            overall=h.overall,
            grade=h.grade,
            total_findings=h.total_findings,
            computed_at=h.computed_at.isoformat(),
        )
        for h, _ in result.all()
    ]
