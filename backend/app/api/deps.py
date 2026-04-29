"""API endpoints for dependency analysis."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_snapshot
from app.storage.database import get_db
from app.storage.models import Dependency, RepoSnapshot

router = APIRouter()


class DependencyOut(BaseModel):
    id: int
    name: str
    version: str
    ecosystem: str
    file_path: str
    is_dev: bool
    is_pinned: bool


class EcosystemSummary(BaseModel):
    ecosystem: str
    total: int
    pinned: int
    unpinned: int
    dev: int
    production: int


class DependencyReport(BaseModel):
    snapshot_id: str
    total: int
    ecosystems: list[EcosystemSummary]
    items: list[DependencyOut]


class UnusedDep(BaseModel):
    name: str
    ecosystem: str
    file_path: str
    version: str


class UnusedReport(BaseModel):
    snapshot_id: str
    total_declared: int
    unused: list[UnusedDep]


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/dependencies",
    response_model=DependencyReport,
    summary="List all declared dependencies",
)
async def list_dependencies(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> DependencyReport:
    """Return all dependencies parsed from manifest files."""
    result = await db.execute(
        select(Dependency)
        .where(Dependency.snapshot_id == snapshot_id)
        .order_by(Dependency.ecosystem, Dependency.name)
    )
    deps = list(result.scalars().all())

    # Build ecosystem summaries
    eco_data: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "pinned": 0, "unpinned": 0, "dev": 0, "prod": 0}
    )
    items = []
    for d in deps:
        e = eco_data[d.ecosystem]
        e["total"] += 1
        if d.is_pinned:
            e["pinned"] += 1
        else:
            e["unpinned"] += 1
        if d.is_dev:
            e["dev"] += 1
        else:
            e["prod"] += 1
        items.append(DependencyOut(
            id=d.id,
            name=d.name,
            version=d.version,
            ecosystem=d.ecosystem,
            file_path=d.file_path,
            is_dev=d.is_dev,
            is_pinned=d.is_pinned,
        ))

    ecosystems = [
        EcosystemSummary(
            ecosystem=eco,
            total=data["total"],
            pinned=data["pinned"],
            unpinned=data["unpinned"],
            dev=data["dev"],
            production=data["prod"],
        )
        for eco, data in sorted(eco_data.items())
    ]

    return DependencyReport(
        snapshot_id=snapshot_id,
        total=len(items),
        ecosystems=ecosystems,
        items=items,
    )
