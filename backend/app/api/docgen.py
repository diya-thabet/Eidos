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

router = APIRouter()


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
) -> Any:
    """
    Generate documentation from the analysed codebase.

    - If ``doc_type`` is omitted, generates **all** document types.
    - If ``doc_type`` is specified, generates only that type.
    - ``scope_id`` is required for ``module`` and ``flow`` types.

    Documents are persisted and can be retrieved via GET.
    Works with or without an LLM.
    """
    await _verify_snapshot(db, repo_id, snapshot_id)
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
) -> Any:
    """List all generated documents for a snapshot."""
    await _verify_snapshot(db, repo_id, snapshot_id)

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
) -> Any:
    """Retrieve a specific generated document by ID."""
    await _verify_snapshot(db, repo_id, snapshot_id)

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
# Helpers
# -------------------------------------------------------------------


async def _verify_snapshot(db: AsyncSession, repo_id: str, snapshot_id: str) -> Any:
    result = await db.execute(
        select(RepoSnapshot).where(
            RepoSnapshot.id == snapshot_id,
            RepoSnapshot.repo_id == repo_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")


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
