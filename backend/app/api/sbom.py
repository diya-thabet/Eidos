"""API endpoints for SBOM (Software Bill of Materials) export."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_snapshot
from app.auth.scopes import require_scope
from app.exports.sbom import generate_cyclonedx, generate_spdx
from app.storage.database import get_db
from app.storage.models import Dependency, Repo, RepoSnapshot

router = APIRouter(dependencies=[Depends(require_scope("read:export"))])


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/export/sbom",
    summary="Generate SBOM (CycloneDX or SPDX)",
    responses={
        200: {"content": {"application/json": {}}},
    },
)
async def export_sbom(
    repo_id: str,
    snapshot_id: str,
    format: str = Query(
        default="cyclonedx",
        description="SBOM format: 'cyclonedx' or 'spdx'",
    ),
    include_dev: bool = Query(
        default=True,
        description="Include dev dependencies",
    ),
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> JSONResponse:
    """Generate a Software Bill of Materials from parsed dependencies.

    Supports CycloneDX 1.5 and SPDX 2.3 output formats.
    """
    if format not in ("cyclonedx", "spdx"):
        raise HTTPException(
            status_code=400,
            detail="Format must be 'cyclonedx' or 'spdx'",
        )

    # Get repo name
    repo = await db.get(Repo, repo_id)
    repo_name = repo.name if repo else repo_id

    # Get dependencies
    stmt = select(Dependency).where(Dependency.snapshot_id == snapshot_id)
    if not include_dev:
        stmt = stmt.where(Dependency.is_dev.is_(False))

    result = await db.execute(stmt)
    deps = result.scalars().all()

    dep_dicts = [
        {
            "name": d.name,
            "version": d.version,
            "ecosystem": d.ecosystem,
            "is_dev": d.is_dev,
            "file_path": d.file_path,
        }
        for d in deps
    ]

    if format == "spdx":
        sbom = generate_spdx(repo_name, snapshot_id, dep_dicts)
        filename = f"{repo_name}-{snapshot_id[:8]}-spdx.json"
    else:
        sbom = generate_cyclonedx(repo_name, snapshot_id, dep_dicts)
        filename = f"{repo_name}-{snapshot_id[:8]}-cyclonedx.json"

    return JSONResponse(
        content=sbom,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
