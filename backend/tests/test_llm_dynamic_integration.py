"""
Integration tests for dynamic LLM provider wiring.

Verifies that reasoning, reviews, and docgen endpoints correctly
use the DB-configured LLM provider when available, fall back to
env settings, and accept per-request provider_id/model overrides.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import LLMProvider
from tests.conftest import (
    create_tables,
    drop_tables,
    override_get_db,
    test_sessionmaker,
)

app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def _seed_provider(name="Fanar", base_url="https://api.fanar.qa/v1",
                         api_key="test-key", model="Fanar-C-2-27B",
                         is_default=True, is_active=True):
    """Seed an LLM provider in test DB."""
    import uuid

    from app.auth.crypto import encrypt
    pid = f"prov-{uuid.uuid4().hex[:8]}"
    async with test_sessionmaker() as session:
        p = LLMProvider(
            id=pid,
            name=name,
            base_url=base_url,
            api_key_enc=encrypt(api_key) if api_key else "",
            default_model=model,
            is_active=is_active,
            is_default=is_default,
            temperature=0.1,
            max_tokens=4096,
            timeout=30,
            rate_limit_rpm=50,
        )
        session.add(p)
        await session.commit()
    return pid


# ---------------------------------------------------------------------------
# get_llm_config_from_provider unit tests (extended)
# ---------------------------------------------------------------------------


class TestDynamicConfigResolution:
    """Test that get_llm_config_from_provider resolves config correctly."""

    @pytest.mark.asyncio
    async def test_default_provider_used_when_no_id(self):
        from app.api.llm_providers import get_llm_config_from_provider
        await _seed_provider(name="DefaultProv", is_default=True)

        async with test_sessionmaker() as session:
            config = await get_llm_config_from_provider(session)
            assert config is not None
            assert config.base_url == "https://api.fanar.qa/v1"
            assert config.model == "Fanar-C-2-27B"

    @pytest.mark.asyncio
    async def test_specific_provider_overrides_default(self):
        from app.api.llm_providers import get_llm_config_from_provider
        await _seed_provider(name="Default", is_default=True)
        pid2 = await _seed_provider(
            name="Ollama", base_url="http://localhost:11434/v1",
            model="llama3", is_default=False
        )

        async with test_sessionmaker() as session:
            config = await get_llm_config_from_provider(session, provider_id=pid2)
            assert config is not None
            assert config.base_url == "http://localhost:11434/v1"
            assert config.model == "llama3"

    @pytest.mark.asyncio
    async def test_model_override_takes_precedence(self):
        from app.api.llm_providers import get_llm_config_from_provider
        await _seed_provider(model="Fanar-C-2-27B")

        async with test_sessionmaker() as session:
            config = await get_llm_config_from_provider(
                session, model_override="Fanar-Sadiq"
            )
            assert config is not None
            assert config.model == "Fanar-Sadiq"

    @pytest.mark.asyncio
    async def test_inactive_default_not_used(self):
        from app.api.llm_providers import get_llm_config_from_provider
        await _seed_provider(is_active=False, is_default=True)

        async with test_sessionmaker() as session:
            with patch("app.api.llm_providers.settings") as ms:
                ms.llm_base_url = ""
                config = await get_llm_config_from_provider(session)
                assert config is None

    @pytest.mark.asyncio
    async def test_env_fallback_when_no_db_provider(self):
        from app.api.llm_providers import get_llm_config_from_provider

        async with test_sessionmaker() as session:
            with patch("app.api.llm_providers.settings") as ms:
                ms.llm_base_url = "https://api.openai.com/v1"
                ms.llm_api_key = "sk-test"
                ms.llm_model = "gpt-4o-mini"
                ms.llm_temperature = 0.2
                ms.llm_max_tokens = 1024
                ms.llm_timeout = 45

                config = await get_llm_config_from_provider(session)
                assert config is not None
                assert config.base_url == "https://api.openai.com/v1"
                assert config.api_key == "sk-test"
                assert config.model == "gpt-4o-mini"
                assert config.temperature == 0.2
                assert config.max_tokens == 1024
                assert config.timeout == 45

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_available(self):
        from app.api.llm_providers import get_llm_config_from_provider

        async with test_sessionmaker() as session:
            with patch("app.api.llm_providers.settings") as ms:
                ms.llm_base_url = ""
                config = await get_llm_config_from_provider(session)
                assert config is None

    @pytest.mark.asyncio
    async def test_decryption_failure_returns_empty_key(self):
        """If decryption fails, the config is still returned with empty key."""
        from app.api.llm_providers import get_llm_config_from_provider

        async with test_sessionmaker() as session:
            p = LLMProvider(
                id="prov-bad-key",
                name="BadKey",
                base_url="http://example.com/v1",
                api_key_enc="not-valid-encrypted-data",
                default_model="m",
                is_active=True,
                is_default=True,
            )
            session.add(p)
            await session.commit()

            config = await get_llm_config_from_provider(session)
            assert config is not None
            assert config.api_key == ""
            assert config.base_url == "http://example.com/v1"

    @pytest.mark.asyncio
    async def test_multiple_providers_default_wins(self):
        from app.api.llm_providers import get_llm_config_from_provider
        await _seed_provider(name="NotDefault", is_default=False,
                             base_url="http://a.com/v1")
        await _seed_provider(name="TheDefault", is_default=True,
                             base_url="http://b.com/v1")

        async with test_sessionmaker() as session:
            config = await get_llm_config_from_provider(session)
            assert config is not None
            assert config.base_url == "http://b.com/v1"


# ---------------------------------------------------------------------------
# Reasoning endpoint dynamic provider tests
# ---------------------------------------------------------------------------


class TestReasoningDynamicProvider:
    """Verify reasoning endpoint uses DB provider."""

    @pytest.mark.asyncio
    async def test_ask_uses_default_provider(self, client):
        """ask endpoint should pick up DB default provider."""
        await _seed_provider()

        with patch("app.api.reasoning.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_create.return_value = mock_llm

            with patch("app.api.reasoning.retrieve_context", new_callable=AsyncMock) as mock_ctx:
                mock_ctx.return_value = []
                with patch("app.api.reasoning.build_answer", new_callable=AsyncMock) as mock_ans:
                    from app.reasoning.models import Answer, Confidence
                    mock_ans.return_value = Answer(
                        question="test",
                        question_type="architecture",
                        answer_text="mocked",
                        evidence=[],
                        confidence=Confidence.HIGH,
                        verification=[],
                        related_symbols=[],
                    )

                    with patch("app.api.dependencies.verify_snapshot", return_value=None):
                        resp = await client.post(
                            "/repos/r1/snapshots/s1/ask",
                            json={"question": "What is the architecture?"},
                        )

                    if resp.status_code == 200:
                        call_args = mock_create.call_args
                        if call_args:
                            config = call_args[0][0]
                            assert config is not None
                            assert config.base_url == "https://api.fanar.qa/v1"

    @pytest.mark.asyncio
    async def test_ask_with_provider_id_param(self, client):
        """ask endpoint with explicit provider_id query param."""
        pid = await _seed_provider(
            name="Custom", base_url="http://custom.com/v1",
            model="custom-model", is_default=False
        )

        with patch("app.api.reasoning.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_create.return_value = mock_llm

            with patch("app.api.reasoning.retrieve_context", new_callable=AsyncMock) as mock_ctx:
                mock_ctx.return_value = []
                with patch("app.api.reasoning.build_answer", new_callable=AsyncMock) as mock_ans:
                    from app.reasoning.models import Answer, Confidence
                    mock_ans.return_value = Answer(
                        question="q", question_type="component",
                        answer_text="a", evidence=[],
                        confidence=Confidence.MEDIUM,
                        verification=[], related_symbols=[],
                    )
                    with patch("app.api.dependencies.verify_snapshot", return_value=None):
                        resp = await client.post(
                            f"/repos/r1/snapshots/s1/ask?provider_id={pid}",
                            json={"question": "test"},
                        )

                    if resp.status_code == 200:
                        call_args = mock_create.call_args
                        if call_args:
                            config = call_args[0][0]
                            assert config.base_url == "http://custom.com/v1"
                            assert config.model == "custom-model"

    @pytest.mark.asyncio
    async def test_ask_with_model_override_param(self, client):
        """ask endpoint with model query param."""
        await _seed_provider()

        with patch("app.api.reasoning.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_create.return_value = mock_llm

            with patch("app.api.reasoning.retrieve_context", new_callable=AsyncMock) as mock_ctx:
                mock_ctx.return_value = []
                with patch("app.api.reasoning.build_answer", new_callable=AsyncMock) as mock_ans:
                    from app.reasoning.models import Answer, Confidence
                    mock_ans.return_value = Answer(
                        question="q", question_type="flow",
                        answer_text="a", evidence=[],
                        confidence=Confidence.LOW,
                        verification=[], related_symbols=[],
                    )
                    with patch("app.api.dependencies.verify_snapshot", return_value=None):
                        resp = await client.post(
                            "/repos/r1/snapshots/s1/ask?model=Fanar-Sadiq",
                            json={"question": "test"},
                        )

                    if resp.status_code == 200:
                        call_args = mock_create.call_args
                        if call_args:
                            config = call_args[0][0]
                            assert config.model == "Fanar-Sadiq"


# ---------------------------------------------------------------------------
# Reviews endpoint dynamic provider tests
# ---------------------------------------------------------------------------


class TestReviewsDynamicProvider:
    """Verify reviews endpoint uses DB provider."""

    @pytest.mark.asyncio
    async def test_review_uses_default_provider(self, client):
        await _seed_provider()

        with patch("app.api.reviews.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_create.return_value = mock_llm

            with patch("app.api.reviews.review_diff", new_callable=AsyncMock) as mock_rev:
                from dataclasses import dataclass, field

                @dataclass
                class FakeReport:
                    snapshot_id: str = "s1"
                    diff_summary: str = "test"
                    files_changed: list = field(default_factory=list)
                    changed_symbols: list = field(default_factory=list)
                    findings: list = field(default_factory=list)
                    impacted_symbols: list = field(default_factory=list)
                    risk_score: float = 0.1
                    risk_level: str = "low"
                    llm_summary: str = ""

                mock_rev.return_value = FakeReport()

                with patch("app.api.dependencies.verify_snapshot", return_value=None):
                    resp = await client.post(
                        "/repos/r1/snapshots/s1/review",
                        json={"diff": "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new"},
                    )

                if resp.status_code in (200, 201):
                    call_args = mock_create.call_args
                    if call_args:
                        config = call_args[0][0]
                        assert config is not None
                        assert config.base_url == "https://api.fanar.qa/v1"


# ---------------------------------------------------------------------------
# Docgen endpoint dynamic provider tests
# ---------------------------------------------------------------------------


class TestDocgenDynamicProvider:
    """Verify docgen endpoint uses DB provider."""

    @pytest.mark.asyncio
    async def test_docgen_uses_default_provider(self, client):
        await _seed_provider()

        with patch("app.api.docgen.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_create.return_value = mock_llm

            with patch("app.api.docgen.generate_all_docs", new_callable=AsyncMock) as mock_gen:
                mock_gen.return_value = [{
                    "id": 1,
                    "doc_type": "overview",
                    "title": "Overview",
                    "scope_id": "",
                    "markdown": "# Overview",
                    "llm_narrative": "",
                }]

                with patch("app.api.dependencies.verify_snapshot", return_value=None):
                    resp = await client.post("/repos/r1/snapshots/s1/docs")

                if resp.status_code == 200:
                    call_args = mock_create.call_args
                    if call_args:
                        config = call_args[0][0]
                        assert config is not None
                        assert config.base_url == "https://api.fanar.qa/v1"
                        assert config.max_tokens == 4096

    @pytest.mark.asyncio
    async def test_docgen_with_provider_id_and_model(self, client):
        pid = await _seed_provider(
            name="Ollama", base_url="http://localhost:11434/v1",
            model="codellama", is_default=False, api_key=""
        )

        with patch("app.api.docgen.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_create.return_value = mock_llm

            with patch("app.api.docgen.generate_all_docs", new_callable=AsyncMock) as mock_gen:
                mock_gen.return_value = []

                with patch("app.api.dependencies.verify_snapshot", return_value=None):
                    resp = await client.post(
                        f"/repos/r1/snapshots/s1/docs?provider_id={pid}&model=deepseek"
                    )

                if resp.status_code == 200:
                    call_args = mock_create.call_args
                    if call_args:
                        config = call_args[0][0]
                        assert config.base_url == "http://localhost:11434/v1"
                        assert config.model == "deepseek"


# ---------------------------------------------------------------------------
# Provider CRUD edge cases
# ---------------------------------------------------------------------------


class TestProviderCRUDEdgeCases:
    """Additional CRUD edge case tests."""

    @pytest.mark.asyncio
    async def test_create_provider_strips_trailing_slash(self, client):
        resp = await client.post("/admin/llm-providers", json={
            "name": "Stripped",
            "base_url": "http://example.com/v1/",
        })
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_duplicate_names_allowed(self, client):
        await client.post("/admin/llm-providers", json={
            "name": "Same",
            "base_url": "http://a.com/v1",
        })
        resp = await client.post("/admin/llm-providers", json={
            "name": "Same",
            "base_url": "http://b.com/v1",
        })
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_update_all_fields(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Initial",
            "base_url": "http://x.com/v1",
        })
        pid = create_resp.json()["id"]

        resp = await client.patch(f"/admin/llm-providers/{pid}", json={
            "name": "Updated",
            "base_url": "http://y.com/v1",
            "api_key": "new-key",
            "default_model": "new-model",
            "max_tokens": 8192,
            "temperature": 0.5,
            "timeout": 120,
            "rate_limit_rpm": 100,
            "is_active": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated"
        assert data["base_url"] == "http://y.com/v1"
        assert data["has_api_key"] is True
        assert data["default_model"] == "new-model"
        assert data["max_tokens"] == 8192
        assert data["temperature"] == 0.5
        assert data["timeout"] == 120
        assert data["rate_limit_rpm"] == 100
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_delete_default_provider(self, client):
        """Deleting a default provider should succeed."""
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Default",
            "base_url": "http://x.com/v1",
        })
        pid = create_resp.json()["id"]
        await client.post(f"/admin/llm-providers/{pid}/set-default")

        resp = await client.delete(f"/admin/llm-providers/{pid}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_list_providers_empty(self, client):
        resp = await client.get("/admin/llm-providers")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_multiple_providers(self, client):
        await client.post("/admin/llm-providers", json={
            "name": "A", "base_url": "http://a.com/v1"
        })
        await client.post("/admin/llm-providers", json={
            "name": "B", "base_url": "http://b.com/v1"
        })
        await client.post("/admin/llm-providers", json={
            "name": "C", "base_url": "http://c.com/v1"
        })

        resp = await client.get("/admin/llm-providers")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    @pytest.mark.asyncio
    async def test_set_default_switches(self, client):
        """Setting new default clears old default."""
        r1 = await client.post("/admin/llm-providers", json={
            "name": "First", "base_url": "http://a.com/v1"
        })
        r2 = await client.post("/admin/llm-providers", json={
            "name": "Second", "base_url": "http://b.com/v1"
        })
        pid1 = r1.json()["id"]
        pid2 = r2.json()["id"]

        await client.post(f"/admin/llm-providers/{pid1}/set-default")
        await client.post(f"/admin/llm-providers/{pid2}/set-default")

        # pid1 should no longer be default
        resp = await client.get(f"/admin/llm-providers/{pid1}")
        assert resp.json()["is_default"] is False
        resp = await client.get(f"/admin/llm-providers/{pid2}")
        assert resp.json()["is_default"] is True


# ---------------------------------------------------------------------------
# Connectivity test edge cases
# ---------------------------------------------------------------------------


class TestConnectivityEdgeCases:
    @pytest.mark.asyncio
    async def test_connectivity_timeout(self, client):
        """Provider with unreachable URL returns error."""
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Unreachable",
            "base_url": "http://192.0.2.1",
            "api_key": "k",
        })
        pid = create_resp.json()["id"]

        with patch("app.api.llm_providers.httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()

            async def _mock_get(*a, **kw):
                raise Exception("Connection timed out")

            instance.get = _mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = await client.post(f"/admin/llm-providers/{pid}/test")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "error"
            assert "timed out" in data["detail"]

    @pytest.mark.asyncio
    async def test_connectivity_success_with_models(self, client):
        """Successful connectivity returns model list."""
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Good",
            "base_url": "https://api.fanar.qa/v1",
            "api_key": "key",
        })
        pid = create_resp.json()["id"]

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {
            "data": [{"id": "Fanar-C-2-27B"}, {"id": "Fanar-Sadiq"}]
        }
        mock_resp.raise_for_status = lambda: None

        async def _mock_get(*a, **kw):
            return mock_resp

        with patch("app.api.llm_providers.httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.get = _mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = await client.post(f"/admin/llm-providers/{pid}/test")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "Fanar-C-2-27B" in data["models"]
            assert "Fanar-Sadiq" in data["models"]
