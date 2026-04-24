"""
API endpoints for cross-entity search and snapshot comparison.

Provides:
- Full-text search across symbols, summaries, and generated docs
- Snapshot diff: what changed between two snapshots (new/removed/modified symbols)
- Export: download analysis results as JSON
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_db
from app.storage.models import (
    Edge,
    GeneratedDoc,
    RepoSnapshot,
    Summary,
    Symbol,
)
from app.storage.schemas import PaginatedResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Search schemas
# ---------------------------------------------------------------------------


class SearchHit(BaseModel):
    """A single search result."""

    entity_type: str  # symbol | summary | doc
    entity_id: str
    title: str
    snippet: str
    file_path: str = ""
    score: float = 1.0
    metadata: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Snapshot diff schemas
# ---------------------------------------------------------------------------


class SymbolDiff(BaseModel):
    fq_name: str
    kind: str
    file_path: str
    change: str  # added | removed | modified


class SnapshotDiffResponse(BaseModel):
    base_snapshot_id: str
    head_snapshot_id: str
    added: list[SymbolDiff]
    removed: list[SymbolDiff]
    modified: list[SymbolDiff]
    summary: dict[str, int]  # counts


# ---------------------------------------------------------------------------
# Export schema
# ---------------------------------------------------------------------------


class ExportResponse(BaseModel):
    snapshot_id: str
    symbols: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    summaries: list[dict[str, Any]]
    docs: list[dict[str, Any]]
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/search",
    response_model=PaginatedResponse,
    summary="Search across symbols, summaries, and documents",
)
async def search(
    repo_id: str,
    snapshot_id: str,
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    entity_type: str | None = Query(None, description="Filter: symbol, summary, doc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Full-text search across all indexed entities in a snapshot.

    Searches symbol names/fq_names, summary content, and generated
    document titles/markdown.  Results are ranked by relevance.
    """
    await _verify_snapshot(db, repo_id, snapshot_id)

    pattern = f"%{q}%"
    hits: list[SearchHit] = []

    # Search symbols
    if entity_type is None or entity_type == "symbol":
        sym_stmt = (
            select(Symbol)
            .where(
                Symbol.snapshot_id == snapshot_id,
                or_(
                    Symbol.name.ilike(pattern),
                    Symbol.fq_name.ilike(pattern),
                    Symbol.file_path.ilike(pattern),
                    Symbol.namespace.ilike(pattern),
                ),
            )
            .limit(limit * 2)  # over-fetch, we'll trim later
        )
        result = await db.execute(sym_stmt)
        for s in result.scalars().all():
            hits.append(
                SearchHit(
                    entity_type="symbol",
                    entity_id=s.fq_name,
                    title=f"{s.kind}: {s.fq_name}",
                    snippet=s.signature or f"{s.kind} {s.name}",
                    file_path=s.file_path,
                    score=_score_symbol(s, q),
                    metadata={"kind": s.kind, "start_line": s.start_line, "end_line": s.end_line},
                )
            )

    # Search summaries
    if entity_type is None or entity_type == "summary":
        sum_stmt = (
            select(Summary)
            .where(
                Summary.snapshot_id == snapshot_id,
                or_(
                    Summary.scope_id.ilike(pattern),
                    Summary.summary_json.ilike(pattern),
                ),
            )
            .limit(limit * 2)
        )
        result = await db.execute(sum_stmt)
        for s in result.scalars().all():
            parsed = {}
            try:
                parsed = json.loads(s.summary_json)
            except (json.JSONDecodeError, TypeError):
                pass
            hits.append(
                SearchHit(
                    entity_type="summary",
                    entity_id=f"{s.scope_type}/{s.scope_id}",
                    title=f"{s.scope_type} summary: {s.scope_id}",
                    snippet=parsed.get("purpose", "")[:200],
                    score=_score_text(s.scope_id, q),
                    metadata={"scope_type": s.scope_type},
                )
            )

    # Search generated docs
    if entity_type is None or entity_type == "doc":
        doc_stmt = (
            select(GeneratedDoc)
            .where(
                GeneratedDoc.snapshot_id == snapshot_id,
                or_(
                    GeneratedDoc.title.ilike(pattern),
                    GeneratedDoc.markdown.ilike(pattern),
                    GeneratedDoc.scope_id.ilike(pattern),
                ),
            )
            .limit(limit * 2)
        )
        result = await db.execute(doc_stmt)
        for d in result.scalars().all():
            hits.append(
                SearchHit(
                    entity_type="doc",
                    entity_id=str(d.id),
                    title=d.title,
                    snippet=d.markdown[:200] if d.markdown else "",
                    score=_score_text(d.title, q),
                    metadata={"doc_type": d.doc_type, "scope_id": d.scope_id},
                )
            )

    # Sort by score descending
    hits.sort(key=lambda h: h.score, reverse=True)
    total = len(hits)
    page = hits[offset : offset + limit]

    return PaginatedResponse(
        items=[h.model_dump() for h in page],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit < total),
    )


# ---------------------------------------------------------------------------
# Snapshot comparison endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/diff/{other_snapshot_id}",
    response_model=SnapshotDiffResponse,
    summary="Compare two snapshots (symbol-level diff)",
)
async def compare_snapshots(
    repo_id: str,
    snapshot_id: str,
    other_snapshot_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Compare symbols between two snapshots of the same repo.

    Returns lists of added, removed, and modified symbols.
    A symbol is considered modified if it exists in both snapshots
    but its signature, line range, or file path changed.
    """
    await _verify_snapshot(db, repo_id, snapshot_id)
    await _verify_snapshot(db, repo_id, other_snapshot_id)

    # Fetch symbols for both snapshots
    base_syms = await _get_symbol_map(db, snapshot_id)
    head_syms = await _get_symbol_map(db, other_snapshot_id)

    base_keys = set(base_syms.keys())
    head_keys = set(head_syms.keys())

    added = [
        SymbolDiff(
            fq_name=fq,
            kind=head_syms[fq]["kind"],
            file_path=head_syms[fq]["file_path"],
            change="added",
        )
        for fq in sorted(head_keys - base_keys)
    ]

    removed = [
        SymbolDiff(
            fq_name=fq,
            kind=base_syms[fq]["kind"],
            file_path=base_syms[fq]["file_path"],
            change="removed",
        )
        for fq in sorted(base_keys - head_keys)
    ]

    modified = []
    for fq in sorted(base_keys & head_keys):
        b = base_syms[fq]
        h = head_syms[fq]
        if (
            b["signature"] != h["signature"]
            or b["start_line"] != h["start_line"]
            or b["end_line"] != h["end_line"]
            or b["file_path"] != h["file_path"]
        ):
            modified.append(
                SymbolDiff(
                    fq_name=fq,
                    kind=h["kind"],
                    file_path=h["file_path"],
                    change="modified",
                )
            )

    return SnapshotDiffResponse(
        base_snapshot_id=snapshot_id,
        head_snapshot_id=other_snapshot_id,
        added=added,
        removed=removed,
        modified=modified,
        summary={
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "unchanged": len(base_keys & head_keys) - len(modified),
        },
    )


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/export",
    response_model=ExportResponse,
    summary="Export full snapshot analysis as JSON",
)
async def export_snapshot(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Export all analysis results for a snapshot in a single JSON payload.

    Includes symbols, edges, summaries, and generated documents.
    Useful for offline analysis, CI/CD pipelines, and integrations.
    """
    snap = await _verify_snapshot(db, repo_id, snapshot_id)

    # Symbols
    sym_result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id).order_by(Symbol.file_path)
    )
    symbols = [
        {
            "fq_name": s.fq_name,
            "name": s.name,
            "kind": s.kind,
            "file_path": s.file_path,
            "start_line": s.start_line,
            "end_line": s.end_line,
            "namespace": s.namespace or "",
            "parent_fq_name": s.parent_fq_name or "",
            "signature": s.signature or "",
            "modifiers": s.modifiers or "",
            "return_type": s.return_type or "",
        }
        for s in sym_result.scalars().all()
    ]

    # Edges
    edge_result = await db.execute(
        select(Edge).where(Edge.snapshot_id == snapshot_id)
    )
    edges = [
        {
            "source_fq_name": e.source_fq_name,
            "target_fq_name": e.target_fq_name,
            "edge_type": e.edge_type,
            "file_path": e.file_path or "",
            "line": e.line or 0,
        }
        for e in edge_result.scalars().all()
    ]

    # Summaries
    sum_result = await db.execute(
        select(Summary).where(Summary.snapshot_id == snapshot_id)
    )
    summaries = []
    for s in sum_result.scalars().all():
        try:
            parsed = json.loads(s.summary_json)
        except (json.JSONDecodeError, TypeError):
            parsed = {}
        summaries.append(
            {
                "scope_type": s.scope_type,
                "scope_id": s.scope_id,
                "summary": parsed,
            }
        )

    # Docs
    doc_result = await db.execute(
        select(GeneratedDoc).where(GeneratedDoc.snapshot_id == snapshot_id)
    )
    docs = [
        {
            "doc_type": d.doc_type,
            "title": d.title,
            "scope_id": d.scope_id,
            "markdown": d.markdown,
        }
        for d in doc_result.scalars().all()
    ]

    return ExportResponse(
        snapshot_id=snapshot_id,
        symbols=symbols,
        edges=edges,
        summaries=summaries,
        docs=docs,
        metadata={
            "commit_sha": snap.commit_sha or "",
            "file_count": snap.file_count,
            "symbol_count": len(symbols),
            "edge_count": len(edges),
            "summary_count": len(summaries),
            "doc_count": len(docs),
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _verify_snapshot(
    db: AsyncSession, repo_id: str, snapshot_id: str
) -> RepoSnapshot:
    result = await db.execute(
        select(RepoSnapshot).where(
            RepoSnapshot.id == snapshot_id,
            RepoSnapshot.repo_id == repo_id,
        )
    )
    snap = result.scalar_one_or_none()
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snap


async def _get_symbol_map(db: AsyncSession, snapshot_id: str) -> dict[str, dict[str, Any]]:
    """Build a fq_name -> symbol dict for comparison."""
    result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id)
    )
    return {
        s.fq_name: {
            "kind": s.kind,
            "file_path": s.file_path,
            "start_line": s.start_line,
            "end_line": s.end_line,
            "signature": s.signature or "",
        }
        for s in result.scalars().all()
    }


def _score_symbol(symbol: Symbol, query: str) -> float:
    """Simple relevance scoring for symbol search."""
    q = query.lower()
    score = 0.0
    if q == symbol.name.lower():
        score += 10.0
    elif q in symbol.name.lower():
        score += 5.0
    if q in (symbol.fq_name or "").lower():
        score += 3.0
    if q in (symbol.namespace or "").lower():
        score += 1.0
    return max(score, 0.1)


def _score_text(text: str, query: str) -> float:
    """Simple relevance scoring for text search."""
    q = query.lower()
    t = text.lower()
    if q == t:
        return 10.0
    if q in t:
        return 5.0
    return 0.1
