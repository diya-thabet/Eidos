"""
API endpoints for static analysis results.

Provides access to symbols, edges, call graph neighborhoods,
entry points, metrics, and modules for a given snapshot.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_db
from app.storage.models import Edge, RepoSnapshot, Symbol
from app.storage.schemas import (
    AnalysisOverview,
    EdgeOut,
    EntryPointOut,
    GraphNeighborhood,
    MetricsOut,
    ModuleOut,
    SymbolOut,
)

router = APIRouter()


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/symbols",
    response_model=list[SymbolOut],
    summary="List symbols in a snapshot",
)
async def list_symbols(
    repo_id: str,
    snapshot_id: str,
    kind: str | None = Query(None, description="Filter by symbol kind (class, method, etc.)"),
    file_path: str | None = Query(None, description="Filter by file path"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    await _verify_snapshot(db, repo_id, snapshot_id)
    stmt = select(Symbol).where(Symbol.snapshot_id == snapshot_id)
    if kind:
        stmt = stmt.where(Symbol.kind == kind)
    if file_path:
        stmt = stmt.where(Symbol.file_path == file_path)
    stmt = stmt.order_by(Symbol.file_path, Symbol.start_line).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/symbols/{fq_name:path}",
    response_model=SymbolOut,
    summary="Get a specific symbol by fully-qualified name",
)
async def get_symbol(
    repo_id: str,
    snapshot_id: str,
    fq_name: str,
    db: AsyncSession = Depends(get_db),
):
    await _verify_snapshot(db, repo_id, snapshot_id)
    result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id, Symbol.fq_name == fq_name)
    )
    sym = result.scalar_one_or_none()
    if sym is None:
        raise HTTPException(status_code=404, detail=f"Symbol not found: {fq_name}")
    return sym


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/edges",
    response_model=list[EdgeOut],
    summary="List edges in a snapshot",
)
async def list_edges(
    repo_id: str,
    snapshot_id: str,
    edge_type: str | None = Query(None, description="Filter by edge type (calls, inherits, etc.)"),
    source: str | None = Query(None, description="Filter by source symbol fq_name"),
    target: str | None = Query(None, description="Filter by target symbol fq_name"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    await _verify_snapshot(db, repo_id, snapshot_id)
    stmt = select(Edge).where(Edge.snapshot_id == snapshot_id)
    if edge_type:
        stmt = stmt.where(Edge.edge_type == edge_type)
    if source:
        stmt = stmt.where(Edge.source_fq_name == source)
    if target:
        stmt = stmt.where(Edge.target_fq_name == target)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/graph/{fq_name:path}",
    response_model=GraphNeighborhood,
    summary="Get call graph neighborhood for a symbol",
)
async def get_graph_neighborhood(
    repo_id: str,
    snapshot_id: str,
    fq_name: str,
    db: AsyncSession = Depends(get_db),
):
    await _verify_snapshot(db, repo_id, snapshot_id)

    # Get the symbol itself
    result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id, Symbol.fq_name == fq_name)
    )
    sym = result.scalar_one_or_none()
    if sym is None:
        raise HTTPException(status_code=404, detail=f"Symbol not found: {fq_name}")

    # Get callers (edges where target = this symbol)
    callers = await _resolve_edge_symbols(db, snapshot_id, Edge.target_fq_name, fq_name, Edge.source_fq_name)
    # Get callees (edges where source = this symbol)
    callees = await _resolve_edge_symbols(db, snapshot_id, Edge.source_fq_name, fq_name, Edge.target_fq_name)
    # Get children (containment edges)
    children = await _resolve_edge_symbols(
        db, snapshot_id, Edge.source_fq_name, fq_name, Edge.target_fq_name, edge_type="contains"
    )

    return GraphNeighborhood(symbol=sym, callers=callers, callees=callees, children=children)


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/overview",
    response_model=AnalysisOverview,
    summary="Get analysis overview for a snapshot",
)
async def get_analysis_overview(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
):
    await _verify_snapshot(db, repo_id, snapshot_id)

    # Count symbols by kind
    result = await db.execute(
        select(Symbol.kind, func.count()).where(Symbol.snapshot_id == snapshot_id).group_by(Symbol.kind)
    )
    kind_counts = {row[0]: row[1] for row in result.all()}
    total_symbols = sum(kind_counts.values())

    # Count edges
    result = await db.execute(
        select(func.count()).where(Edge.snapshot_id == snapshot_id)
    )
    total_edges = result.scalar() or 0

    # Count distinct namespaces as modules
    result = await db.execute(
        select(func.count(func.distinct(Symbol.namespace))).where(
            Symbol.snapshot_id == snapshot_id, Symbol.namespace != ""
        )
    )
    total_modules = result.scalar() or 0

    return AnalysisOverview(
        snapshot_id=snapshot_id,
        total_symbols=total_symbols,
        total_edges=total_edges,
        total_modules=total_modules,
        symbols_by_kind=kind_counts,
        entry_points=[],  # Populated by the analysis task, queried separately
        hotspots=[],       # Same
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _verify_snapshot(db: AsyncSession, repo_id: str, snapshot_id: str) -> RepoSnapshot:
    """Verify snapshot exists and belongs to the repo."""
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


async def _resolve_edge_symbols(
    db: AsyncSession,
    snapshot_id: str,
    filter_col,
    filter_val: str,
    resolve_col,
    edge_type: str = "calls",
) -> list[Symbol]:
    """Find symbols connected via edges of a given type."""
    edge_result = await db.execute(
        select(resolve_col).where(
            Edge.snapshot_id == snapshot_id,
            filter_col == filter_val,
            Edge.edge_type == edge_type,
        ).distinct()
    )
    fq_names = [row[0] for row in edge_result.all()]
    if not fq_names:
        return []
    result = await db.execute(
        select(Symbol).where(
            Symbol.snapshot_id == snapshot_id,
            Symbol.fq_name.in_(fq_names),
        )
    )
    return list(result.scalars().all())
