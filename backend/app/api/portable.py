"""

Portable snapshot export and import.

Provides endpoints to:

- Export a snapshot as a compact ``.eidos`` file (gzip'd JSON)

- Import a ``.eidos`` file to restore a snapshot without re-running ingestion

The ``.eidos`` format:

- gzip-compressed JSON

- Contains a schema version for forward compatibility

- Includes: metadata, files, symbols, edges, summaries, docs, evaluations

- Typically 80-90% smaller than raw JSON

"""

from __future__ import annotations

import gzip
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_snapshot
from app.storage.database import get_db
from app.storage.models import (
    Edge,
    Evaluation,
    File,
    GeneratedDoc,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Summary,
    Symbol,
)

router = APIRouter()

# Schema version -- bump when the export format changes

PORTABLE_SCHEMA_VERSION = 1

# Maximum upload size: 200 MB

MAX_UPLOAD_BYTES = 200 * 1024 * 1024

# ---------------------------------------------------------------------------

# Schemas

# ---------------------------------------------------------------------------

class ImportResponse(BaseModel):

    """Response after importing a portable snapshot."""

    snapshot_id: str
    repo_id: str
    symbols_imported: int
    edges_imported: int
    files_imported: int
    summaries_imported: int
    docs_imported: int
    evaluations_imported: int
    message: str

# ---------------------------------------------------------------------------

# Export endpoint

# ---------------------------------------------------------------------------

@router.get(

    "/{repo_id}/snapshots/{snapshot_id}/portable",
    summary="Export snapshot as a portable .eidos file",
    description="Downloads a gzip-compressed JSON file containing all analysis data.",
    response_class=Response,
    responses={200: {"content": {"application/gzip": {}}}},
)

async def export_portable(

    repo_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    snap: RepoSnapshot = Depends(verify_snapshot),

) -> Response:

    """
    Export a complete snapshot as a portable ``.eidos`` file.
    The file is gzip-compressed JSON containing all analysis data:
    symbols, edges, files, summaries, generated docs, and evaluations.
    Use ``POST /repos/{repo_id}/import`` to restore it on any Eidos instance.
    """
    payload = await _build_export_payload(db, snap)
    json_bytes = json.dumps(payload, separators=(",", ":"), default=str).encode()
    compressed = gzip.compress(json_bytes, compresslevel=9)

    return Response(
        content=compressed,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{repo_id}_{snapshot_id}.eidos"',
            "X-Eidos-Schema-Version": str(PORTABLE_SCHEMA_VERSION),
            "X-Eidos-Uncompressed-Size": str(len(json_bytes)),
            "X-Eidos-Compressed-Size": str(len(compressed)),
        },
    )

# ---------------------------------------------------------------------------

# Import endpoint

# ---------------------------------------------------------------------------

@router.post(

    "/{repo_id}/import",
    response_model=ImportResponse,
    status_code=201,
    summary="Import a portable .eidos file",
    description="Upload a .eidos file to restore a snapshot without re-running ingestion.",
)

async def import_portable(

    repo_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),

) -> Any:

    """
    Import a ``.eidos`` file and create a new snapshot with all analysis data.
    The repo must already exist.  A new snapshot is created with status
    ``completed`` and all symbols, edges, files, summaries, docs, and
    evaluations from the file are restored.
    This allows migrating analysis results between Eidos instances or
    restoring a previous analysis without re-cloning and re-parsing.
    """
    # Verify repo exists
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    payload = await _validate_and_parse_upload(file)
    counts = await _restore_snapshot(db, repo_id, payload)

    return ImportResponse(
        snapshot_id=counts["snapshot_id"],
        repo_id=repo_id,
        symbols_imported=counts["symbols"],
        edges_imported=counts["edges"],
        files_imported=counts["files"],
        summaries_imported=counts["summaries"],
        docs_imported=counts["docs"],
        evaluations_imported=counts["evaluations"],
        message="Snapshot restored successfully",
    )

# ---------------------------------------------------------------------------

# Validation helpers

# ---------------------------------------------------------------------------

async def _validate_and_parse_upload(file: UploadFile) -> dict[str, Any]:
    """Read, decompress, parse, and validate an uploaded .eidos file."""
    if file.content_type and file.content_type not in (
        "application/gzip",
        "application/octet-stream",
        "application/x-gzip",
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Expected gzip file, got {file.content_type}",
        )

    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(raw)} bytes). Max: {MAX_UPLOAD_BYTES}",
        )

    try:
        decompressed = gzip.decompress(raw)
    except gzip.BadGzipFile:
        raise HTTPException(status_code=400, detail="Invalid gzip file")

    try:
        payload = json.loads(decompressed)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON inside gzip")

    schema_version = payload.get("schema_version", 0)
    if schema_version > PORTABLE_SCHEMA_VERSION:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File schema version {schema_version} is newer than this server "
                f"supports ({PORTABLE_SCHEMA_VERSION}). Please upgrade Eidos."
            ),
        )
    if "metadata" not in payload:
        raise HTTPException(status_code=400, detail="Missing metadata in .eidos file")

    result: dict[str, Any] = payload
    return result

# ---------------------------------------------------------------------------

# Export: per-entity serializers

# ---------------------------------------------------------------------------

async def _build_export_payload(

    db: AsyncSession, snap: RepoSnapshot

) -> dict[str, Any]:

    """Serialize a snapshot into a dict ready for JSON compression."""
    sid = snap.id
    result: dict[str, Any] = {
        "schema_version": PORTABLE_SCHEMA_VERSION,
        "metadata": {
            "commit_sha": snap.commit_sha or "",
            "file_count": snap.file_count,
            "original_snapshot_id": snap.id,
            "original_repo_id": snap.repo_id,
        },
        "files": await _export_files(db, sid),
        "symbols": await _export_symbols(db, sid),
        "edges": await _export_edges(db, sid),
        "summaries": await _export_summaries(db, sid),
        "docs": await _export_docs(db, sid),
        "evaluations": await _export_evaluations(db, sid),
    }
    return result

async def _export_files(db: AsyncSession, sid: str) -> list[dict[str, Any]]:
    result = await db.execute(select(File).where(File.snapshot_id == sid))
    return [
        {"path": f.path, "language": f.language, "hash": f.hash, "size_bytes": f.size_bytes}
        for f in result.scalars().all()
    ]

async def _export_symbols(db: AsyncSession, sid: str) -> list[dict[str, Any]]:
    result = await db.execute(select(Symbol).where(Symbol.snapshot_id == sid))
    symbols = []
    for s in result.scalars().all():
        sym: dict[str, Any] = {
            "n": s.name, "k": s.kind, "fq": s.fq_name,
            "fp": s.file_path, "sl": s.start_line, "el": s.end_line,
        }
        if s.namespace:
            sym["ns"] = s.namespace
        if s.parent_fq_name:
            sym["p"] = s.parent_fq_name
        if s.signature:
            sym["sig"] = s.signature
        if s.modifiers:
            sym["mod"] = s.modifiers
        if s.return_type:
            sym["rt"] = s.return_type
        symbols.append(sym)
    return symbols

async def _export_edges(db: AsyncSession, sid: str) -> list[dict[str, Any]]:
    result = await db.execute(select(Edge).where(Edge.snapshot_id == sid))
    edges = []
    for e in result.scalars().all():
        edge: dict[str, Any] = {"s": e.source_fq_name, "t": e.target_fq_name, "tp": e.edge_type}
        if e.file_path:
            edge["fp"] = e.file_path
        if e.line:
            edge["ln"] = e.line
        edges.append(edge)
    return edges

async def _export_summaries(db: AsyncSession, sid: str) -> list[dict[str, Any]]:
    result = await db.execute(select(Summary).where(Summary.snapshot_id == sid))
    return [
        {"scope_type": s.scope_type, "scope_id": s.scope_id, "json": s.summary_json}
        for s in result.scalars().all()
    ]

async def _export_docs(db: AsyncSession, sid: str) -> list[dict[str, Any]]:
    result = await db.execute(select(GeneratedDoc).where(GeneratedDoc.snapshot_id == sid))
    return [
        {
            "doc_type": d.doc_type, "scope_id": d.scope_id, "title": d.title,
            "markdown": d.markdown, "llm_narrative": d.llm_narrative or "",
        }
        for d in result.scalars().all()
    ]

async def _export_evaluations(db: AsyncSession, sid: str) -> list[dict[str, Any]]:
    result = await db.execute(select(Evaluation).where(Evaluation.snapshot_id == sid))
    return [
        {
            "scope": ev.scope, "overall_score": ev.overall_score,
            "overall_severity": ev.overall_severity,
            "checks_json": ev.checks_json, "summary": ev.summary,
        }
        for ev in result.scalars().all()
    ]

# ---------------------------------------------------------------------------

# Import: per-entity restorers

# ---------------------------------------------------------------------------

async def _restore_snapshot(

    db: AsyncSession, repo_id: str, payload: dict[str, Any]

) -> dict[str, Any]:

    """Create a new snapshot and populate it from an import payload."""
    meta = payload["metadata"]
    snapshot_id = uuid.uuid4().hex[:12]

    db.add(RepoSnapshot(
        id=snapshot_id,
        repo_id=repo_id,
        commit_sha=meta.get("commit_sha") or None,
        status=SnapshotStatus.completed,
        file_count=meta.get("file_count", 0),
    ))
    await db.flush()

    counts = {
        "snapshot_id": snapshot_id,
        "files": _import_files(db, snapshot_id, payload.get("files", [])),
        "symbols": _import_symbols(db, snapshot_id, payload.get("symbols", [])),
        "edges": _import_edges(db, snapshot_id, payload.get("edges", [])),
        "summaries": _import_summaries(db, snapshot_id, payload.get("summaries", [])),
        "docs": _import_docs(db, snapshot_id, payload.get("docs", [])),
        "evaluations": _import_evaluations(db, snapshot_id, payload.get("evaluations", [])),
    }
    await db.commit()
    return counts


def _import_files(db: AsyncSession, sid: str, data: list[dict[str, Any]]) -> int:
    for f in data:
        db.add(File(
            snapshot_id=sid, path=f["path"], language=f.get("language"),
            hash=f.get("hash", ""), size_bytes=f.get("size_bytes", 0),
        ))
    return len(data)


def _import_symbols(db: AsyncSession, sid: str, data: list[dict[str, Any]]) -> int:
    for s in data:
        db.add(Symbol(
            snapshot_id=sid, name=s["n"], kind=s["k"], fq_name=s["fq"],
            file_path=s["fp"], start_line=s["sl"], end_line=s["el"],
            namespace=s.get("ns", ""), parent_fq_name=s.get("p"),
            signature=s.get("sig", ""), modifiers=s.get("mod", ""),
            return_type=s.get("rt", ""),
        ))
    return len(data)


def _import_edges(db: AsyncSession, sid: str, data: list[dict[str, Any]]) -> int:
    for e in data:
        db.add(Edge(
            snapshot_id=sid, source_fq_name=e["s"], target_fq_name=e["t"],
            edge_type=e["tp"], file_path=e.get("fp", ""), line=e.get("ln"),
        ))
    return len(data)


def _import_summaries(db: AsyncSession, sid: str, data: list[dict[str, Any]]) -> int:
    for s in data:
        db.add(Summary(
            snapshot_id=sid, scope_type=s["scope_type"],
            scope_id=s["scope_id"], summary_json=s["json"],
        ))
    return len(data)


def _import_docs(db: AsyncSession, sid: str, data: list[dict[str, Any]]) -> int:
    for d in data:
        db.add(GeneratedDoc(
            snapshot_id=sid, doc_type=d["doc_type"], scope_id=d.get("scope_id", ""),
            title=d["title"], markdown=d["markdown"],
            llm_narrative=d.get("llm_narrative", ""),
        ))
    return len(data)


def _import_evaluations(db: AsyncSession, sid: str, data: list[dict[str, Any]]) -> int:
    for ev in data:
        db.add(Evaluation(
            snapshot_id=sid, scope=ev.get("scope", "snapshot"),
            overall_score=ev.get("overall_score", 0.0),
            overall_severity=ev.get("overall_severity", "pass"),
            checks_json=ev.get("checks_json", "[]"), summary=ev.get("summary", ""),
        ))
    return len(data)
