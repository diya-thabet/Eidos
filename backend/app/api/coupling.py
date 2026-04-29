"""API endpoint for module coupling and cohesion metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.coupling import analyze_coupling
from app.api.dead_code import _build_graph_from_db
from app.api.dependencies import verify_snapshot
from app.storage.database import get_db
from app.storage.models import RepoSnapshot

router = APIRouter()


class ModuleMetricsOut(BaseModel):
    name: str
    file_count: int
    symbol_count: int
    class_count: int
    abstract_count: int
    method_count: int
    afferent_coupling: int
    efferent_coupling: int
    instability: float
    abstractness: float
    distance: float
    intra_edges: int
    inter_edges: int
    cohesion: float
    depends_on: list[str]
    depended_by: list[str]


class CouplingResponse(BaseModel):
    snapshot_id: str
    total_modules: int
    avg_instability: float
    avg_cohesion: float
    avg_distance: float
    dependency_cycles: list[list[str]]
    modules: list[ModuleMetricsOut]


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/coupling",
    response_model=CouplingResponse,
    summary="Module coupling and cohesion metrics",
)
async def get_coupling(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> CouplingResponse:
    """Compute Robert C. Martin package metrics per module."""
    graph = await _build_graph_from_db(db, snapshot_id)
    report = analyze_coupling(graph)

    return CouplingResponse(
        snapshot_id=snapshot_id,
        total_modules=report.total_modules,
        avg_instability=report.avg_instability,
        avg_cohesion=report.avg_cohesion,
        avg_distance=report.avg_distance,
        dependency_cycles=report.dependency_cycles,
        modules=[
            ModuleMetricsOut(
                name=m.name,
                file_count=m.file_count,
                symbol_count=m.symbol_count,
                class_count=m.class_count,
                abstract_count=m.abstract_count,
                method_count=m.method_count,
                afferent_coupling=m.afferent_coupling,
                efferent_coupling=m.efferent_coupling,
                instability=round(m.instability, 3),
                abstractness=round(m.abstractness, 3),
                distance=round(m.distance, 3),
                intra_edges=m.intra_edges,
                inter_edges=m.inter_edges,
                cohesion=round(m.cohesion, 3),
                depends_on=m.depends_on,
                depended_by=m.depended_by,
            )
            for m in report.modules
        ],
    )
