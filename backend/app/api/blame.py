"""API endpoints for git blame / churn analysis."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_snapshot
from app.auth.scopes import require_scope
from app.storage.database import get_db
from app.storage.models import RepoSnapshot, Symbol

router = APIRouter(dependencies=[Depends(require_scope("read:analysis"))])


class ContributorStats(BaseModel):
    author: str
    function_count: int
    file_count: int
    line_count: int
    commit_count: int
    symbol_count: int
    modules: list[str]


class ContributorsReport(BaseModel):
    snapshot_id: str
    total_authors: int
    total_commits: int
    total_lines: int
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
    """Return per-author stats using full blame data from authors_json.

    Each symbol stores a JSON dict of {author: line_count} from git blame.
    This gives accurate attribution � every author who wrote any line in a
    symbol gets credit proportional to their contribution.
    """
    result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id)
    )
    symbols = list(result.scalars().all())

    author_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "funcs": 0,
            "files": set(),
            "modules": set(),
            "lines": 0,
            "symbols": 0,
            "commit_hexes": set(),
        }
    )

    for s in symbols:
        # Parse the full author breakdown from blame
        authors_map: dict[str, Any] = {}
        if s.authors_json:
            try:
                authors_map = json.loads(s.authors_json)
            except (json.JSONDecodeError, TypeError):
                pass

        # Skip classes/interfaces for line counting to avoid overlapping
        # with their children (methods). Only count leaf symbols.
        is_leaf = s.kind in ("method", "constructor", "function", "field")

        if authors_map:
            # Credit every author based on their actual contribution
            # Determine if this is new-format (with hashes) or old-format (plain int)
            has_hashes = False
            for author, val in authors_map.items():
                if not author:
                    continue
                d = author_data[author]
                # Support both old {author: linecount} and new {author: {lines, commits, hashes}}
                if isinstance(val, dict):
                    lines = val.get("lines", 0)
                    hashes = val.get("hashes", [])
                    if hashes:
                        has_hashes = True
                else:
                    lines = int(val) if val else 0
                    hashes = []
                if is_leaf:
                    d["lines"] += lines
                d["files"].add(s.file_path)
                d["symbols"] += 1
                if s.kind in ("method", "constructor", "function"):
                    d["funcs"] += 1
                # Deduplicate commits using actual hashes
                for ch in hashes:
                    d["commit_hexes"].add(ch)
                ns = s.namespace or ""
                if not ns and "/" in s.file_path:
                    ns = s.file_path.rsplit("/", 1)[0]
                if ns:
                    d["modules"].add(ns)

            # For old-format authors_json (no hashes), credit each author
            # with the symbol's total commit_count (tracked via symbol identity
            # to avoid over-counting when multiple authors share a symbol).
            if not has_hashes and (s.commit_count or 0) > 0:
                for a in [a for a in authors_map if a]:
                    author_data[a]["commit_hexes"].add(
                        f"_legacy_{s.fq_name}"
                    )
        elif s.last_author:
            # Fallback for symbols without authors_json (old data)
            author = s.last_author
            d = author_data[author]
            if is_leaf:
                d["lines"] += max(0, (s.end_line or 0) - (s.start_line or 0))
            d["files"].add(s.file_path)
            d["symbols"] += 1
            if s.kind in ("method", "constructor", "function"):
                d["funcs"] += 1
            # Track unique symbols as proxy for commits when no hashes
            d["commit_hexes"].add(f"_legacy_{s.fq_name}")
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
                line_count=data["lines"],
                commit_count=len(data["commit_hexes"]),
                symbol_count=data["symbols"],
                modules=sorted(data["modules"]),
            )
            for author, data in author_data.items()
        ],
        key=lambda c: c.line_count,
        reverse=True,
    )

    # Compute accurate totals
    total_lines = sum(c.line_count for c in contributors)
    total_commits = sum(c.commit_count for c in contributors)

    return ContributorsReport(
        snapshot_id=snapshot_id,
        total_authors=len(contributors),
        total_commits=total_commits,
        total_lines=total_lines,
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
