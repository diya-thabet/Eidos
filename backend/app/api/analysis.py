"""
API endpoints for static analysis results.

Provides access to symbols, edges, call graph neighborhoods,
entry points, metrics, modules, and code health checks for a given snapshot.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.database import get_db
from app.storage.models import Edge, RepoSnapshot, Symbol
from app.storage.schemas import (
    AnalysisOverview,
    EdgeOut,
    GraphNeighborhood,
    PaginatedResponse,
    SymbolOut,
)

router = APIRouter()


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/symbols",
    response_model=PaginatedResponse,
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
) -> Any:
    await _verify_snapshot(db, repo_id, snapshot_id)
    base = select(Symbol).where(Symbol.snapshot_id == snapshot_id)
    if kind:
        base = base.where(Symbol.kind == kind)
    if file_path:
        base = base.where(Symbol.file_path == file_path)

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    stmt = base.order_by(Symbol.file_path, Symbol.start_line).offset(offset).limit(limit)
    result = await db.execute(stmt)
    items = [SymbolOut.model_validate(s) for s in result.scalars().all()]
    return PaginatedResponse(
        items=items, total=total, limit=limit, offset=offset, has_more=(offset + limit < total)
    )


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
) -> Any:
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
    response_model=PaginatedResponse,
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
) -> Any:
    await _verify_snapshot(db, repo_id, snapshot_id)
    base = select(Edge).where(Edge.snapshot_id == snapshot_id)
    if edge_type:
        base = base.where(Edge.edge_type == edge_type)
    if source:
        base = base.where(Edge.source_fq_name == source)
    if target:
        base = base.where(Edge.target_fq_name == target)

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    stmt = base.offset(offset).limit(limit)
    result = await db.execute(stmt)
    items = [EdgeOut.model_validate(e) for e in result.scalars().all()]
    return PaginatedResponse(
        items=items, total=total, limit=limit, offset=offset, has_more=(offset + limit < total)
    )


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
) -> Any:
    await _verify_snapshot(db, repo_id, snapshot_id)

    # Get the symbol itself
    result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id, Symbol.fq_name == fq_name)
    )
    sym = result.scalar_one_or_none()
    if sym is None:
        raise HTTPException(status_code=404, detail=f"Symbol not found: {fq_name}")

    # Get callers (edges where target = this symbol)
    callers = await _resolve_edge_symbols(
        db, snapshot_id, Edge.target_fq_name, fq_name, Edge.source_fq_name
    )
    # Get callees (edges where source = this symbol)
    callees = await _resolve_edge_symbols(
        db, snapshot_id, Edge.source_fq_name, fq_name, Edge.target_fq_name
    )
    # Get children (containment edges)
    children = await _resolve_edge_symbols(
        db, snapshot_id, Edge.source_fq_name, fq_name, Edge.target_fq_name, edge_type="contains"
    )

    return GraphNeighborhood(
        symbol=sym,  # type: ignore[arg-type]
        callers=callers,  # type: ignore[arg-type]
        callees=callees,  # type: ignore[arg-type]
        children=children,  # type: ignore[arg-type]
    )


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/overview",
    response_model=AnalysisOverview,
    summary="Get analysis overview for a snapshot",
)
async def get_analysis_overview(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    await _verify_snapshot(db, repo_id, snapshot_id)

    # Count symbols by kind
    result = await db.execute(
        select(Symbol.kind, func.count())
        .where(Symbol.snapshot_id == snapshot_id)
        .group_by(Symbol.kind)
    )
    kind_counts = {row[0]: row[1] for row in result.all()}
    total_symbols = sum(kind_counts.values())

    # Count edges
    result = await db.execute(select(func.count()).where(Edge.snapshot_id == snapshot_id))
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
        hotspots=[],  # Same
    )


# ---------------------------------------------------------------------------
# Code Health
# ---------------------------------------------------------------------------


class HealthCheckRequest(BaseModel):
    """Request body for code health analysis."""

    categories: list[str] = []
    disabled_rules: list[str] = []
    max_method_lines: int = 30
    max_class_lines: int = 300
    max_parameters: int = 5
    max_fan_out: int = 10
    max_fan_in: int = 15
    max_children: int = 20
    max_inheritance_depth: int = 4
    max_god_class_methods: int = 15
    use_llm: bool = False


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/health/rules",
    summary="List all available code health rules",
)
async def list_health_rules() -> Any:
    from app.analysis.code_health import HealthConfig

    return HealthConfig.all_rules()


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/health",
    summary="Run code health analysis on a snapshot",
)
async def run_health_analysis(
    repo_id: str,
    snapshot_id: str,
    body: HealthCheckRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    await _verify_snapshot(db, repo_id, snapshot_id)

    from app.analysis.code_health import HealthConfig, run_health_check, run_llm_health_analysis
    from app.analysis.graph_builder import CodeGraph
    from app.analysis.models import EdgeInfo, EdgeType, SymbolInfo, SymbolKind

    # Rebuild graph from DB
    graph = CodeGraph()

    sym_result = await db.execute(select(Symbol).where(Symbol.snapshot_id == snapshot_id))
    for s in sym_result.scalars().all():
        si = SymbolInfo(
            name=s.name,
            kind=SymbolKind(s.kind),
            fq_name=s.fq_name,
            file_path=s.file_path,
            start_line=s.start_line,
            end_line=s.end_line,
            namespace=s.namespace or "",
            parent_fq_name=s.parent_fq_name,
            signature=s.signature or "",
            modifiers=s.modifiers.split(",") if s.modifiers else [],
            return_type=s.return_type or "",
        )
        graph.symbols[si.fq_name] = si

    edge_result = await db.execute(select(Edge).where(Edge.snapshot_id == snapshot_id))
    for e in edge_result.scalars().all():
        graph.edges.append(
            EdgeInfo(
                source_fq_name=e.source_fq_name,
                target_fq_name=e.target_fq_name,
                edge_type=EdgeType(e.edge_type),
                file_path=e.file_path or "",
                line=e.line or 0,
            )
        )

    graph.finalize()

    # Build config from request
    if body:
        config = HealthConfig(
            categories=body.categories,
            disabled_rules=body.disabled_rules,
            max_method_lines=body.max_method_lines,
            max_class_lines=body.max_class_lines,
            max_parameters=body.max_parameters,
            max_fan_out=body.max_fan_out,
            max_fan_in=body.max_fan_in,
            max_children=body.max_children,
            max_inheritance_depth=body.max_inheritance_depth,
            max_god_class_methods=body.max_god_class_methods,
            use_llm=body.use_llm,
        )
    else:
        config = HealthConfig()

    report = run_health_check(graph, config)

    # Optional LLM enrichment
    if config.use_llm:
        from app.core.config import settings
        from app.reasoning.llm_client import LLMConfig, OpenAICompatibleClient

        if settings.llm_base_url:
            llm = OpenAICompatibleClient(
                LLMConfig(
                    base_url=settings.llm_base_url,
                    api_key=settings.llm_api_key,
                    model=settings.llm_model,
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    timeout=settings.llm_timeout,
                )
            )
            report.llm_insights = await run_llm_health_analysis(graph, report, llm)

    return report.to_dict()


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


async def _resolve_edge_symbols(  # type: ignore[no-untyped-def]
    db: AsyncSession,
    snapshot_id: str,
    filter_col,
    filter_val: str,
    resolve_col,
    edge_type: str = "calls",
) -> list[Symbol]:
    """Find symbols connected via edges of a given type."""
    edge_result = await db.execute(
        select(resolve_col)
        .where(
            Edge.snapshot_id == snapshot_id,
            filter_col == filter_val,
            Edge.edge_type == edge_type,
        )
        .distinct()
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
