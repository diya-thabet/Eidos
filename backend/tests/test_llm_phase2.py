"""
Tests for Phase 2: Dynamic Model Selection API.

Covers: model listing (all providers), per-provider model listing,
direct chat endpoint, and API key auto-validation on update.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from tests.conftest import (
    create_tables,
    drop_tables,
    override_get_db,
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


async def _create_provider(client, name="Fanar", base_url="https://api.fanar.qa/v1",
                           api_key="test-key", model="Fanar-C-2-27B"):
    resp = await client.post("/admin/llm-providers", json={
        "name": name,
        "base_url": base_url,
        "api_key": api_key,
        "default_model": model,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Model Listing â€” All Providers
# ---------------------------------------------------------------------------


class TestListAllModels:
    @pytest.mark.asyncio
    async def test_no_providers_returns_empty(self, client):
        resp = await client.get("/admin/llm-providers/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["models"] == []
        assert data["providers"] == 0

    @pytest.mark.asyncio
    async def test_aggregates_models_from_multiple_providers(self, client):
        await _create_provider(client, name="Fanar",
                                      base_url="https://api.fanar.qa/v1")
        await _create_provider(client, name="OpenAI",
                                      base_url="https://api.openai.com/v1",
                                      model="gpt-4o-mini")

        mock_fanar_resp = AsyncMock()
        mock_fanar_resp.json = lambda: {
            "data": [{"id": "Fanar-C-2-27B"}, {"id": "Fanar-Sadiq"}]
        }
        mock_fanar_resp.raise_for_status = lambda: None

        mock_openai_resp = AsyncMock()
        mock_openai_resp.json = lambda: {
            "data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}]
        }
        mock_openai_resp.raise_for_status = lambda: None

        call_count = [0]

        async def _mock_get(*args, **kwargs):
            call_count[0] += 1
            url = args[0] if args else kwargs.get("url", "")
            if "fanar" in str(url):
                return mock_fanar_resp
            return mock_openai_resp

        with patch("app.api.llm_providers.httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.get = _mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = await client.get("/admin/llm-providers/models")

        assert resp.status_code == 200
        data = resp.json()
        assert data["providers"] == 2
        model_ids = [m["id"] for m in data["models"]]
        assert "Fanar-C-2-27B" in model_ids
        assert "Fanar-Sadiq" in model_ids
        assert "gpt-4o-mini" in model_ids
        assert "gpt-4o" in model_ids

    @pytest.mark.asyncio
    async def test_handles_provider_failure_gracefully(self, client):
        await _create_provider(client, name="Good",
                               base_url="https://good.com/v1")
        await _create_provider(client, name="Bad",
                               base_url="https://bad.com/v1")

        async def _mock_get(*args, **kwargs):
            url = str(args[0] if args else "")
            if "bad" in url:
                raise Exception("Connection refused")
            resp = AsyncMock()
            resp.json = lambda: {"data": [{"id": "model-a"}]}
            resp.raise_for_status = lambda: None
            return resp

        with patch("app.api.llm_providers.httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.get = _mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = await client.get("/admin/llm-providers/models")

        assert resp.status_code == 200
        data = resp.json()
        # Should still get models from the good provider
        assert data["providers"] == 2
        # At least some results came through
        assert len(data["results"]) == 2

    @pytest.mark.asyncio
    async def test_inactive_provider_excluded(self, client):
        pid = await _create_provider(client)
        # Deactivate it
        await client.patch(f"/admin/llm-providers/{pid}", json={"is_active": False})

        resp = await client.get("/admin/llm-providers/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["providers"] == 0
        assert data["models"] == []

    @pytest.mark.asyncio
    async def test_models_include_provider_info(self, client):
        await _create_provider(client, name="TestProv", model="default-m")

        mock_resp = AsyncMock()
        mock_resp.json = lambda: {"data": [{"id": "default-m"}, {"id": "other-m"}]}
        mock_resp.raise_for_status = lambda: None

        async def _mock_get(*a, **kw):
            return mock_resp

        with patch("app.api.llm_providers.httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.get = _mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = await client.get("/admin/llm-providers/models")

        data = resp.json()
        for m in data["models"]:
            assert "provider_id" in m
            assert "provider_name" in m
            assert "is_default" in m
        # The default model should be marked
        default_models = [m for m in data["models"] if m["is_default"]]
        assert len(default_models) == 1
        assert default_models[0]["id"] == "default-m"


# ---------------------------------------------------------------------------
# Model Listing â€” Per Provider
# ---------------------------------------------------------------------------


class TestListProviderModels:
    @pytest.mark.asyncio
    async def test_list_models_for_provider(self, client):
        pid = await _create_provider(client, model="Fanar-C-2-27B")

        mock_resp = AsyncMock()
        mock_resp.json = lambda: {
            "data": [
                {"id": "Fanar-C-2-27B", "owned_by": "fanar"},
                {"id": "Fanar-Sadiq", "owned_by": "fanar"},
            ]
        }
        mock_resp.raise_for_status = lambda: None

        async def _mock_get(*a, **kw):
            return mock_resp

        with patch("app.api.llm_providers.httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.get = _mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = await client.get(f"/admin/llm-providers/{pid}/models")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["provider"] == "Fanar"
        assert data["default_model"] == "Fanar-C-2-27B"
        assert len(data["models"]) == 2
        # Check is_default flag
        assert data["models"][0]["is_default"] is True
        assert data["models"][1]["is_default"] is False

    @pytest.mark.asyncio
    async def test_list_models_404_for_missing_provider(self, client):
        resp = await client.get("/admin/llm-providers/nonexistent/models")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_models_handles_connection_error(self, client):
        pid = await _create_provider(client)

        async def _mock_get(*a, **kw):
            raise Exception("Connection refused")

        with patch("app.api.llm_providers.httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.get = _mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = await client.get(f"/admin/llm-providers/{pid}/models")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert data["models"] == []


# ---------------------------------------------------------------------------
# Direct Chat Endpoint
# ---------------------------------------------------------------------------


class TestDirectChat:
    @pytest.mark.asyncio
    async def test_chat_with_default_provider(self, client):
        pid = await _create_provider(client)
        await client.post(f"/admin/llm-providers/{pid}/set-default")

        with patch("app.api.llm_providers.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_llm.chat.return_value = "Hello! I can help with code."
            mock_create.return_value = mock_llm

            resp = await client.post("/admin/llm-providers/chat", json={
                "message": "Hello",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Hello! I can help with code."
        assert "provider" in data
        assert "model" in data

    @pytest.mark.asyncio
    async def test_chat_with_specific_provider(self, client):
        pid = await _create_provider(client, name="Ollama",
                                     base_url="http://localhost:11434/v1",
                                     model="llama3")

        with patch("app.api.llm_providers.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_llm.chat.return_value = "Ollama response"
            mock_create.return_value = mock_llm

            resp = await client.post("/admin/llm-providers/chat", json={
                "message": "Hi",
                "provider_id": pid,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Ollama response"

    @pytest.mark.asyncio
    async def test_chat_with_model_override(self, client):
        pid = await _create_provider(client)
        await client.post(f"/admin/llm-providers/{pid}/set-default")

        with patch("app.api.llm_providers.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_llm.chat.return_value = "Sadiq response"
            mock_create.return_value = mock_llm

            resp = await client.post("/admin/llm-providers/chat", json={
                "message": "Explain this code",
                "model": "Fanar-Sadiq",
            })

        assert resp.status_code == 200
        # Verify create was called with the overridden model
        call_args = mock_create.call_args
        config = call_args[0][0]
        assert config.model == "Fanar-Sadiq"

    @pytest.mark.asyncio
    async def test_chat_with_custom_system_prompt(self, client):
        pid = await _create_provider(client)
        await client.post(f"/admin/llm-providers/{pid}/set-default")

        with patch("app.api.llm_providers.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_llm.chat.return_value = "Code review result"
            mock_create.return_value = mock_llm

            resp = await client.post("/admin/llm-providers/chat", json={
                "message": "Review this diff",
                "system_prompt": "You are a code reviewer. Be concise.",
            })

        assert resp.status_code == 200
        # Verify system prompt was passed
        mock_llm.chat.assert_called_once_with(
            "You are a code reviewer. Be concise.",
            "Review this diff",
        )

    @pytest.mark.asyncio
    async def test_chat_no_provider_configured(self, client):
        with patch("app.api.llm_providers.settings") as ms:
            ms.llm_base_url = ""

            resp = await client.post("/admin/llm-providers/chat", json={
                "message": "Hello",
            })

        assert resp.status_code == 400
        assert "No LLM provider configured" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_chat_handles_llm_error(self, client):
        pid = await _create_provider(client)
        await client.post(f"/admin/llm-providers/{pid}/set-default")

        with patch("app.api.llm_providers.create_llm_client") as mock_create:
            mock_llm = AsyncMock()
            mock_llm.chat.side_effect = Exception("LLM timeout")
            mock_create.return_value = mock_llm

            resp = await client.post("/admin/llm-providers/chat", json={
                "message": "Hello",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert "timeout" in data["error"]


# ---------------------------------------------------------------------------
# API Key Auto-Validation on Update (Phase 3)
# ---------------------------------------------------------------------------


class TestAPIKeyAutoValidation:
    @pytest.mark.asyncio
    async def test_update_with_validation_success(self, client):
        pid = await _create_provider(client)

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None

        async def _mock_get(*a, **kw):
            return mock_resp

        with patch("app.api.llm_providers.httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.get = _mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = await client.patch(
                f"/admin/llm-providers/{pid}?validate_key=true",
                json={"api_key": "new-valid-key"},
            )

        assert resp.status_code == 200
        assert resp.json()["has_api_key"] is True

    @pytest.mark.asyncio
    async def test_update_with_validation_failure(self, client):
        pid = await _create_provider(client)

        async def _mock_get(*a, **kw):
            raise Exception("401 Unauthorized")

        with patch("app.api.llm_providers.httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.get = _mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = await client.patch(
                f"/admin/llm-providers/{pid}?validate_key=true",
                json={"api_key": "bad-key"},
            )

        assert resp.status_code == 400
        assert "validation failed" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_without_validation_skips_check(self, client):
        pid = await _create_provider(client)

        # No httpx mock needed â€” validation is skipped
        resp = await client.patch(
            f"/admin/llm-providers/{pid}",
            json={"api_key": "any-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["has_api_key"] is True

    @pytest.mark.asyncio
    async def test_validation_not_triggered_without_key_change(self, client):
        pid = await _create_provider(client)

        # Updating name with validate_key=true should not trigger validation
        resp = await client.patch(
            f"/admin/llm-providers/{pid}?validate_key=true",
            json={"name": "Renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_validation_uses_new_base_url_if_provided(self, client):
        pid = await _create_provider(client)

        called_urls = []

        async def _mock_get(url, **kw):
            called_urls.append(url)
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            return resp

        with patch("app.api.llm_providers.httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.get = _mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            resp = await client.patch(
                f"/admin/llm-providers/{pid}?validate_key=true",
                json={
                    "api_key": "new-key",
                    "base_url": "https://new-provider.com/v1",
                },
            )

        assert resp.status_code == 200
        # Validation should have used the new base URL
        assert any("new-provider" in str(u) for u in called_urls)
