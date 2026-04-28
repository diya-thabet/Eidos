"""
Analysis pipeline: parses source files in a snapshot via the language
parser registry, builds a unified code graph, and persists symbols +
edges to the database.

Supports parallel parsing via concurrent.futures for large repos.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.graph_builder import CodeGraph, build_graph
from app.analysis.models import FileAnalysis
from app.analysis.parser_registry import get_parser, supported_languages
from app.storage.models import Edge, Symbol

logger = logging.getLogger(__name__)

# Number of parallel workers for parsing (default: CPU count, capped at 8)
_MAX_WORKERS = min(int(os.environ.get("EIDOS_PARSE_WORKERS", "0")) or os.cpu_count() or 4, 8)


def _parse_single_file(
    repo_dir_str: str, file_path: str, language: str
) -> FileAnalysis | None:
    """Parse a single file (designed to run in a subprocess)."""
    from app.analysis.parser_registry import get_parser as _get_parser

    parser = _get_parser(language)
    if parser is None:
        return None

    full_path = Path(repo_dir_str) / file_path
    if not full_path.exists():
        return None

    try:
        source = full_path.read_bytes()
        return parser.parse_file(source, file_path)
    except Exception:
        return None


def analyze_snapshot_files(repo_dir: Path, file_records: list[dict[str, Any]]) -> CodeGraph:
    """
    Run static analysis on all parseable files in a snapshot directory.

    Uses parallel parsing when file count exceeds the threshold (20 files).
    Falls back to sequential parsing for small repos or when workers=1.

    Args:
        repo_dir: Path to the cloned repo on disk.
        file_records: List of file dicts (from ingestion) with 'path' and 'language'.

    Returns:
        A fully constructed CodeGraph.
    """
    available = supported_languages()

    # Filter to parseable files
    parseable = [
        f for f in file_records
        if f.get("language", "") in available
    ]

    # Use parallel parsing for large repos
    if len(parseable) > 20 and _MAX_WORKERS > 1:
        analyses = _parse_parallel(repo_dir, parseable)
    else:
        analyses = _parse_sequential(repo_dir, parseable)

    graph = build_graph(analyses)
    logger.info(
        "Analysis complete: %d files parsed, %d symbols, %d edges (workers=%d)",
        len(analyses),
        len(graph.symbols),
        len(graph.edges),
        _MAX_WORKERS if len(parseable) > 20 else 1,
    )
    return graph


def _parse_sequential(repo_dir: Path, file_records: list[dict[str, Any]]) -> list[FileAnalysis]:
    """Parse files one-by-one (for small repos or single-worker mode)."""
    analyses: list[FileAnalysis] = []
    for file_info in file_records:
        parser = get_parser(file_info["language"])
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
    return analyses


def _parse_parallel(repo_dir: Path, file_records: list[dict[str, Any]]) -> list[FileAnalysis]:
    """Parse files in parallel using a process pool."""
    analyses: list[FileAnalysis] = []
    repo_dir_str = str(repo_dir)

    with ProcessPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                _parse_single_file, repo_dir_str, f["path"], f["language"]
            ): f["path"]
            for f in file_records
        }
        for future in as_completed(futures):
            file_path = futures[future]
            try:
                result = future.result()
                if result is not None:
                    analyses.append(result)
            except Exception:
                logger.exception("Parallel parse failed for %s", file_path)

    return analyses


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
