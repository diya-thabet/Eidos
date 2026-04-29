"""API endpoint for dead code analysis."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.dead_code import analyze_dead_code
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import (
    EdgeInfo,
    EdgeType,
    SymbolInfo,
    SymbolKind,
)
from app.api.dependencies import verify_snapshot
from app.storage.database import get_db
from app.storage.models import Edge, RepoSnapshot, Symbol

router = APIRouter()


class DeadSymbolOut(BaseModel):
    fq_name: str
    name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int


class DeadModuleOut(BaseModel):
    module: str
    file_count: int
    symbol_count: int
    files: list[str]


class DeadImportOut(BaseModel):
    source_file: str
    target: str
    line: int


class DeadCodeResponse(BaseModel):
    snapshot_id: str
    total_symbols: int
    reachable_count: int
    unreachable_count: int
    entry_point_count: int
    unreachable_functions: list[DeadSymbolOut]
    unreachable_classes: list[DeadSymbolOut]
    unreachable_modules: list[DeadModuleOut]
    dead_imports: list[DeadImportOut]


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/dead-code",
    response_model=DeadCodeResponse,
    summary="Detect dead code via graph reachability",
)
async def get_dead_code(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> DeadCodeResponse:
    """BFS from entry points to find unreachable symbols."""
    # Rebuild a lightweight CodeGraph from DB
    graph = await _build_graph_from_db(db, snapshot_id)
    report = analyze_dead_code(graph)

    return DeadCodeResponse(
        snapshot_id=snapshot_id,
        total_symbols=report.total_symbols,
        reachable_count=report.reachable_count,
        unreachable_count=report.unreachable_count,
        entry_point_count=report.entry_point_count,
        unreachable_functions=[
            DeadSymbolOut(
                fq_name=s.fq_name, name=s.name, kind=s.kind,
                file_path=s.file_path,
                start_line=s.start_line, end_line=s.end_line,
            )
            for s in report.unreachable_functions
        ],
        unreachable_classes=[
            DeadSymbolOut(
                fq_name=s.fq_name, name=s.name, kind=s.kind,
                file_path=s.file_path,
                start_line=s.start_line, end_line=s.end_line,
            )
            for s in report.unreachable_classes
        ],
        unreachable_modules=[
            DeadModuleOut(
                module=m.module, file_count=m.file_count,
                symbol_count=m.symbol_count, files=m.files,
            )
            for m in report.unreachable_modules
        ],
        dead_imports=[
            DeadImportOut(
                source_file=i.source_file, target=i.target,
                line=i.line,
            )
            for i in report.dead_imports
        ],
    )


async def _build_graph_from_db(
    db: AsyncSession, snapshot_id: str,
) -> CodeGraph:
    """Reconstruct a CodeGraph from persisted symbols and edges."""
    sym_result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id)
    )
    edge_result = await db.execute(
        select(Edge).where(Edge.snapshot_id == snapshot_id)
    )

    graph = CodeGraph()
    for s in sym_result.scalars():
        mods = s.modifiers.split(",") if s.modifiers else []
        kind_val = (
            SymbolKind(s.kind)
            if s.kind in SymbolKind.__members__.values()
            else SymbolKind.METHOD
        )
        si = SymbolInfo(
            name=s.name,
            kind=kind_val,
            fq_name=s.fq_name,
            file_path=s.file_path,
            start_line=s.start_line,
            end_line=s.end_line,
            namespace=s.namespace or "",
            parent_fq_name=s.parent_fq_name,
            signature=s.signature or "",
            modifiers=mods,
            return_type=s.return_type or "",
        )
        graph.symbols[s.fq_name] = si

    for e in edge_result.scalars():
        try:
            et = EdgeType(e.edge_type)
        except ValueError:
            et = EdgeType.USES
        graph.edges.append(EdgeInfo(
            source_fq_name=e.source_fq_name,
            target_fq_name=e.target_fq_name,
            edge_type=et,
            file_path=e.file_path or "",
            line=e.line or 0,
        ))

    graph.finalize()
    return graph
