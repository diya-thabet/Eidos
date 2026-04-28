"""
Incremental ingestion: only re-parse files that changed between snapshots.

Compares file hashes from the previous snapshot to determine which files
need re-parsing. Unchanged files reuse symbols/edges from the prior snapshot.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import Edge, File, RepoSnapshot, SnapshotStatus, Symbol

logger = logging.getLogger(__name__)


async def compute_changed_files(
    db: AsyncSession,
    repo_id: str,
    current_files: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Compare current files against the previous completed snapshot.

    Args:
        db: Database session.
        repo_id: The repository ID.
        current_files: List of file dicts with 'path', 'hash', 'language', 'size_bytes'.

    Returns:
        Tuple of (files_to_parse, previous_snapshot_id).
        - files_to_parse: Only files with changed or new hashes.
        - previous_snapshot_id: The snapshot we're comparing against (or None if first).
    """
    # Find the most recent completed snapshot for this repo
    result = await db.execute(
        select(RepoSnapshot)
        .where(
            RepoSnapshot.repo_id == repo_id,
            RepoSnapshot.status == SnapshotStatus.completed,
        )
        .order_by(RepoSnapshot.created_at.desc())
        .limit(1)
    )
    prev_snapshot = result.scalar_one_or_none()

    if prev_snapshot is None:
        # First snapshot - parse everything
        logger.info("No previous snapshot for repo %s - full parse", repo_id)
        return current_files, None

    # Get previous file hashes
    prev_files_result = await db.execute(
        select(File).where(File.snapshot_id == prev_snapshot.id)
    )
    prev_hashes: dict[str, str] = {
        f.path: f.hash for f in prev_files_result.scalars().all()
    }

    # Determine changed files
    changed: list[dict[str, Any]] = []
    unchanged_paths: list[str] = []

    for f in current_files:
        prev_hash = prev_hashes.get(f["path"])
        if prev_hash is None or prev_hash != f["hash"]:
            changed.append(f)
        else:
            unchanged_paths.append(f["path"])

    logger.info(
        "Incremental: %d changed, %d unchanged (previous snapshot: %s)",
        len(changed),
        len(unchanged_paths),
        prev_snapshot.id,
    )

    return changed, prev_snapshot.id


async def copy_unchanged_symbols(
    db: AsyncSession,
    prev_snapshot_id: str,
    new_snapshot_id: str,
    changed_file_paths: set[str],
) -> tuple[int, int]:
    """
    Copy symbols and edges from the previous snapshot for unchanged files.

    Only copies symbols/edges whose file_path is NOT in the changed set.

    Returns:
        Tuple of (symbols_copied, edges_copied).
    """
    # Copy symbols from unchanged files
    prev_symbols = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == prev_snapshot_id)
    )
    symbols_copied = 0
    for sym in prev_symbols.scalars().all():
        if sym.file_path in changed_file_paths:
            continue
        db.add(Symbol(
            snapshot_id=new_snapshot_id,
            name=sym.name,
            kind=sym.kind,
            fq_name=sym.fq_name,
            file_path=sym.file_path,
            start_line=sym.start_line,
            end_line=sym.end_line,
            namespace=sym.namespace,
            parent_fq_name=sym.parent_fq_name,
            signature=sym.signature,
            modifiers=sym.modifiers,
            return_type=sym.return_type,
        ))
        symbols_copied += 1

    # Copy edges from unchanged files
    prev_edges = await db.execute(
        select(Edge).where(Edge.snapshot_id == prev_snapshot_id)
    )
    edges_copied = 0
    for edge in prev_edges.scalars().all():
        if edge.file_path in changed_file_paths:
            continue
        db.add(Edge(
            snapshot_id=new_snapshot_id,
            source_fq_name=edge.source_fq_name,
            target_fq_name=edge.target_fq_name,
            edge_type=edge.edge_type,
            file_path=edge.file_path,
            line=edge.line,
        ))
        edges_copied += 1

    await db.flush()
    logger.info(
        "Copied %d symbols and %d edges from previous snapshot %s",
        symbols_copied, edges_copied, prev_snapshot_id,
    )
    return symbols_copied, edges_copied
