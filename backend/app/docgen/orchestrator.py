"""
Documentation generation orchestrator.

Fetches all analysis data from the database, generates documents
using the deterministic generator, optionally enriches with LLM,
renders to Markdown, and persists to the database.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.docgen.generator import (
    generate_architecture,
    generate_flow_doc,
    generate_module_doc,
    generate_readme,
    generate_runbook,
)
from app.docgen.models import DocType, GeneratedDocument
from app.docgen.renderer import render_markdown
from app.reasoning.llm_client import LLMClient, StubLLMClient
from app.storage.models import Edge, GeneratedDoc, Summary, Symbol

logger = logging.getLogger(__name__)


async def generate_all_docs(
    db: AsyncSession,
    snapshot_id: str,
    *,
    llm: LLMClient | None = None,
) -> list[dict[str, Any]]:
    """
    Generate all document types for a snapshot.

    Returns a list of dicts with doc metadata and generated content.
    """
    # Fetch analysis data
    data = await _fetch_analysis_data(db, snapshot_id)

    generated: list[dict[str, Any]] = []

    # 1. README
    readme = generate_readme(snapshot_id=snapshot_id, **data)
    generated.append(await _finalize_doc(db, readme, llm))

    # 2. Architecture
    arch = generate_architecture(snapshot_id=snapshot_id, **data)
    generated.append(await _finalize_doc(db, arch, llm))

    # 3. Module docs (one per module)
    for mod in data["modules"]:
        mod_name = mod.get("name", "")
        if not mod_name:
            continue
        mod_doc = generate_module_doc(
            snapshot_id=snapshot_id,
            module_name=mod_name,
            symbols=data["symbols"],
            edges=data["edges"],
            summaries=data["summaries"],
            files=mod.get("files", []),
            dependencies=mod.get("dependencies", []),
        )
        generated.append(await _finalize_doc(db, mod_doc, llm))

    # 4. Flow docs (one per entry point, limit 10)
    for ep in data["entry_points"][:10]:
        fq = ep.get("symbol_fq_name", "")
        if not fq:
            continue
        flow_doc = generate_flow_doc(
            snapshot_id=snapshot_id,
            entry_fq_name=fq,
            symbols=data["symbols"],
            edges=data["edges"],
            summaries=data["summaries"],
        )
        generated.append(await _finalize_doc(db, flow_doc, llm))

    # 5. Runbook
    runbook = generate_runbook(snapshot_id=snapshot_id, **data)
    generated.append(await _finalize_doc(db, runbook, llm))

    await db.commit()

    logger.info(
        "Generated %d documents for snapshot %s",
        len(generated),
        snapshot_id,
    )
    return generated


async def generate_single_doc(
    db: AsyncSession,
    snapshot_id: str,
    doc_type: DocType,
    scope_id: str = "",
    *,
    llm: LLMClient | None = None,
) -> dict[str, Any]:
    """Generate a single document of a specific type."""
    data = await _fetch_analysis_data(db, snapshot_id)

    if doc_type == DocType.README:
        doc = generate_readme(snapshot_id=snapshot_id, **data)
    elif doc_type == DocType.ARCHITECTURE:
        doc = generate_architecture(snapshot_id=snapshot_id, **data)
    elif doc_type == DocType.MODULE:
        mod = next(
            (m for m in data["modules"] if m.get("name") == scope_id),
            None,
        )
        if mod is None:
            return {"error": f"Module '{scope_id}' not found."}
        doc = generate_module_doc(
            snapshot_id=snapshot_id,
            module_name=scope_id,
            symbols=data["symbols"],
            edges=data["edges"],
            summaries=data["summaries"],
            files=mod.get("files", []),
            dependencies=mod.get("dependencies", []),
        )
    elif doc_type == DocType.FLOW:
        doc = generate_flow_doc(
            snapshot_id=snapshot_id,
            entry_fq_name=scope_id,
            symbols=data["symbols"],
            edges=data["edges"],
            summaries=data["summaries"],
        )
    elif doc_type == DocType.RUNBOOK:
        doc = generate_runbook(snapshot_id=snapshot_id, **data)
    else:
        return {"error": f"Unknown doc type: {doc_type}"}

    result = await _finalize_doc(db, doc, llm)
    await db.commit()
    return result


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------


async def _finalize_doc(
    db: AsyncSession,
    doc: GeneratedDocument,
    llm: LLMClient | None,
) -> dict[str, Any]:
    """Render, optionally enrich with LLM, persist, and return."""
    markdown = render_markdown(doc)

    # Optional LLM enrichment
    llm_narrative = ""
    if llm is not None and not isinstance(llm, StubLLMClient):
        llm_narrative = await _llm_narrate(llm, doc, markdown)

    # Persist
    db_doc = GeneratedDoc(
        snapshot_id=doc.snapshot_id,
        doc_type=doc.doc_type.value,
        scope_id=doc.scope_id,
        title=doc.title,
        markdown=markdown,
        llm_narrative=llm_narrative,
        metadata_json=json.dumps(doc.metadata, default=str),
    )
    db.add(db_doc)
    await db.flush()

    return {
        "id": db_doc.id,
        "doc_type": doc.doc_type.value,
        "title": doc.title,
        "scope_id": doc.scope_id,
        "markdown": markdown,
        "llm_narrative": llm_narrative,
    }


async def _llm_narrate(
    llm: LLMClient,
    doc: GeneratedDocument,
    markdown: str,
) -> str:
    """Ask the LLM to narrate/improve the generated doc."""
    system = (
        "You are a technical writer. The user provides auto-generated "
        "documentation from code analysis. Your job is to write a short, "
        "clear narrative summary (2-4 paragraphs) that highlights the "
        "most important points. Do NOT invent facts. Only narrate what "
        "is in the document. Cite symbol names and file paths."
    )
    user_msg = (
        f"Document type: {doc.doc_type.value}\nTitle: {doc.title}\n\nContent:\n{markdown[:3000]}"
    )
    try:
        return str(await llm.chat(system, user_msg))
    except Exception as e:
        logger.warning("LLM narration failed: %s", e)
        return ""


async def _fetch_analysis_data(db: AsyncSession, snapshot_id: str) -> dict[str, Any]:
    """Fetch all data needed for doc generation."""
    # Symbols
    result = await db.execute(select(Symbol).where(Symbol.snapshot_id == snapshot_id))
    symbols = [
        {
            "fq_name": s.fq_name,
            "kind": s.kind,
            "name": s.name,
            "file_path": s.file_path,
            "start_line": s.start_line,
            "end_line": s.end_line,
            "namespace": s.namespace,
            "parent_fq_name": s.parent_fq_name,
            "signature": s.signature,
            "modifiers": s.modifiers,
            "return_type": s.return_type,
        }
        for s in result.scalars().all()
    ]

    # Edges
    result = await db.execute(select(Edge).where(Edge.snapshot_id == snapshot_id))
    edges = [
        {
            "source_fq_name": e.source_fq_name,  # type: ignore[attr-defined]
            "target_fq_name": e.target_fq_name,  # type: ignore[attr-defined]
            "edge_type": e.edge_type,  # type: ignore[attr-defined]
            "file_path": e.file_path,
            "line": e.line,  # type: ignore[attr-defined]
        }
        for e in result.scalars().all()
    ]

    # Summaries
    result = await db.execute(select(Summary).where(Summary.snapshot_id == snapshot_id))
    summaries = [
        {
            "scope_type": s.scope_type,  # type: ignore[attr-defined]
            "scope_id": s.scope_id,  # type: ignore[attr-defined]
            "summary": _safe_json(s.summary_json),  # type: ignore[attr-defined]
        }
        for s in result.scalars().all()
    ]

    # Build modules from symbols (group by namespace)
    ns_symbols: dict[str, list[dict[str, Any]]] = {}
    ns_files: dict[str, set[str]] = {}
    for s in symbols:
        ns = str(s.get("namespace", ""))
        if not ns:
            continue
        ns_symbols.setdefault(ns, []).append(s)
        ns_files.setdefault(ns, set()).add(str(s.get("file_path", "")))

    # Build module dependency map from edges
    ns_deps: dict[str, set[str]] = {}
    for e in edges:
        src_ns = _find_namespace(symbols, e.get("source_fq_name", ""))
        tgt_ns = _find_namespace(symbols, e.get("target_fq_name", ""))
        if src_ns and tgt_ns and src_ns != tgt_ns:
            ns_deps.setdefault(src_ns, set()).add(tgt_ns)

    modules = [
        {
            "name": ns,
            "symbol_count": len(syms),
            "file_count": len(ns_files.get(ns, set())),
            "files": sorted(ns_files.get(ns, set())),
            "dependencies": sorted(ns_deps.get(ns, set())),
        }
        for ns, syms in sorted(ns_symbols.items())
    ]

    # Entry points (from summaries or symbols with specific patterns)
    entry_points = _detect_entry_points(symbols, edges)

    # Metrics (top hotspots by fan-in)
    metrics = _compute_simple_metrics(symbols, edges)

    return {
        "symbols": symbols,
        "edges": edges,
        "modules": modules,
        "summaries": summaries,
        "entry_points": entry_points,
        "metrics": metrics,
    }


def _detect_entry_points(
    symbols: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Detect entry points from symbols."""
    eps: list[dict[str, Any]] = []
    for s in symbols:
        name_lower = s.get("name", "").lower()
        fq = s.get("fq_name", "")
        kind = s.get("kind", "")

        is_controller = "controller" in fq.lower() and kind == "method"
        is_main = name_lower in ("main", "program", "startup")
        has_route_attr = "httpget" in s.get("modifiers", "").lower() or (
            "httppost" in s.get("modifiers", "").lower()
        )

        if is_controller or is_main or has_route_attr:
            ep_kind = "controller_action" if is_controller else "entry_point"
            eps.append(
                {
                    "symbol_fq_name": fq,
                    "kind": ep_kind,
                    "file_path": s.get("file_path", ""),
                    "line": s.get("start_line", 0),
                    "route": "",
                }
            )
    return eps


def _compute_simple_metrics(
    symbols: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Compute simple metrics for hotspot detection."""
    from collections import Counter

    fan_in = Counter(e.get("target_fq_name", "") for e in edges if e.get("edge_type") == "calls")
    fan_out = Counter(e.get("source_fq_name", "") for e in edges if e.get("edge_type") == "calls")

    metrics = []
    for s in symbols:
        fq = s.get("fq_name", "")
        loc = max((s.get("end_line", 0) - s.get("start_line", 0)), 0)
        fi = fan_in.get(fq, 0)
        fo = fan_out.get(fq, 0)
        if fi >= 3 or fo >= 3 or loc >= 30:
            metrics.append(
                {
                    "fq_name": fq,
                    "kind": s.get("kind", ""),
                    "lines_of_code": loc,
                    "fan_in": fi,
                    "fan_out": fo,
                }
            )

    metrics.sort(key=lambda m: m["fan_in"], reverse=True)
    return metrics[:20]


def _find_namespace(symbols: list[dict[str, Any]], fq_name: str) -> str:
    """Find the namespace for a fully-qualified name."""
    for s in symbols:
        if s.get("fq_name") == fq_name:
            return str(s.get("namespace", ""))
    return ""


def _safe_json(text: str) -> dict[str, Any]:
    """Parse JSON safely, returning empty dict[str, Any] on failure."""
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        return {}
