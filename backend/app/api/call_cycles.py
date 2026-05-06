"""API endpoint for function-level call cycle detection."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.call_cycles import detect_call_cycles
from app.api.dependencies import verify_snapshot
from app.auth.scopes import require_scope
from app.storage.database import get_db
from app.storage.models import Edge, RepoSnapshot, Symbol

router = APIRouter(dependencies=[Depends(require_scope("read:analysis"))])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CallCycleOut(BaseModel):
    members: list[str]
    size: int
    cycle_path: list[str]
    files: list[str]


class CallCycleReportOut(BaseModel):
    snapshot_id: str
    total_cycles: int
    direct_recursion_count: int
    mutual_recursion_count: int
    largest_cycle_size: int
    cycles: list[CallCycleOut]
    direct_recursions: list[str]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/call-cycles",
    response_model=CallCycleReportOut,
    summary="Detect function-level call cycles (Tarjan's SCC)",
)
async def get_call_cycles(
    repo_id: str,
    snapshot_id: str,
    min_cycle_size: int = Query(2, ge=2, le=100, description="Minimum cycle size"),
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> CallCycleReportOut:
    """Detect call cycles in the function call graph.

    Uses Tarjan's strongly connected components algorithm to find:
    - Direct recursion (function calls itself)
    - Mutual recursion (A calls B calls A)
    - Large cycles (potential architecture issues)
    """
    # Build adjacency from call edges
    edge_result = await db.execute(
        select(Edge).where(
            Edge.snapshot_id == snapshot_id,
            Edge.edge_type == "calls",
        )
    )
    edges = edge_result.scalars().all()

    callees: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        callees[edge.source_fq_name].append(edge.target_fq_name)

    # Build symbol -> file mapping
    sym_result = await db.execute(
        select(Symbol.fq_name, Symbol.file_path).where(
            Symbol.snapshot_id == snapshot_id,
        )
    )
    symbol_files = {row[0]: row[1] for row in sym_result.all()}

    # Detect cycles
    report = detect_call_cycles(dict(callees), symbol_files)

    # Filter by min_cycle_size
    filtered_cycles = [c for c in report.cycles if c.size >= min_cycle_size]

    return CallCycleReportOut(
        snapshot_id=snapshot_id,
        total_cycles=len(filtered_cycles),
        direct_recursion_count=report.direct_recursion_count,
        mutual_recursion_count=report.mutual_recursion_count,
        largest_cycle_size=report.largest_cycle_size,
        cycles=[
            CallCycleOut(
                members=c.members,
                size=c.size,
                cycle_path=c.cycle_path,
                files=c.files,
            )
            for c in filtered_cycles
        ],
        direct_recursions=report.direct_recursions,
    )
