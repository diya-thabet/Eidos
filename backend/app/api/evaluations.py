"""
API endpoints for evaluation & guardrails.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_snapshot
from app.guardrails.runner import run_snapshot_evaluation
from app.storage.database import get_db
from app.storage.models import Evaluation, RepoSnapshot
from app.storage.schemas import EvalCheckOut, EvalReportOut

router = APIRouter()


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/evaluate",
    response_model=EvalReportOut,
    summary="Run evaluation & guardrails on a snapshot",
)
async def evaluate_snapshot(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snap: RepoSnapshot = Depends(verify_snapshot),
) -> Any:
    """
    Run all guardrail checks for a snapshot:
    - Document completeness and accuracy
    - Review finding precision
    - Symbol coverage
    - Output safety (PII leak detection)

    Results are persisted and can be retrieved via GET.
    """
    report = await run_snapshot_evaluation(db, snapshot_id)

    return EvalReportOut(
        snapshot_id=report.snapshot_id,
        scope=report.scope,
        overall_score=report.overall_score,
        overall_severity=report.overall_severity.value,
        checks=[
            EvalCheckOut(
                category=c.category.value,
                name=c.name,
                passed=c.passed,
                severity=c.severity.value,
                score=c.score,
                message=c.message,
                details=c.details,
            )
            for c in report.checks
        ],
        summary=report.summary,
    )


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/evaluations",
    response_model=list[EvalReportOut],
    summary="List past evaluations for a snapshot",
)
async def list_evaluations(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snap: RepoSnapshot = Depends(verify_snapshot),
) -> Any:
    """List all past evaluation reports for a snapshot."""
    result = await db.execute(
        select(Evaluation)
        .where(Evaluation.snapshot_id == snapshot_id)
        .order_by(Evaluation.id.desc())
    )
    evals = []
    for row in result.scalars().all():
        checks_data = json.loads(row.checks_json)
        evals.append(
            EvalReportOut(
                id=row.id,
                snapshot_id=row.snapshot_id,
                scope=row.scope,
                overall_score=row.overall_score,
                overall_severity=row.overall_severity,
                checks=[EvalCheckOut(**c) for c in checks_data],
                summary=row.summary,
            )
        )
    return evals


