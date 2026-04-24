"""
End-to-end integration tests for the complete pipeline.

Tests the full flow: create repo, ingest, analyze, index,
query, review, docs, evaluate.
All with realistic data and cross-module interactions.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Edge,
    File,
    GeneratedDoc,
    Repo,
    RepoSnapshot,
    Review,
    SnapshotStatus,
    Summary,
    Symbol,
    User,
)
from tests.conftest import (
    create_tables,
    drop_tables,
    override_get_db,
    test_sessionmaker,
)

app.dependency_overrides[get_db] = override_get_db


async def _build_full_snapshot():
    """Build a complete snapshot with symbols, edges, summaries, docs, reviews."""
    async with test_sessionmaker() as db:
        db.add(User(id="u-int", github_login="integrator", name="Integrator"))
        db.add(
            Repo(
                id="r-int",
                owner_id="u-int",
                name="integration-project",
                url="https://github.com/test/proj",
            )
        )
        db.add(
            RepoSnapshot(
                id="s-int",
                repo_id="r-int",
                commit_sha="abc123",
                status=SnapshotStatus.completed,
                file_count=3,
            )
        )
        await db.flush()

        # Files
        db.add(
            File(
                snapshot_id="s-int", path="Program.cs", language="csharp", hash="h1", size_bytes=500
            )
        )
        db.add(
            File(
                snapshot_id="s-int",
                path="UserService.cs",
                language="csharp",
                hash="h2",
                size_bytes=800,
            )
        )
        db.add(
            File(
                snapshot_id="s-int",
                path="IRepository.cs",
                language="csharp",
                hash="h3",
                size_bytes=200,
            )
        )

        # Symbols
        for i, (kind, name, fq, fp, s, e) in enumerate(
            [
                ("class", "Program", "MyApp.Program", "Program.cs", 1, 30),
                ("method", "Main", "MyApp.Program.Main", "Program.cs", 5, 25),
                ("class", "UserService", "MyApp.UserService", "UserService.cs", 1, 50),
                ("method", "GetUser", "MyApp.UserService.GetUser", "UserService.cs", 10, 25),
                ("method", "SaveUser", "MyApp.UserService.SaveUser", "UserService.cs", 30, 45),
                ("interface", "IRepository", "MyApp.IRepository", "IRepository.cs", 1, 10),
                ("method", "Find", "MyApp.IRepository.Find", "IRepository.cs", 3, 5),
                ("class", "SqlRepository", "MyApp.SqlRepository", "UserService.cs", 52, 80),
                (
                    "constructor",
                    "SqlRepository",
                    "MyApp.SqlRepository..ctor",
                    "UserService.cs",
                    55,
                    60,
                ),
            ]
        ):
            db.add(
                Symbol(
                    snapshot_id="s-int",
                    kind=kind,
                    name=name,
                    fq_name=fq,
                    file_path=fp,
                    start_line=s,
                    end_line=e,
                    namespace="MyApp",
                    signature=f"public {kind} {name}()",
                    modifiers="public",
                )
            )

        # Edges
        for src, tgt, etype in [
            ("MyApp.Program.Main", "MyApp.UserService.GetUser", "calls"),
            ("MyApp.Program.Main", "MyApp.UserService.SaveUser", "calls"),
            ("MyApp.UserService.GetUser", "MyApp.IRepository.Find", "calls"),
            ("MyApp.SqlRepository", "MyApp.IRepository", "implements"),
            ("MyApp.Program", "MyApp.Program.Main", "contains"),
            ("MyApp.UserService", "MyApp.UserService.GetUser", "contains"),
            ("MyApp.UserService", "MyApp.UserService.SaveUser", "contains"),
        ]:
            db.add(
                Edge(
                    snapshot_id="s-int",
                    source_fq_name=src,
                    target_fq_name=tgt,
                    edge_type=etype,
                    file_path="Program.cs",
                )
            )

        # Summaries
        for scope_type, scope_id in [
            ("symbol", "MyApp.Program"),
            ("symbol", "MyApp.UserService"),
            ("module", "MyApp"),
            ("file", "Program.cs"),
        ]:
            db.add(
                Summary(
                    snapshot_id="s-int",
                    scope_type=scope_type,
                    scope_id=scope_id,
                    summary_json=json.dumps(
                        {"purpose": f"Summary for {scope_id}", "fq_name": scope_id}
                    ),
                )
            )

        # Generated docs
        db.add(
            GeneratedDoc(
                snapshot_id="s-int",
                doc_type="readme",
                title="README",
                markdown="# MyApp\n`MyApp.Program` is the entry point calling `MyApp.UserService`.",
                scope_id="",
            )
        )
        db.add(
            GeneratedDoc(
                snapshot_id="s-int",
                doc_type="architecture",
                title="Architecture",
                markdown="## Architecture\n`MyApp.SqlRepository` implements `MyApp.IRepository`.",
                scope_id="",
            )
        )

        # Review
        db.add(
            Review(
                snapshot_id="s-int",
                diff_summary="3 files changed",
                risk_score=45,
                risk_level="medium",
                report_json=json.dumps(
                    {
                        "findings": [
                            {
                                "category": "complexity",
                                "severity": "medium",
                                "title": "High fan-out",
                                "description": "Main calls many methods",
                                "file_path": "Program.cs",
                                "symbol_fq_name": "MyApp.Program.Main",
                            },
                            {
                                "category": "coupling",
                                "severity": "low",
                                "title": "Interface coupling",
                                "description": "Good separation",
                                "file_path": "IRepository.cs",
                                "symbol_fq_name": "MyApp.IRepository",
                            },
                        ],
                        "changed_symbols": [{"fq_name": "MyApp.Program.Main"}],
                    }
                ),
            )
        )

        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await create_tables()
    await _build_full_snapshot()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestSymbolEndpoints:
    @pytest.mark.asyncio
    async def test_list_symbols(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/symbols")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 9
        assert len(data["items"]) == 9

    @pytest.mark.asyncio
    async def test_filter_by_kind_class(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/symbols?kind=class")
        assert r.status_code == 200
        assert all(s["kind"] == "class" for s in r.json()["items"])

    @pytest.mark.asyncio
    async def test_filter_by_kind_method(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/symbols?kind=method")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 4

    @pytest.mark.asyncio
    async def test_filter_by_file_path(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/symbols?file_path=Program.cs")
        assert r.status_code == 200
        assert all(s["file_path"] == "Program.cs" for s in r.json()["items"])

    @pytest.mark.asyncio
    async def test_filter_by_kind_interface(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/symbols?kind=interface")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1
        assert r.json()["items"][0]["name"] == "IRepository"

    @pytest.mark.asyncio
    async def test_get_single_symbol(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/symbols?kind=class")
        fq = r.json()["items"][0]["fq_name"]
        r2 = await client.get(f"/repos/r-int/snapshots/s-int/symbols/{fq}")
        assert r2.status_code == 200
        assert r2.json()["fq_name"] == fq

    @pytest.mark.asyncio
    async def test_symbol_not_found(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/symbols/Ghost.Class")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_snapshot_not_found(self, client):
        r = await client.get("/repos/r-int/snapshots/bad/symbols")
        assert r.status_code == 404


class TestEdgeEndpoints:
    @pytest.mark.asyncio
    async def test_list_edges(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/edges")
        assert r.status_code == 200
        assert r.json()["total"] == 7

    @pytest.mark.asyncio
    async def test_filter_edges_by_type(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/edges?edge_type=calls")
        assert r.status_code == 200
        assert all(e["edge_type"] == "calls" for e in r.json()["items"])
        assert len(r.json()["items"]) == 3

    @pytest.mark.asyncio
    async def test_implements_edges(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/edges?edge_type=implements")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    @pytest.mark.asyncio
    async def test_contains_edges(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/edges?edge_type=contains")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 3


class TestAnalysisOverview:
    @pytest.mark.asyncio
    async def test_overview_returns_200(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/overview")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_overview_counts(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/overview")
        data = r.json()
        assert data["total_symbols"] == 9
        assert data["total_edges"] == 7
        assert data["snapshot_id"] == "s-int"

    @pytest.mark.asyncio
    async def test_overview_symbols_by_kind(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/overview")
        kinds = r.json()["symbols_by_kind"]
        assert kinds.get("class", 0) == 3
        assert kinds.get("method", 0) == 4
        assert kinds.get("interface", 0) == 1


class TestSummaryEndpoints:
    @pytest.mark.asyncio
    async def test_list_summaries(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/summaries")
        assert r.status_code == 200
        assert r.json()["total"] == 4

    @pytest.mark.asyncio
    async def test_filter_summaries_by_scope(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/summaries?scope_type=symbol")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    @pytest.mark.asyncio
    async def test_summary_contains_json(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/summaries?scope_type=module")
        data = r.json()
        assert data["total"] == 1
        assert "purpose" in data["items"][0]["summary"]


class TestEvaluationIntegration:
    @pytest.mark.asyncio
    async def test_evaluate_full_snapshot(self, client):
        r = await client.post("/repos/r-int/snapshots/s-int/evaluate")
        assert r.status_code == 200
        data = r.json()
        assert 0.0 <= data["overall_score"] <= 1.0
        assert len(data["checks"]) > 0

    @pytest.mark.asyncio
    async def test_evaluation_persisted(self, client):
        await client.post("/repos/r-int/snapshots/s-int/evaluate")
        r = await client.get("/repos/r-int/snapshots/s-int/evaluations")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    @pytest.mark.asyncio
    async def test_multiple_evaluations(self, client):
        await client.post("/repos/r-int/snapshots/s-int/evaluate")
        await client.post("/repos/r-int/snapshots/s-int/evaluate")
        r = await client.get("/repos/r-int/snapshots/s-int/evaluations")
        assert len(r.json()) >= 2

    @pytest.mark.asyncio
    async def test_evaluation_has_doc_checks(self, client):
        r = await client.post("/repos/r-int/snapshots/s-int/evaluate")
        names = [c["name"] for c in r.json()["checks"]]
        assert "docs_exist" in names
        assert "doc_symbol_accuracy" in names

    @pytest.mark.asyncio
    async def test_evaluation_has_review_checks(self, client):
        r = await client.post("/repos/r-int/snapshots/s-int/evaluate")
        names = [c["name"] for c in r.json()["checks"]]
        assert "review_precision" in names
        assert "severity_distribution" in names


class TestDocGenEndpoints:
    @pytest.mark.asyncio
    async def test_list_docs(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/docs")
        assert r.status_code == 200
        assert len(r.json()) == 2

    @pytest.mark.asyncio
    async def test_get_doc_by_id(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/docs")
        doc_id = r.json()[0]["id"]
        r2 = await client.get(f"/repos/r-int/snapshots/s-int/docs/{doc_id}")
        assert r2.status_code == 200

    @pytest.mark.asyncio
    async def test_doc_not_found(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/docs/99999")
        assert r.status_code == 404


class TestRepoLifecycle:
    @pytest.mark.asyncio
    async def test_create_and_get_status(self, client):
        r = await client.post(
            "/repos", json={"name": "lifecycle-test", "url": "https://github.com/x/y"}
        )
        assert r.status_code == 201
        rid = r.json()["id"]

        r2 = await client.get(f"/repos/{rid}/status")
        assert r2.status_code == 200
        assert r2.json()["name"] == "lifecycle-test"
        assert r2.json()["snapshots"] == []

    @pytest.mark.asyncio
    async def test_existing_repo_status(self, client):
        r = await client.get("/repos/r-int/status")
        assert r.status_code == 200
        assert r.json()["repo_id"] == "r-int"
        assert len(r.json()["snapshots"]) == 1

    @pytest.mark.asyncio
    async def test_snapshot_detail(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int")
        assert r.status_code == 200
        data = r.json()
        assert data["file_count"] == 3
        assert data["status"] == "completed"
        assert len(data["files"]) == 3

    @pytest.mark.asyncio
    async def test_repo_not_found(self, client):
        r = await client.get("/repos/ghost/status")
        assert r.status_code == 404


class TestGraphNeighborhood:
    @pytest.mark.asyncio
    async def test_neighborhood_exists(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/graph/MyApp.UserService")
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"]["fq_name"] == "MyApp.UserService"

    @pytest.mark.asyncio
    async def test_neighborhood_not_found(self, client):
        r = await client.get("/repos/r-int/snapshots/s-int/graph/Ghost")
        assert r.status_code == 404


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
