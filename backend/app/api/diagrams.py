"""
Mermaid diagram generation from code graph data.

Generates class diagrams and module dependency diagrams
in Mermaid syntax that can be rendered in any Markdown viewer.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_snapshot
from app.storage.database import get_db
from app.storage.models import Edge, RepoSnapshot, Symbol

router = APIRouter()


class DiagramResponse(BaseModel):
    """Response containing Mermaid diagram syntax."""

    snapshot_id: str
    diagram_type: str
    mermaid: str
    node_count: int
    edge_count: int


@router.get(
    "/{repo_id}/snapshots/{snapshot_id}/diagram",
    response_model=DiagramResponse,
    summary="Generate a Mermaid diagram for the snapshot",
)
async def generate_diagram(
    repo_id: str,
    snapshot_id: str,
    diagram_type: str = Query(
        "class",
        description=(
            "Diagram type: 'class' (class/interface hierarchy)"
            " or 'module' (namespace dependencies)"
        ),
    ),
    max_nodes: int = Query(80, ge=1, le=500, description="Maximum number of nodes to include"),
    file_path: str | None = Query(None, description="Filter symbols by file path"),
    namespace: str | None = Query(None, description="Filter symbols by namespace"),
    db: AsyncSession = Depends(get_db),
    _snap: RepoSnapshot = Depends(verify_snapshot),
) -> Any:
    """
    Generate a Mermaid diagram from the code graph.

    Supported diagram types:
    - **class**: Shows classes, interfaces, and their relationships
      (inheritance, implementation, containment).
    - **module**: Shows namespace-level dependencies (which namespaces
      call/import which).

    The output is valid Mermaid syntax. Paste it into any Markdown renderer,
    GitHub issue, or Mermaid live editor to visualize.
    """
    if diagram_type == "class":
        return await _class_diagram(db, snapshot_id, max_nodes, file_path, namespace)
    elif diagram_type == "module":
        return await _module_diagram(db, snapshot_id, max_nodes, namespace)
    else:
        return DiagramResponse(
            snapshot_id=snapshot_id,
            diagram_type=diagram_type,
            mermaid=f"%% Unknown diagram type: {diagram_type}",
            node_count=0,
            edge_count=0,
        )


# ---------------------------------------------------------------------------
# Class diagram
# ---------------------------------------------------------------------------


async def _class_diagram(
    db: AsyncSession,
    snapshot_id: str,
    max_nodes: int,
    file_path: str | None,
    namespace: str | None,
) -> DiagramResponse:
    """Generate a Mermaid classDiagram."""
    sym_stmt = select(Symbol).where(
        Symbol.snapshot_id == snapshot_id,
        Symbol.kind.in_(["class", "interface", "struct", "enum"]),
    )
    if file_path:
        sym_stmt = sym_stmt.where(Symbol.file_path == file_path)
    if namespace:
        sym_stmt = sym_stmt.where(Symbol.namespace == namespace)
    sym_stmt = sym_stmt.order_by(Symbol.namespace, Symbol.name).limit(max_nodes)

    result = await db.execute(sym_stmt)
    symbols = result.scalars().all()
    fq_set = {s.fq_name for s in symbols}

    # Fetch methods/fields for these classes
    member_stmt = select(Symbol).where(
        Symbol.snapshot_id == snapshot_id,
        Symbol.parent_fq_name.in_(list(fq_set)),
        Symbol.kind.in_(["method", "property", "field", "constructor"]),
    )
    member_result = await db.execute(member_stmt)
    members = member_result.scalars().all()

    # Group members by parent
    members_by_parent: dict[str, list[Any]] = {}
    for m in members:
        members_by_parent.setdefault(m.parent_fq_name or "", []).append(m)

    # Fetch relationships (inherits, implements, contains)
    edge_stmt = select(Edge).where(
        Edge.snapshot_id == snapshot_id,
        Edge.edge_type.in_(["inherits", "implements"]),
        Edge.source_fq_name.in_(list(fq_set)),
    )
    edge_result = await db.execute(edge_stmt)
    edges = edge_result.scalars().all()

    # Build Mermaid syntax
    lines = ["classDiagram"]
    edge_count = 0

    for sym in symbols:
        safe_name = _safe_id(sym.fq_name)
        kind_annotation = ""
        if sym.kind == "interface":
            kind_annotation = "<<interface>>"
        elif sym.kind == "struct":
            kind_annotation = "<<struct>>"
        elif sym.kind == "enum":
            kind_annotation = "<<enumeration>>"

        lines.append(f"    class {safe_name} {{")
        if kind_annotation:
            lines.append(f"        {kind_annotation}")
        for m in members_by_parent.get(sym.fq_name, [])[:10]:
            prefix = "+" if "public" in (m.modifiers or "") else "-"
            if m.kind == "method" or m.kind == "constructor":
                sig = m.signature or m.name
                ret = f" {m.return_type}" if m.return_type else ""
                lines.append(f"        {prefix}{sig}{ret}")
            else:
                lines.append(f"        {prefix}{m.name}")
        lines.append("    }")

    for edge in edges:
        src = _safe_id(edge.source_fq_name)
        tgt = _safe_id(edge.target_fq_name)
        if edge.edge_type == "inherits":
            lines.append(f"    {tgt} <|-- {src}")
        elif edge.edge_type == "implements":
            lines.append(f"    {tgt} <|.. {src}")
        edge_count += 1

    return DiagramResponse(
        snapshot_id=snapshot_id,
        diagram_type="class",
        mermaid="\n".join(lines),
        node_count=len(symbols),
        edge_count=edge_count,
    )


# ---------------------------------------------------------------------------
# Module diagram
# ---------------------------------------------------------------------------


async def _module_diagram(
    db: AsyncSession,
    snapshot_id: str,
    max_nodes: int,
    namespace: str | None,
) -> DiagramResponse:
    """Generate a Mermaid flowchart showing namespace dependencies."""
    # Get all unique namespaces
    sym_stmt = select(Symbol.namespace).where(
        Symbol.snapshot_id == snapshot_id,
        Symbol.namespace.isnot(None),
        Symbol.namespace != "",
    ).distinct()
    ns_result = await db.execute(sym_stmt)
    namespaces = [row[0] for row in ns_result.all()]

    if namespace:
        namespaces = [n for n in namespaces if namespace in n]
    namespaces = namespaces[:max_nodes]
    ns_set = set(namespaces)

    # Build namespace -> symbols mapping for edge lookup
    sym_by_ns: dict[str, set[str]] = {}
    full_syms = await db.execute(
        select(Symbol.fq_name, Symbol.namespace).where(
            Symbol.snapshot_id == snapshot_id,
            Symbol.namespace.in_(list(ns_set)),
        )
    )
    for fq, ns in full_syms.all():
        sym_by_ns.setdefault(ns, set()).add(fq)

    # Get cross-namespace edges (calls, uses)
    edge_stmt = select(Edge).where(
        Edge.snapshot_id == snapshot_id,
        Edge.edge_type.in_(["calls", "uses", "imports"]),
    )
    edge_result = await db.execute(edge_stmt)
    all_edges = edge_result.scalars().all()

    # Map fq_name -> namespace
    fq_to_ns: dict[str, str] = {}
    for ns, fqs in sym_by_ns.items():
        for fq in fqs:
            fq_to_ns[fq] = ns

    # Build cross-namespace dependency set
    deps: set[tuple[str, str]] = set()
    for edge in all_edges:
        src_ns = fq_to_ns.get(edge.source_fq_name)
        tgt_ns = fq_to_ns.get(edge.target_fq_name)
        if src_ns and tgt_ns and src_ns != tgt_ns and src_ns in ns_set and tgt_ns in ns_set:
            deps.add((src_ns, tgt_ns))

    lines = ["graph LR"]
    for ns in sorted(namespaces):
        safe = _safe_id(ns)
        count = len(sym_by_ns.get(ns, []))
        lines.append(f'    {safe}["{ns}<br/>{count} symbols"]')

    for src_ns, tgt_ns in sorted(deps):
        lines.append(f"    {_safe_id(src_ns)} --> {_safe_id(tgt_ns)}")

    return DiagramResponse(
        snapshot_id=snapshot_id,
        diagram_type="module",
        mermaid="\n".join(lines),
        node_count=len(namespaces),
        edge_count=len(deps),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_id(name: str) -> str:
    """Convert a dotted FQ name into a safe Mermaid node ID."""
    result = name.replace(".", "_").replace("-", "_")
    return result.replace(" ", "_").replace("<", "").replace(">", "")
