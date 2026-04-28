"""
Tests for incremental ingestion (P3.16).

Covers:
- First snapshot: all files parsed (no previous snapshot)
- Second snapshot: only changed files returned
- New files detected as changed
- Deleted files handled
- Identical hashes skip re-parsing
- copy_unchanged_symbols copies only from unchanged files
- Edge cases: empty file list, all files changed
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.core.incremental import compute_changed_files, copy_unchanged_symbols
from app.storage.models import (
    Edge,
    File,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, test_sessionmaker


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    yield
    await drop_tables()


async def _seed_completed_snapshot(
    repo_id: str = "r-inc",
    snapshot_id: str = "s-prev",
    files: list[dict] | None = None,
    symbols: list[dict] | None = None,
    edges: list[dict] | None = None,
) -> None:
    """Seed a completed snapshot with files, symbols, and edges."""
    async with test_sessionmaker() as db:
        db.add(Repo(id=repo_id, name="incr-test", url="https://example.com/inc"))
        db.add(RepoSnapshot(
            id=snapshot_id, repo_id=repo_id, status=SnapshotStatus.completed,
            file_count=len(files or []),
        ))
        for f in (files or []):
            db.add(File(snapshot_id=snapshot_id, **f))
        for s in (symbols or []):
            db.add(Symbol(snapshot_id=snapshot_id, **s))
        for e in (edges or []):
            db.add(Edge(snapshot_id=snapshot_id, **e))
        await db.commit()


class TestComputeChangedFiles:
    @pytest.mark.asyncio
    async def test_first_snapshot_returns_all_files(self):
        async with test_sessionmaker() as db:
            db.add(Repo(id="r-first", name="first", url="https://example.com"))
            await db.commit()

        current = [
            {"path": "a.py", "hash": "h1", "language": "python", "size_bytes": 100},
            {"path": "b.py", "hash": "h2", "language": "python", "size_bytes": 200},
        ]
        async with test_sessionmaker() as db:
            changed, prev_id = await compute_changed_files(db, "r-first", current)
        assert len(changed) == 2
        assert prev_id is None

    @pytest.mark.asyncio
    async def test_unchanged_files_excluded(self):
        await _seed_completed_snapshot(files=[
            {"path": "a.py", "hash": "h1", "language": "python", "size_bytes": 100},
            {"path": "b.py", "hash": "h2", "language": "python", "size_bytes": 200},
        ])
        current = [
            {"path": "a.py", "hash": "h1", "language": "python", "size_bytes": 100},  # same
            {"path": "b.py", "hash": "h2", "language": "python", "size_bytes": 200},  # same
        ]
        async with test_sessionmaker() as db:
            changed, prev_id = await compute_changed_files(db, "r-inc", current)
        assert len(changed) == 0
        assert prev_id == "s-prev"

    @pytest.mark.asyncio
    async def test_changed_file_detected(self):
        await _seed_completed_snapshot(files=[
            {"path": "a.py", "hash": "h1", "language": "python", "size_bytes": 100},
            {"path": "b.py", "hash": "h2", "language": "python", "size_bytes": 200},
        ])
        current = [
            {"path": "a.py", "hash": "h1", "language": "python", "size_bytes": 100},  # same
            {"path": "b.py", "hash": "CHANGED", "language": "python", "size_bytes": 250},
        ]
        async with test_sessionmaker() as db:
            changed, prev_id = await compute_changed_files(db, "r-inc", current)
        assert len(changed) == 1
        assert changed[0]["path"] == "b.py"

    @pytest.mark.asyncio
    async def test_new_file_detected(self):
        await _seed_completed_snapshot(files=[
            {"path": "a.py", "hash": "h1", "language": "python", "size_bytes": 100},
        ])
        current = [
            {"path": "a.py", "hash": "h1", "language": "python", "size_bytes": 100},
            {"path": "new.py", "hash": "h3", "language": "python", "size_bytes": 50},
        ]
        async with test_sessionmaker() as db:
            changed, prev_id = await compute_changed_files(db, "r-inc", current)
        assert len(changed) == 1
        assert changed[0]["path"] == "new.py"

    @pytest.mark.asyncio
    async def test_all_files_changed(self):
        await _seed_completed_snapshot(files=[
            {"path": "a.py", "hash": "h1", "language": "python", "size_bytes": 100},
        ])
        current = [
            {"path": "a.py", "hash": "DIFFERENT", "language": "python", "size_bytes": 100},
        ]
        async with test_sessionmaker() as db:
            changed, prev_id = await compute_changed_files(db, "r-inc", current)
        assert len(changed) == 1

    @pytest.mark.asyncio
    async def test_empty_current_files(self):
        await _seed_completed_snapshot(files=[
            {"path": "a.py", "hash": "h1", "language": "python", "size_bytes": 100},
        ])
        async with test_sessionmaker() as db:
            changed, prev_id = await compute_changed_files(db, "r-inc", [])
        assert len(changed) == 0


class TestCopyUnchangedSymbols:
    @pytest.mark.asyncio
    async def test_copies_symbols_from_unchanged_files(self):
        await _seed_completed_snapshot(
            symbols=[
                {
                    "name": "Foo", "kind": "class", "fq_name": "a.Foo",
                    "file_path": "a.py", "start_line": 1, "end_line": 10,
                },
                {
                    "name": "Bar", "kind": "class", "fq_name": "b.Bar",
                    "file_path": "b.py", "start_line": 1, "end_line": 10,
                },
            ],
            edges=[
                {
                    "source_fq_name": "a.Foo", "target_fq_name": "b.Bar",
                    "edge_type": "calls", "file_path": "a.py",
                },
            ],
        )
        # Create a new snapshot
        async with test_sessionmaker() as db:
            db.add(RepoSnapshot(
                id="s-new", repo_id="r-inc", status=SnapshotStatus.running,
            ))
            await db.commit()

        # Copy symbols from unchanged files (only b.py changed)
        async with test_sessionmaker() as db:
            sym_copied, edge_copied = await copy_unchanged_symbols(
                db, "s-prev", "s-new", changed_file_paths={"b.py"},
            )
            await db.commit()

        assert sym_copied == 1  # Only a.py symbol copied
        # edge file_path="a.py" is NOT in changed_file_paths={"b.py"},
        # so the edge should be copied too
        assert edge_copied == 1

    @pytest.mark.asyncio
    async def test_no_copy_when_all_files_changed(self):
        await _seed_completed_snapshot(
            symbols=[
                {
                    "name": "Foo", "kind": "class", "fq_name": "a.Foo",
                    "file_path": "a.py", "start_line": 1, "end_line": 10,
                },
            ],
        )
        async with test_sessionmaker() as db:
            db.add(RepoSnapshot(
                id="s-new2", repo_id="r-inc", status=SnapshotStatus.running,
            ))
            await db.commit()

        async with test_sessionmaker() as db:
            sym_copied, edge_copied = await copy_unchanged_symbols(
                db, "s-prev", "s-new2", changed_file_paths={"a.py"},
            )
        assert sym_copied == 0
        assert edge_copied == 0

    @pytest.mark.asyncio
    async def test_copies_all_when_no_files_changed(self):
        await _seed_completed_snapshot(
            symbols=[
                {
                    "name": "Foo", "kind": "class", "fq_name": "a.Foo",
                    "file_path": "a.py", "start_line": 1, "end_line": 10,
                },
                {
                    "name": "Bar", "kind": "class", "fq_name": "b.Bar",
                    "file_path": "b.py", "start_line": 1, "end_line": 10,
                },
            ],
        )
        async with test_sessionmaker() as db:
            db.add(RepoSnapshot(
                id="s-new3", repo_id="r-inc", status=SnapshotStatus.running,
            ))
            await db.commit()

        async with test_sessionmaker() as db:
            sym_copied, _ = await copy_unchanged_symbols(
                db, "s-prev", "s-new3", changed_file_paths=set(),
            )
        assert sym_copied == 2
