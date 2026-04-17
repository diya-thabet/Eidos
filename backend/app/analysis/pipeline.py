"""
Analysis pipeline: parses source files in a snapshot via the language
parser registry, builds a unified code graph, and persists symbols +
edges to the database.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.graph_builder import CodeGraph, build_graph
from app.analysis.models import FileAnalysis
from app.analysis.parser_registry import get_parser, supported_languages
from app.storage.models import Edge, Symbol

logger = logging.getLogger(__name__)


def analyze_snapshot_files(repo_dir: Path, file_records: list[dict[str, Any]]) -> CodeGraph:
    """
    Run static analysis on all parseable files in a snapshot directory.

    Uses the parser registry so that any language with a registered
    parser is automatically handled.

    Args:
        repo_dir: Path to the cloned repo on disk.
        file_records: List of file dicts (from ingestion) with 'path' and 'language'.

    Returns:
        A fully constructed CodeGraph.
    """
    analyses: list[FileAnalysis] = []
    available = supported_languages()

    for file_info in file_records:
        lang = file_info.get("language", "")
        if lang not in available:
            continue

        parser = get_parser(lang)
        if parser is None:
            continue

        file_path = repo_dir / file_info["path"]
        if not file_path.exists():
            logger.warning("File not found on disk: %s", file_path)
            continue

        try:
            source = file_path.read_bytes()
            analysis = parser.parse_file(source, file_info["path"])
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
