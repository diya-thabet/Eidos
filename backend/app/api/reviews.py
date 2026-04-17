"""
API endpoints for the PR review engine.

Accepts a unified diff, runs behavioral analysis + impact analysis,
and returns a structured review report.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.reasoning.llm_client import LLMConfig, create_llm_client
from app.reviews.reviewer import review_diff
from app.storage.database import get_db
from app.storage.models import RepoSnapshot, Review
from app.storage.schemas import (
    ChangedSymbolOut,
    ImpactedSymbolOut,
    ReviewFindingOut,
    ReviewReportOut,
    ReviewRequest,
)

router = APIRouter()


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/review",
    response_model=ReviewReportOut,
    summary="Review a PR diff against this snapshot",
)
async def review_pr(
    repo_id: str,
    snapshot_id: str,
    body: ReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a unified diff for review.

    The system:
    1. Parses the diff into file-level changes
    2. Maps changed lines to known symbols
    3. Runs behavioral heuristics (removed validations, changed conditions, etc.)
    4. Analyses blast radius via call graph
    5. Computes a risk score
    6. Optionally enriches with LLM summary

    Works with or without an LLM.
    """
    await _verify_snapshot(db, repo_id, snapshot_id)

    # Create LLM client (or stub)
    llm_config = _get_llm_config()
    llm = create_llm_client(llm_config)

    report = await review_diff(db, snapshot_id, body.diff, llm=llm, max_hops=body.max_hops)

    # Persist the review
    db_review = Review(
        snapshot_id=snapshot_id,
        diff_summary=report.diff_summary,
        risk_score=report.risk_score,
        risk_level=report.risk_level,
        report_json=json.dumps(asdict(report), default=str),
    )
    db.add(db_review)
    await db.flush()
    await db.commit()

    return ReviewReportOut(
        id=db_review.id,
        snapshot_id=report.snapshot_id,
        diff_summary=report.diff_summary,
        files_changed=report.files_changed,
        changed_symbols=[ChangedSymbolOut(**asdict(cs)) for cs in report.changed_symbols],
        findings=[
            ReviewFindingOut(
                category=f.category.value,
                severity=f.severity.value,
                **{k: v for k, v in asdict(f).items() if k not in ("category", "severity")},
            )
            for f in report.findings
        ],
        impacted_symbols=[ImpactedSymbolOut(**asdict(imp)) for imp in report.impacted_symbols],
        risk_score=report.risk_score,
        risk_level=report.risk_level,
        llm_summary=report.llm_summary,
    )


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/reviews",
    response_model=list[ReviewReportOut],
    summary="List past reviews for a snapshot",
)
async def list_reviews(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
):
    await _verify_snapshot(db, repo_id, snapshot_id)
    result = await db.execute(
        select(Review).where(Review.snapshot_id == snapshot_id).order_by(Review.id.desc())
    )
    reviews = []
    for row in result.scalars().all():
        data = json.loads(row.report_json)
        reviews.append(
            ReviewReportOut(
                id=row.id,
                snapshot_id=row.snapshot_id,
                diff_summary=row.diff_summary,
                files_changed=data.get("files_changed", []),
                changed_symbols=[ChangedSymbolOut(**cs) for cs in data.get("changed_symbols", [])],
                findings=[ReviewFindingOut(**f) for f in data.get("findings", [])],
                impacted_symbols=[
                    ImpactedSymbolOut(**imp) for imp in data.get("impacted_symbols", [])
                ],
                risk_score=row.risk_score,
                risk_level=row.risk_level,
                llm_summary=data.get("llm_summary", ""),
            )
        )
    return reviews


async def _verify_snapshot(db: AsyncSession, repo_id: str, snapshot_id: str):
    result = await db.execute(
        select(RepoSnapshot).where(
            RepoSnapshot.id == snapshot_id,
            RepoSnapshot.repo_id == repo_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")


def _get_llm_config() -> LLMConfig | None:
    if settings.llm_base_url:
        return LLMConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
        )
    return None
