from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.pipeline import analyze_snapshot_files, persist_graph
from app.api.metrics import record_ingestion
from app.auth.crypto import decrypt
from app.core.incremental import compute_changed_files, copy_unchanged_symbols
from app.core.ingestion import clone_repo, repo_clone_path, scan_files
from app.core.retention import cleanup_clone
from app.indexing.indexer import run_indexing
from app.storage.database import async_session
from app.storage.models import File, Repo, RepoSnapshot, SnapshotStatus, Symbol

logger = logging.getLogger(__name__)


async def run_ingestion(snapshot_id: str) -> None:
    """Background task: clone repo, scan files, run analysis, persist results."""
    async with async_session() as db:
        snapshot = await db.get(RepoSnapshot, snapshot_id)
        if snapshot is None:
            logger.error("Snapshot %s not found", snapshot_id)
            return

        repo = await db.get(Repo, snapshot.repo_id)
        if repo is None:
            logger.error("Repo %s not found", snapshot.repo_id)
            return

        snapshot.status = SnapshotStatus.running
        snapshot.progress_percent = 0
        snapshot.progress_message = "Starting ingestion..."
        await db.commit()

        async def _progress(percent: int, message: str) -> None:
            snapshot.progress_percent = percent
            snapshot.progress_message = message
            await db.commit()
            logger.info("Snapshot %s: %d%% - %s", snapshot_id, percent, message)

        try:
            git_token = _resolve_git_token(repo)

            dest, resolved_sha = await _clone_phase(
                _progress, repo, snapshot, git_token,
            )
            file_entries = await _scan_phase(
                _progress, db, snapshot_id, snapshot, dest,
            )
            graph = await _analyze_phase(
                _progress, db, snapshot_id, repo, dest, file_entries,
            )
            await _blame_phase(db, snapshot_id, dest, graph)
            await _progress(70, "Generating summaries...")

            indexing_stats = await run_indexing(db, snapshot_id, graph)
            total_summaries = (
                indexing_stats.get("symbol_summaries", 0)
                + indexing_stats.get("module_summaries", 0)
                + indexing_stats.get("file_summaries", 0)
            )
            await _progress(90, f"Generated {total_summaries} summaries. Finalizing...")

            snapshot.status = SnapshotStatus.completed
            snapshot.progress_percent = 100
            snapshot.progress_message = "Ingestion complete"
            repo.last_indexed_at = datetime.now(UTC)
            await db.commit()
            record_ingestion("completed")
            logger.info(
                "Ingestion complete: snapshot=%s, files=%d, "
                "symbols=%d, edges=%d, summaries=%d, sha=%s",
                snapshot_id, len(file_entries), len(graph.symbols),
                len(graph.edges), total_summaries, resolved_sha,
            )
            cleanup_clone(repo.id, snapshot_id)

        except Exception as e:
            logger.exception("Ingestion failed for snapshot %s", snapshot_id)
            snapshot.status = SnapshotStatus.failed
            snapshot.error_message = str(e)[:2000]
            snapshot.progress_message = f"Failed: {str(e)[:200]}"
            await db.commit()
            record_ingestion("failed")


def _resolve_git_token(repo: Repo) -> str:
    """Decrypt the Git token for private repos."""
    if repo.git_token_enc:
        try:
            return decrypt(repo.git_token_enc)
        except ValueError:
            logger.warning("Could not decrypt Git token for repo %s", repo.id)
    return ""


async def _clone_phase(
    progress: Any, repo: Repo, snapshot: RepoSnapshot, git_token: str,
) -> tuple[Path, str]:
    """Clone the repo and return (dest_path, resolved_sha)."""
    await progress(5, "Cloning repository...")
    dest = repo_clone_path(repo.id, snapshot.id)
    resolved_sha = await asyncio.to_thread(
        clone_repo, repo.url, repo.default_branch,
        dest, snapshot.commit_sha, git_token,
    )
    snapshot.commit_sha = resolved_sha
    return dest, resolved_sha


async def _scan_phase(
    progress: Any, db: AsyncSession, snapshot_id: str,
    snapshot: RepoSnapshot, dest: Path,
) -> list[dict[str, Any]]:
    """Scan files and persist File records."""
    await progress(15, "Scanning files...")
    file_entries = await asyncio.to_thread(scan_files, dest)
    for entry in file_entries:
        db.add(File(
            snapshot_id=snapshot_id,
            path=entry["path"],
            language=entry["language"],
            hash=entry["hash"],
            size_bytes=entry["size_bytes"],
        ))
    snapshot.file_count = len(file_entries)
    await progress(25, f"Scanned {len(file_entries)} files. Parsing ASTs...")
    return file_entries


async def _analyze_phase(
    progress: Any, db: AsyncSession, snapshot_id: str,
    repo: Repo, dest: Path, file_entries: list[dict[str, Any]],
) -> Any:
    """Run AST analysis and persist the code graph."""
    changed_files, prev_snapshot_id = await compute_changed_files(
        db, repo.id, file_entries,
    )
    graph = await asyncio.to_thread(analyze_snapshot_files, dest, changed_files)
    await progress(
        50,
        f"Parsed {len(graph.symbols)} symbols, "
        f"{len(graph.edges)} edges. Persisting graph...",
    )
    await persist_graph(db, snapshot_id, graph)

    if prev_snapshot_id:
        changed_paths = {f["path"] for f in changed_files}
        await copy_unchanged_symbols(
            db, prev_snapshot_id, snapshot_id, changed_paths,
        )
    await progress(65, "Graph persisted. Extracting blame data...")
    return graph


async def _blame_phase(
    db: AsyncSession, snapshot_id: str, dest: Path, graph: Any,
) -> None:
    """Extract git blame data and persist to symbols (non-fatal)."""
    try:
        from app.analysis.blame import extract_blame_for_snapshot

        sym_dicts = [
            {
                "fq_name": s.fq_name,
                "file_path": s.file_path,
                "start_line": s.start_line,
                "end_line": s.end_line,
            }
            for s in graph.symbols.values()
            if s.kind.value in ("method", "constructor")
        ]
        blame_map = await asyncio.to_thread(
            extract_blame_for_snapshot, dest, sym_dicts,
        )
        if blame_map:
            for fq_name, info in blame_map.items():
                await db.execute(
                    update(Symbol)
                    .where(
                        Symbol.snapshot_id == snapshot_id,
                        Symbol.fq_name == fq_name,
                    )
                    .values(
                        last_author=info.last_author,
                        last_modified_at=info.last_modified_at,
                        author_count=info.author_count,
                        commit_count=info.commit_count,
                    )
                )
            await db.flush()
            logger.info("Blame data persisted for %d symbols", len(blame_map))
    except Exception:
        logger.warning(
            "Blame extraction failed (non-fatal), continuing",
            exc_info=True,
        )
