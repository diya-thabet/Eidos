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
from app.reasoning.answer_builder import build_answer
from app.reasoning.models import Question, QuestionType, RetrievalContext
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
            source_code=(
                "public class OrderService { "
                "public Order CreateOrder(int userId) { return new Order(); } }"
            ),
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
            source_code=(
                "public Order CreateOrder(int userId) { "
                "Validate(userId); return new Order(); }"
            ),
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
        assert "rag_context" in data

    @pytest.mark.asyncio
    async def test_ask_returns_advanced_rag_context(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/ask",
            json={"question": "Explain OrderService CreateOrder flow"},
        )
        data = resp.json()
        ctx = data["rag_context"]
        assert ctx["summary"]["target_symbol"]
        assert ctx["summary"]["snippet_count"] > 0
        assert ctx["snippets"]
        assert "source_snippets" in ctx["summary"]["confidence_signals"]

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
    async def test_ask_codebase_overview_question_uses_architecture_context(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/ask",
            json={"question": "explain me what this codebase do exactly"},
        )
        data = resp.json()
        assert data["question_type"] == "architecture"
        assert data["confidence"] != "low"
        assert "OrderService" in data["answer_text"]
        assert data["rag_context"]["summary"]["symbol_count"] > 0

    @pytest.mark.asyncio
    async def test_ask_generic_code_explanation_is_human_readable(self, client):
        resp = await client.post(
            "/repos/r-qa/snapshots/s-qa/ask",
            json={"question": "hi can u explain the code here ?"},
        )
        data = resp.json()
        assert "Plain-English explanation" in data["answer_text"]
        assert "What the main parts do" in data["answer_text"]
        assert "declared in" not in data["answer_text"]

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
    async def test_llm_string_evidence_does_not_crash(self):
        mock_llm = AsyncMock()
        mock_llm.chat_json.return_value = {
            "answer": "OrderService creates orders after validation.",
            "confidence": "medium",
            "evidence": ["OrderService.cs shows the class and CreateOrder method."],
            "verification": ["Open OrderService.cs and inspect CreateOrder."],
        }
        context = RetrievalContext(
            symbols=[
                {
                    "fq_name": "MyApp.OrderService",
                    "kind": "class",
                    "file_path": "OrderService.cs",
                    "start_line": 5,
                    "end_line": 50,
                }
            ]
        )

        answer = await build_answer(
            Question(
                text="Explain OrderService",
                snapshot_id="s-qa",
                question_type=QuestionType.COMPONENT,
            ),
            context,
            mock_llm,
        )

        assert answer.answer_text == "OrderService creates orders after validation."
        assert (
            answer.evidence[0].relevance
            == "OrderService.cs shows the class and CreateOrder method."
        )
        assert answer.verification[0].description == "Open OrderService.cs and inspect CreateOrder."

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
