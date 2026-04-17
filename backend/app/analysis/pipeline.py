"""
Analysis pipeline: parses all C# files in a snapshot, builds graph,
and persists symbols + edges to the database.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.csharp_parser import parse_file
from app.analysis.graph_builder import CodeGraph, build_graph
from app.analysis.models import FileAnalysis
from app.storage.models import Edge, Symbol

logger = logging.getLogger(__name__)


def analyze_snapshot_files(repo_dir: Path, file_records: list[dict[str, Any]]) -> CodeGraph:
    """
    Run static analysis on all C# files in a snapshot directory.

    Args:
        repo_dir: Path to the cloned repo on disk.
        file_records: List of file dicts (from ingestion) with 'path' and 'language'.

    Returns:
        A fully constructed CodeGraph.
    """
    cs_files = [f for f in file_records if f.get("language") == "csharp"]
    analyses: list[FileAnalysis] = []

    for file_info in cs_files:
        file_path = repo_dir / file_info["path"]
        if not file_path.exists():
            logger.warning("File not found on disk: %s", file_path)
            continue

        try:
            source = file_path.read_bytes()
            analysis = parse_file(source, file_info["path"])
            analyses.append(analysis)
        except Exception:
            logger.exception("Failed to parse %s", file_info["path"])

    graph = build_graph(analyses)
    logger.info(
        "Analysis complete: %d files parsed, %d symbols, %d edges",
        len(analyses),
        len(graph.symbols),
        len(graph.edges),
    )
    return graph


async def persist_graph(db: AsyncSession, snapshot_id: str, graph: CodeGraph) -> None:
    """
    Persist all symbols and edges from a CodeGraph to the database.

    Also attempts to link edges to symbol IDs for efficient joins.
    """
    # Build fq_name -> file_id lookup from existing file records
    fq_to_symbol_id: dict[str, int] = {}

    # Persist symbols
    for sym in graph.symbols.values():
        db_symbol = Symbol(
            snapshot_id=snapshot_id,
            kind=sym.kind.value,
            name=sym.name,
            fq_name=sym.fq_name,
            file_path=sym.file_path,
            start_line=sym.start_line,
            end_line=sym.end_line,
            namespace=sym.namespace,
            parent_fq_name=sym.parent_fq_name,
            signature=sym.signature,
            modifiers=",".join(sym.modifiers),
            return_type=sym.return_type,
        )
        db.add(db_symbol)
        await db.flush()  # get the auto-generated ID
        fq_to_symbol_id[sym.fq_name] = db_symbol.id

    # Persist edges with resolved symbol IDs where possible
    for edge in graph.edges:
        db_edge = Edge(
            snapshot_id=snapshot_id,
            source_symbol_id=fq_to_symbol_id.get(edge.source_fq_name),
            target_symbol_id=fq_to_symbol_id.get(edge.target_fq_name),
            source_fq_name=edge.source_fq_name,
            target_fq_name=edge.target_fq_name,
            edge_type=edge.edge_type.value,
            file_path=edge.file_path,
            line=edge.line,
        )
        db.add(db_edge)

    await db.flush()
    logger.info(
        "Persisted %d symbols and %d edges for snapshot %s",
        len(fq_to_symbol_id),
        len(graph.edges),
        snapshot_id,
    )
