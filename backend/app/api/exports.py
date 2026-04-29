"""API endpoints for export: CSV (ZIP), SARIF, Markdown report."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_snapshot
from app.exports.generators import (
    generate_csv_zip,
    generate_markdown_report,
    generate_sarif,
)
from app.storage.database import get_db
from app.storage.models import Edge, File, Repo, RepoSnapshot, Symbol

router = APIRouter()


async def _load_export_data(
    db: AsyncSession, snapshot_id: str,
) -> dict[str, Any]:
    """Load symbols, edges, files from DB for export."""
    sym_result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id)
    )
    edge_result = await db.execute(
        select(Edge).where(Edge.snapshot_id == snapshot_id)
    )
    file_result = await db.execute(
        select(File).where(File.snapshot_id == snapshot_id)
    )

    symbols = [
        {
            "fq_name": s.fq_name, "name": s.name, "kind": s.kind,
            "file_path": s.file_path, "start_line": s.start_line,
            "end_line": s.end_line, "namespace": s.namespace or "",
            "cyclomatic_complexity": s.cyclomatic_complexity or 0,
            "cognitive_complexity": s.cognitive_complexity or 0,
            "last_author": s.last_author or "",
            "author_count": s.author_count or 0,
            "commit_count": s.commit_count or 0,
        }
        for s in sym_result.scalars().all()
    ]
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
    files = list(file_result.scalars().all())

    return {
        "symbols": symbols,
        "edges": edges,
        "files": files,
        "file_count": len(files),
    }


def _mock_health_findings(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate basic health findings from symbol data for export."""
    findings: list[dict[str, Any]] = []
    for s in symbols:
        if s.get("kind") not in ("method", "constructor"):
            continue
        cc = s.get("cyclomatic_complexity", 0)
        if cc >= 15:
            findings.append({
                "rule_id": "CC001",
                "rule_name": "high_cyclomatic_complexity",
                "category": "complexity",
                "severity": "warning",
                "symbol_fq_name": s["fq_name"],
                "file_path": s["file_path"],
                "line": s["start_line"],
                "message": f"Cyclomatic complexity {cc} exceeds threshold",
            })
        cog = s.get("cognitive_complexity", 0)
        if cog >= 20:
            findings.append({
                "rule_id": "CC002",
                "rule_name": "high_cognitive_complexity",
                "category": "complexity",
                "severity": "warning",
                "symbol_fq_name": s["fq_name"],
                "file_path": s["file_path"],
                "line": s["start_line"],
                "message": f"Cognitive complexity {cog} exceeds threshold",
            })
    return findings


# -----------------------------------------------------------------------
# CSV Export
# -----------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/export/csv",
    summary="Export snapshot as CSV (ZIP)",
    responses={200: {"content": {"application/zip": {}}}},
)
async def export_csv(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> Response:
    """Download a ZIP with symbols.csv, edges.csv, health_findings.csv."""
    data = await _load_export_data(db, snapshot_id)
    findings = _mock_health_findings(data["symbols"])

    zip_bytes = generate_csv_zip(
        symbols=data["symbols"],
        edges=data["edges"],
        health_findings=findings,
    )

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="eidos-{snapshot_id}.zip"'
            ),
        },
    )


# -----------------------------------------------------------------------
# SARIF Export
# -----------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/export/sarif",
    summary="Export health findings as SARIF 2.1.0",
)
async def export_sarif(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> dict[str, Any]:
    """SARIF output for GitHub Code Scanning / VS Code integration."""
    data = await _load_export_data(db, snapshot_id)
    findings = _mock_health_findings(data["symbols"])
    return generate_sarif(health_findings=findings)


# -----------------------------------------------------------------------
# Markdown Report
# -----------------------------------------------------------------------


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/export/markdown",
    summary="Export health report as Markdown",
    responses={200: {"content": {"text/markdown": {}}}},
)
async def export_markdown(
    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snapshot: RepoSnapshot = Depends(verify_snapshot),
) -> Response:
    """Download a Markdown health report."""
    data = await _load_export_data(db, snapshot_id)
    findings = _mock_health_findings(data["symbols"])

    # Get repo name
    snapshot = await db.get(RepoSnapshot, snapshot_id)
    repo = await db.get(Repo, snapshot.repo_id) if snapshot else None
    repo_name = repo.name if repo else repo_id

    top_complex = sorted(
        [s for s in data["symbols"] if s.get("kind") in ("method", "constructor")],
        key=lambda s: s.get("cyclomatic_complexity", 0),
        reverse=True,
    )[:15]

    md = generate_markdown_report(
        snapshot_id=snapshot_id,
        repo_name=repo_name,
        symbol_count=len(data["symbols"]),
        file_count=data["file_count"],
        edge_count=len(data["edges"]),
        health_findings=findings,
        top_complex=top_complex,
    )

    return Response(
        content=md,
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                f'attachment; filename="eidos-report-{snapshot_id}.md"'
            ),
        },
    )
