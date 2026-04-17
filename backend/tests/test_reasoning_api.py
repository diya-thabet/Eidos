"""
Tests for the reasoning API endpoints.

Covers: ask endpoint, classify endpoint, error handling,
response structure validation.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import Edge, Repo, RepoSnapshot, SnapshotStatus, Summary, Symbol
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed():
    async with test_sessionmaker() as db:
        db.add(Repo(id="r-qa", name="test", url="https://example.com", default_branch="main"))
        db.add(
            RepoSnapshot(
                id="s-qa", repo_id="r-qa", commit_sha="abc", status=SnapshotStatus.completed
            )
        )
        await db.flush()

        s = Symbol(
            snapshot_id="s-qa",
            kind="class",
            name="OrderService",
            fq_name="MyApp.OrderService",
            file_path="OrderService.cs",
            start_line=5,
            end_line=50,
            namespace="MyApp",
            modifiers="public",
            signature="public class OrderService",
        )
        db.add(s)
        await db.flush()

        m = Symbol(
            snapshot_id="s-qa",
            kind="method",
            name="CreateOrder",
            fq_name="MyApp.OrderService.CreateOrder",
            file_path="OrderService.cs",
            start_line=10,
            end_line=25,
            namespace="MyApp",
            parent_fq_name="MyApp.OrderService",
            modifiers="public",
            signature="public Order CreateOrder(int userId)",
        )
        db.add(m)
        await db.flush()

        db.add(
            Edge(
                snapshot_id="s-qa",
                source_fq_name="MyApp.OrderService",
                target_fq_name="MyApp.OrderService.CreateOrder",
                edge_type="contains",
                file_path="OrderService.cs",
                line=10,
            )
        )
        db.add(
            Edge(
                snapshot_id="s-qa",
                source_fq_name="MyApp.OrderService.CreateOrder",
                target_fq_name="Validate",
                edge_type="calls",
                file_path="OrderService.cs",
                line=15,
            )
        )

        db.add(
            Summary(
                snapshot_id="s-qa",
                scope_type="module",
                scope_id="MyApp",
                summary_json=json.dumps(
                    {
                        "name": "MyApp",
                        "purpose": "Main module",
                        "citations": [{"file_path": "OrderService.cs"}],
                    }
                ),
            )
        )
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await create_tables()
    await _seed()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestAskEndpoint:
    @pytest.mark.asyncio
    async def test_ask_returns_200(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/ask", json={"question": "What does OrderService do?"}
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_ask_response_structure(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/ask", json={"question": "What does OrderService do?"}
        )
        data = resp.json()
        assert "question" in data
        assert "question_type" in data
        assert "answer_text" in data
        assert "evidence" in data
        assert "confidence" in data
        assert "verification" in data
        assert "related_symbols" in data

    @pytest.mark.asyncio
    async def test_ask_with_target_symbol(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/ask",
            json={"question": "What does this do?", "target_symbol": "MyApp.OrderService"},
        )
        data = resp.json()
        assert "OrderService" in data["answer_text"]

    @pytest.mark.asyncio
    async def test_ask_component_question(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/ask", json={"question": "Explain the OrderService class"}
        )
        data = resp.json()
        assert data["question_type"] == "component"

    @pytest.mark.asyncio
    async def test_ask_architecture_question(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/ask", json={"question": "What is the overall architecture?"}
        )
        data = resp.json()
        assert data["question_type"] == "architecture"

    @pytest.mark.asyncio
    async def test_ask_has_evidence(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/ask",
            json={"question": "Explain OrderService", "target_symbol": "MyApp.OrderService"},
        )
        data = resp.json()
        assert len(data["evidence"]) > 0
        assert any(e["file_path"] == "OrderService.cs" for e in data["evidence"])

    @pytest.mark.asyncio
    async def test_ask_has_verification(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/ask",
            json={"question": "Explain OrderService", "target_symbol": "MyApp.OrderService"},
        )
        data = resp.json()
        assert len(data["verification"]) > 0

    @pytest.mark.asyncio
    async def test_ask_snapshot_not_found(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/nonexistent/ask", json={"question": "Hello"}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_ask_repo_not_found(self, client):
        resp = await client.post(
            "/repos/nonexistent/snapshots/s-qa/ask", json={"question": "Hello"}
        )
        assert resp.status_code == 404


class TestClassifyEndpoint:
    @pytest.mark.asyncio
    async def test_classify_returns_200(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/classify", json={"question": "What does OrderService do?"}
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_classify_response_structure(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/classify", json={"question": "What does OrderService do?"}
        )
        data = resp.json()
        assert data["question_type"] == "component"
        assert data["target_symbol"] == "OrderService"

    @pytest.mark.asyncio
    async def test_classify_impact(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/classify",
            json={"question": "What would break if I change OrderService?"},
        )
        data = resp.json()
        assert data["question_type"] == "impact"

    @pytest.mark.asyncio
    async def test_classify_with_explicit_target(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/classify",
            json={"question": "Explain this", "target_symbol": "MyApp.Foo.Bar"},
        )
        data = resp.json()
        assert data["target_symbol"] == "MyApp.Foo.Bar"

    @pytest.mark.asyncio
    async def test_classify_snapshot_not_found(self, client):
        resp = await client.post("/repos/r-qa/snapshots/bad/classify", json={"question": "Hello"})
        assert resp.status_code == 404
