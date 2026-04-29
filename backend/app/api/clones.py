"""API endpoint for clone / duplicate detection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.clone_detection import (
    MIN_FUNC_LINES,
    CloneInfo,
    detect_clones,
)
from app.api.dependencies import verify_snapshot
from app.storage.database import get_db
from app.storage.models import RepoSnapshot, Symbol

router = APIRouter()


# -----------------------------------------------------------------------
# Response models
# -----------------------------------------------------------------------


class CloneMemberOut(BaseModel):
    fq_name: str
    name: str
    file_path: str
    start_line: int
    end_line: int
    lines: int


class CloneGroupOut(BaseModel):
    fingerprint: str
    count: int
    members: list[CloneMemberOut]


class NearClonePairOut(BaseModel):
    a: CloneMemberOut
    b: CloneMemberOut
    similarity: float


class ClonesResponse(BaseModel):
    snapshot_id: str
    total_functions_analyzed: int
    exact_clone_groups: list[CloneGroupOut]
    near_clone_pairs: list[NearClonePairOut]
    total_exact_clones: int
    total_near_clones: int


# -----------------------------------------------------------------------
# Endpoint
# -----------------------------------------------------------------------

# Reuse pipeline's tree-sitter language cache
_FUNC_NODE_TYPES: frozenset[str] = frozenset({
    "function_definition", "method_declaration",
    "constructor_declaration", "function_declaration",
    "method_definition", "arrow_function", "function_item",
})


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/clones",
    response_model=ClonesResponse,
    summary="Detect code clones via AST fingerprinting",
)
async def get_clones(
    repo_id: str,
    snapshot_id: str,
    near_clones: bool = Query(
        False, description="Also detect near-clones (slower)",
    ),
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> ClonesResponse:
    """Detect exact and near code clones."""
    result = await db.execute(
        select(Symbol)
        .where(
            Symbol.snapshot_id == snapshot_id,
            Symbol.kind.in_(["method", "constructor"]),
        )
    )
    symbols = list(result.scalars().all())

    # Build CloneInfo list from DB metadata_json or re-compute
    functions: list[CloneInfo] = []
    for s in symbols:
        lines = s.end_line - s.start_line + 1
        if lines < MIN_FUNC_LINES:
            continue
        # Use stored fingerprint from metadata or generate placeholder
        fp = ""
        if s.metadata_json:
            import json
            try:
                meta = json.loads(s.metadata_json)
                fp = meta.get("structural_fingerprint", "")
            except Exception:
                pass
        if not fp:
            # Generate a unique placeholder (no clone detection possible
            # without the actual AST, but the data is still useful)
            fp = f"nofp_{s.id}"
        functions.append(CloneInfo(
            fq_name=s.fq_name,
            name=s.name,
            file_path=s.file_path,
            start_line=s.start_line,
            end_line=s.end_line,
            lines=lines,
            fingerprint=fp,
        ))

    report = detect_clones(functions)

    return ClonesResponse(
        snapshot_id=snapshot_id,
        total_functions_analyzed=report.total_functions,
        exact_clone_groups=[
            CloneGroupOut(
                fingerprint=g.fingerprint,
                count=len(g.members),
                members=[
                    CloneMemberOut(
                        fq_name=m.fq_name, name=m.name,
                        file_path=m.file_path,
                        start_line=m.start_line,
                        end_line=m.end_line, lines=m.lines,
                    )
                    for m in g.members
                ],
            )
            for g in report.exact_clone_groups
        ],
        near_clone_pairs=[
            NearClonePairOut(
                a=CloneMemberOut(
                    fq_name=p.a.fq_name, name=p.a.name,
                    file_path=p.a.file_path,
                    start_line=p.a.start_line,
                    end_line=p.a.end_line, lines=p.a.lines,
                ),
                b=CloneMemberOut(
                    fq_name=p.b.fq_name, name=p.b.name,
                    file_path=p.b.file_path,
                    start_line=p.b.start_line,
                    end_line=p.b.end_line, lines=p.b.lines,
                ),
                similarity=p.similarity,
            )
            for p in report.near_clone_pairs
        ],
        total_exact_clones=report.total_exact_clones,
        total_near_clones=report.total_near_clones,
    )
