"""API endpoints for git blame / churn analysis."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_snapshot
from app.storage.database import get_db
from app.storage.models import RepoSnapshot, Symbol

router = APIRouter()


class ContributorStats(BaseModel):
    author: str
    function_count: int
    file_count: int
    modules: list[str]


class ContributorsReport(BaseModel):
    snapshot_id: str
    total_authors: int
    contributors: list[ContributorStats]


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/contributors",
    response_model=ContributorsReport,
    summary="Get contributor stats per author",
)
async def get_contributors(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> ContributorsReport:
    """Return per-author function count, files touched, modules."""
    result = await db.execute(
        select(Symbol)
        .where(
            Symbol.snapshot_id == snapshot_id,
            Symbol.kind.in_(["method", "constructor"]),
            Symbol.last_author != "",
            Symbol.last_author.is_not(None),
        )
    )
    symbols = list(result.scalars().all())

    author_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"funcs": 0, "files": set(), "modules": set()}
    )
    for s in symbols:
        a = s.last_author or ""
        if not a:
            continue
        d = author_data[a]
        d["funcs"] += 1
        d["files"].add(s.file_path)
        ns = s.namespace or ""
        if not ns and "/" in s.file_path:
            ns = s.file_path.rsplit("/", 1)[0]
        if ns:
            d["modules"].add(ns)

    contributors = sorted(
        [
            ContributorStats(
                author=author,
                function_count=data["funcs"],
                file_count=len(data["files"]),
                modules=sorted(data["modules"]),
            )
            for author, data in author_data.items()
        ],
        key=lambda c: c.function_count,
        reverse=True,
    )

    return ContributorsReport(
        snapshot_id=snapshot_id,
        total_authors=len(contributors),
        contributors=contributors,
    )


class HotspotItem(BaseModel):
    fq_name: str
    name: str
    file_path: str
    start_line: int
    end_line: int
    cyclomatic_complexity: int
    cognitive_complexity: int
    commit_count: int
    author_count: int
    last_author: str
    risk_score: float


class HotspotsReport(BaseModel):
    snapshot_id: str
    total: int
    items: list[HotspotItem]


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/hotspots",
    response_model=HotspotsReport,
    summary="Get code hotspots (high churn x high complexity)",
)
async def get_hotspots(
    repo_id: str,
    snapshot_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> HotspotsReport:
    """Functions sorted by risk = commit_count * complexity."""
    result = await db.execute(
        select(Symbol)
        .where(
            Symbol.snapshot_id == snapshot_id,
            Symbol.kind.in_(["method", "constructor"]),
        )
    )
    symbols = list(result.scalars().all())

    items: list[HotspotItem] = []
    for s in symbols:
        cc = s.cyclomatic_complexity or 0
        churn = s.commit_count or 0
        risk = churn * cc
        if risk == 0:
            continue
        items.append(HotspotItem(
            fq_name=s.fq_name,
            name=s.name,
            file_path=s.file_path,
            start_line=s.start_line,
            end_line=s.end_line,
            cyclomatic_complexity=cc,
            cognitive_complexity=s.cognitive_complexity or 0,
            commit_count=churn,
            author_count=s.author_count or 0,
            last_author=s.last_author or "",
            risk_score=float(risk),
        ))

    items.sort(key=lambda i: i.risk_score, reverse=True)
    items = items[:limit]

    return HotspotsReport(
        snapshot_id=snapshot_id,
        total=len(items),
        items=items,
    )
