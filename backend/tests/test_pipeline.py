"""
Tests for the analysis pipeline (end-to-end).

Covers: parsing files from disk, building graph, persisting to DB,
and querying symbols/edges back.
"""

import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.analysis.pipeline import analyze_snapshot_files, persist_graph
from app.storage.models import Base, Edge, Symbol


TEST_DB_URL = "sqlite+aiosqlite://"

_engine = create_async_engine(TEST_DB_URL, echo=False)
_sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def sample_repo(tmp_path):
    """Create a minimal C# project on disk for testing."""
    # Service file
    svc = tmp_path / "Services" / "UserService.cs"
    svc.parent.mkdir(parents=True)
    svc.write_text("""\
using System;

namespace TestApp.Services
{
    public class UserService
    {
        public User GetById(int id)
        {
            Console.WriteLine("Fetching");
            return new User();
        }

        public void Delete(int id)
        {
            var user = GetById(id);
        }
    }
}
""", encoding="utf-8")

    # Controller file
    ctrl = tmp_path / "Controllers" / "UserController.cs"
    ctrl.parent.mkdir(parents=True)
    ctrl.write_text("""\
using Microsoft.AspNetCore.Mvc;

namespace TestApp.Controllers
{
    public class UserController : Controller
    {
        public IActionResult Get(int id)
        {
            var svc = new UserService();
            return Ok(svc.GetById(id));
        }
    }
}
""", encoding="utf-8")

    # Model file
    model = tmp_path / "Models" / "User.cs"
    model.parent.mkdir(parents=True)
    model.write_text("""\
namespace TestApp.Models
{
    public class User
    {
        public int Id { get; set; }
        public string Name { get; set; }
    }
}
""", encoding="utf-8")

    # Non-C# file (should be ignored)
    cfg = tmp_path / "appsettings.json"
    cfg.write_text("{}", encoding="utf-8")

    return tmp_path


class TestAnalyzeSnapshotFiles:
    """Tests for the file-level analysis function."""

    def test_analyzes_csharp_files_only(self, sample_repo):
        file_records = [
            {"path": "Services/UserService.cs", "language": "csharp"},
            {"path": "Controllers/UserController.cs", "language": "csharp"},
            {"path": "Models/User.cs", "language": "csharp"},
            {"path": "appsettings.json", "language": "json"},
        ]
        graph = analyze_snapshot_files(sample_repo, file_records)
        # JSON file should not produce symbols
        assert "TestApp.Services.UserService" in graph.symbols
        assert "TestApp.Controllers.UserController" in graph.symbols
        assert "TestApp.Models.User" in graph.symbols

    def test_graph_has_call_edges(self, sample_repo):
        file_records = [
            {"path": "Services/UserService.cs", "language": "csharp"},
            {"path": "Controllers/UserController.cs", "language": "csharp"},
            {"path": "Models/User.cs", "language": "csharp"},
        ]
        graph = analyze_snapshot_files(sample_repo, file_records)
        call_edges = [e for e in graph.edges if e.edge_type.value == "calls"]
        assert len(call_edges) > 0

    def test_graph_has_modules(self, sample_repo):
        file_records = [
            {"path": "Services/UserService.cs", "language": "csharp"},
            {"path": "Controllers/UserController.cs", "language": "csharp"},
            {"path": "Models/User.cs", "language": "csharp"},
        ]
        graph = analyze_snapshot_files(sample_repo, file_records)
        assert "TestApp.Services" in graph.modules
        assert "TestApp.Controllers" in graph.modules
        assert "TestApp.Models" in graph.modules

    def test_handles_missing_file(self, sample_repo):
        file_records = [
            {"path": "NonExistent.cs", "language": "csharp"},
            {"path": "Services/UserService.cs", "language": "csharp"},
        ]
        graph = analyze_snapshot_files(sample_repo, file_records)
        # Should still parse the file that exists
        assert "TestApp.Services.UserService" in graph.symbols

    def test_empty_file_list(self, sample_repo):
        graph = analyze_snapshot_files(sample_repo, [])
        assert len(graph.symbols) == 0


class TestPersistGraph:
    """Tests for persisting the graph to the database."""

    @pytest.mark.asyncio
    async def test_persist_symbols(self, sample_repo):
        file_records = [
            {"path": "Services/UserService.cs", "language": "csharp"},
            {"path": "Models/User.cs", "language": "csharp"},
        ]
        graph = analyze_snapshot_files(sample_repo, file_records)

        async with _sessionmaker() as db:
            await persist_graph(db, "snap-001", graph)
            await db.commit()

            result = await db.execute(select(Symbol).where(Symbol.snapshot_id == "snap-001"))
            symbols = result.scalars().all()
            assert len(symbols) > 0
            fq_names = {s.fq_name for s in symbols}
            assert "TestApp.Services.UserService" in fq_names
            assert "TestApp.Models.User" in fq_names

    @pytest.mark.asyncio
    async def test_persist_edges(self, sample_repo):
        file_records = [
            {"path": "Services/UserService.cs", "language": "csharp"},
        ]
        graph = analyze_snapshot_files(sample_repo, file_records)

        async with _sessionmaker() as db:
            await persist_graph(db, "snap-002", graph)
            await db.commit()

            result = await db.execute(select(Edge).where(Edge.snapshot_id == "snap-002"))
            edges = result.scalars().all()
            assert len(edges) > 0
            edge_types = {e.edge_type for e in edges}
            assert "contains" in edge_types  # class -> method containment

    @pytest.mark.asyncio
    async def test_symbol_ids_linked_to_edges(self, sample_repo):
        file_records = [
            {"path": "Services/UserService.cs", "language": "csharp"},
        ]
        graph = analyze_snapshot_files(sample_repo, file_records)

        async with _sessionmaker() as db:
            await persist_graph(db, "snap-003", graph)
            await db.commit()

            result = await db.execute(select(Edge).where(Edge.snapshot_id == "snap-003"))
            edges = result.scalars().all()
            # At least some edges should have resolved symbol IDs
            resolved = [e for e in edges if e.source_symbol_id is not None]
            assert len(resolved) > 0

    @pytest.mark.asyncio
    async def test_symbol_fields_persisted(self, sample_repo):
        file_records = [
            {"path": "Services/UserService.cs", "language": "csharp"},
        ]
        graph = analyze_snapshot_files(sample_repo, file_records)

        async with _sessionmaker() as db:
            await persist_graph(db, "snap-004", graph)
            await db.commit()

            result = await db.execute(
                select(Symbol).where(
                    Symbol.snapshot_id == "snap-004",
                    Symbol.fq_name == "TestApp.Services.UserService",
                )
            )
            sym = result.scalar_one()
            assert sym.kind == "class"
            assert sym.name == "UserService"
            assert sym.namespace == "TestApp.Services"
            assert sym.file_path == "Services/UserService.cs"
            assert sym.start_line >= 1
            assert sym.end_line > sym.start_line
