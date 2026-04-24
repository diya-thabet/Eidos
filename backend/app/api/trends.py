"""
Health score trend tracking across snapshots.

Tracks code health scores over time to answer:
"Is the codebase getting better or worse?"
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_db
from app.storage.models import Evaluation, Repo, RepoSnapshot

router = APIRouter()


class HealthTrendPoint(BaseModel):
    """A single data point in the health trend."""

    snapshot_id: str
    commit_sha: str | None = None
    created_at: str
    overall_score: float
    overall_severity: str
    check_count: int
    passed_count: int


class HealthTrendResponse(BaseModel):
    """Health score trend across snapshots."""

    repo_id: str
    data_points: list[HealthTrendPoint]
    trend: str  # improving | degrading | stable | insufficient_data
    latest_score: float | None = None
    score_change: float | None = None


@router.get(
    "/{repo_id}/health/trend",
    response_model=HealthTrendResponse,
    summary="Get health score trend across snapshots",
)
async def health_trend(
    repo_id: str,
    limit: int = Query(20, ge=1, le=100, description="Max number of snapshots to include"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Returns health scores across the most recent snapshots for a repo.

    The trend is computed by comparing the first and last scores:
    - **improving**: latest score > earliest score by > 0.02
    - **degrading**: latest score < earliest score by > 0.02
    - **stable**: within 0.02
    - **insufficient_data**: fewer than 2 data points
    """
    repo = await db.get(Repo, repo_id)
    if repo is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Repo not found")

    # Get snapshots with evaluations, ordered by creation date
    snap_result = await db.execute(
        select(RepoSnapshot)
        .where(RepoSnapshot.repo_id == repo_id)
        .order_by(RepoSnapshot.created_at.desc())
        .limit(limit)
    )
    snapshots = list(snap_result.scalars().all())
    snapshots.reverse()  # oldest first

    data_points: list[HealthTrendPoint] = []

    for snap in snapshots:
        eval_result = await db.execute(
            select(Evaluation)
            .where(Evaluation.snapshot_id == snap.id)
            .order_by(Evaluation.id.desc())
            .limit(1)
        )
        evaluation = eval_result.scalar_one_or_none()
        if evaluation is None:
            continue

        checks_data = json.loads(evaluation.checks_json) if evaluation.checks_json else []
        passed = sum(1 for c in checks_data if c.get("passed", False))

        data_points.append(
            HealthTrendPoint(
                snapshot_id=snap.id,
                commit_sha=snap.commit_sha,
                created_at=snap.created_at.isoformat() if snap.created_at else "",
                overall_score=evaluation.overall_score,
                overall_severity=evaluation.overall_severity,
                check_count=len(checks_data),
                passed_count=passed,
            )
        )

    # Compute trend
    trend = "insufficient_data"
    latest_score = None
    score_change = None

    if len(data_points) >= 2:
        first = data_points[0].overall_score
        last = data_points[-1].overall_score
        latest_score = last
        score_change = round(last - first, 4)

        if score_change > 0.02:
            trend = "improving"
        elif score_change < -0.02:
            trend = "degrading"
        else:
            trend = "stable"
    elif len(data_points) == 1:
        latest_score = data_points[0].overall_score
        trend = "insufficient_data"

    return HealthTrendResponse(
        repo_id=repo_id,
        data_points=data_points,
        trend=trend,
        latest_score=latest_score,
        score_change=score_change,
    )
