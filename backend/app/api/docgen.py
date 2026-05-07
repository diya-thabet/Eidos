"""
API endpoints for auto-documentation generation.

Generates, lists, and retrieves documentation artifacts
for a snapshot of an indexed codebase.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_snapshot
from app.auth.scopes import require_scope
from app.core.config import settings
from app.docgen.models import DocType
from app.docgen.orchestrator import generate_all_docs, generate_single_doc
from app.reasoning.llm_client import LLMConfig, create_llm_client
from app.storage.database import get_db
from app.storage.models import GeneratedDoc, RepoSnapshot
from app.storage.schemas import (
    GeneratedDocOut,
    GenerateDocsRequest,
    GenerateDocsResponse,
)

router = APIRouter(dependencies=[Depends(require_scope("write:docs"))])


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/docs",
    response_model=GenerateDocsResponse,
    summary="Generate documentation for a snapshot",
)
async def generate_docs(
    repo_id: str,
    snapshot_id: str,
    body: GenerateDocsRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _snap: RepoSnapshot = Depends(verify_snapshot),
) -> Any:
    """
    Generate documentation from the analysed codebase.

    - If ``doc_type`` is omitted, generates **all** document types.
    - If ``doc_type`` is specified, generates only that type.
    - ``scope_id`` is required for ``module`` and ``flow`` types.

    Documents are persisted and can be retrieved via GET.
    Works with or without an LLM.
    """
    llm = _make_llm()
    body = body or GenerateDocsRequest()

    if body.doc_type is None:
        # Generate all
        results = await generate_all_docs(db, snapshot_id, llm=llm)
    else:
        try:
            dt = DocType(body.doc_type)
        except ValueError:
            valid = [t.value for t in DocType]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid doc_type. Valid: {valid}",
            )
        result = await generate_single_doc(db, snapshot_id, dt, body.scope_id, llm=llm)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        results = [result]

    docs_out = [
        GeneratedDocOut(
            id=r.get("id"),
            doc_type=r["doc_type"],
            title=r["title"],
            scope_id=r.get("scope_id", ""),
            markdown=r["markdown"],
            llm_narrative=r.get("llm_narrative", ""),
        )
        for r in results
    ]

    return GenerateDocsResponse(
        snapshot_id=snapshot_id,
        documents=docs_out,
        total=len(docs_out),
    )


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/docs",
    response_model=list[GeneratedDocOut],
    summary="List generated documents",
)
async def list_docs(
    repo_id: str,
    snapshot_id: str,
    doc_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    _snap: RepoSnapshot = Depends(verify_snapshot),
) -> Any:
    """List all generated documents for a snapshot."""

    stmt = select(GeneratedDoc).where(GeneratedDoc.snapshot_id == snapshot_id)
    if doc_type:
        stmt = stmt.where(GeneratedDoc.doc_type == doc_type)
    stmt = stmt.order_by(GeneratedDoc.id)

    result = await db.execute(stmt)
    return [
        GeneratedDocOut(
            id=d.id,
            doc_type=d.doc_type,
            title=d.title,
            scope_id=d.scope_id,
            markdown=d.markdown,
            llm_narrative=d.llm_narrative,
        )
        for d in result.scalars().all()
    ]


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/docs/{doc_id}",
    response_model=GeneratedDocOut,
    summary="Get a specific generated document",
)
async def get_doc(
    repo_id: str,
    snapshot_id: str,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    _snap: RepoSnapshot = Depends(verify_snapshot),
) -> Any:
    """Retrieve a specific generated document by ID."""

    result = await db.execute(
        select(GeneratedDoc).where(
            GeneratedDoc.id == doc_id,
            GeneratedDoc.snapshot_id == snapshot_id,
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return GeneratedDocOut(
        id=doc.id,
        doc_type=doc.doc_type,
        title=doc.title,
        scope_id=doc.scope_id,
        markdown=doc.markdown,
        llm_narrative=doc.llm_narrative,
    )


# -------------------------------------------------------------------
# Changelog
# -------------------------------------------------------------------


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/docs/changelog",
    response_model=GeneratedDocOut,
    summary="Generate changelog between two snapshots",
)
async def generate_changelog_endpoint(
    repo_id: str,
    snapshot_id: str,
    previous_snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    _snap: RepoSnapshot = Depends(verify_snapshot),
) -> Any:
    """Generate a changelog comparing current snapshot with a previous one."""
    import json

    from app.docgen.generator import generate_changelog
    from app.docgen.renderer import render_markdown
    from app.storage.models import Edge, GeneratedDoc, Symbol

    # Fetch current snapshot data
    cur_result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id)
    )
    cur_symbols = [
        {
            "fq_name": s.fq_name, "name": s.name, "kind": s.kind,
            "signature": s.signature or "", "modifiers": s.modifiers or "",
            "file_path": s.file_path, "start_line": s.start_line,
            "namespace": s.namespace or "",
        }
        for s in cur_result.scalars().all()
    ]
    cur_edges_result = await db.execute(
        select(Edge).where(Edge.snapshot_id == snapshot_id)
    )
    cur_edges = [
        {
            "source_fq_name": e.source_fq_name,
            "target_fq_name": e.target_fq_name,
            "edge_type": e.edge_type,
        }
        for e in cur_edges_result.scalars().all()
    ]

    # Fetch previous snapshot
    prev_snap = await db.get(RepoSnapshot, previous_snapshot_id)
    if prev_snap is None or prev_snap.repo_id != repo_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404, detail="Previous snapshot not found",
        )

    prev_result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == previous_snapshot_id)
    )
    prev_symbols = [
        {
            "fq_name": s.fq_name, "name": s.name, "kind": s.kind,
            "signature": s.signature or "", "modifiers": s.modifiers or "",
            "file_path": s.file_path, "start_line": s.start_line,
            "namespace": s.namespace or "",
        }
        for s in prev_result.scalars().all()
    ]
    prev_edges_result = await db.execute(
        select(Edge).where(Edge.snapshot_id == previous_snapshot_id)
    )
    prev_edges = [
        {
            "source_fq_name": e.source_fq_name,
            "target_fq_name": e.target_fq_name,
            "edge_type": e.edge_type,
        }
        for e in prev_edges_result.scalars().all()
    ]

    doc = generate_changelog(
        snapshot_id=snapshot_id,
        previous_snapshot_id=previous_snapshot_id,
        current_symbols=cur_symbols,
        previous_symbols=prev_symbols,
        current_edges=cur_edges,
        previous_edges=prev_edges,
    )

    markdown = render_markdown(doc)
    db_doc = GeneratedDoc(
        snapshot_id=snapshot_id,
        doc_type=doc.doc_type.value,
        scope_id=doc.scope_id,
        title=doc.title,
        markdown=markdown,
        llm_narrative="",
        metadata_json=json.dumps(doc.metadata, default=str),
    )
    db.add(db_doc)
    await db.commit()
    await db.refresh(db_doc)

    return GeneratedDocOut(
        id=db_doc.id,
        doc_type=db_doc.doc_type,
        title=db_doc.title,
        scope_id=db_doc.scope_id,
        markdown=markdown,
        llm_narrative="",
    )


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------



def _make_llm() -> Any:
    if settings.llm_base_url:
        return create_llm_client(
            LLMConfig(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                timeout=settings.llm_timeout,
            )
        )
    return create_llm_client(None)
