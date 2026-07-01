"""
Tests for LLM provider management (Phase 1 of Fanar integration).

Covers: CRUD, set-default, test connectivity, status, config helper.
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


# ---------------------------------------------------------------------------
# Create Provider
# ---------------------------------------------------------------------------


class TestCreateProvider:
    @pytest.mark.asyncio
    async def test_create_provider(self, client):
        resp = await client.post("/admin/llm-providers", json={
            "name": "Fanar",
            "base_url": "https://api.fanar.qa/v1",
            "api_key": "test-key-123",
            "default_model": "Fanar-C-2-27B",
            "rate_limit_rpm": 50,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Fanar"
        assert data["base_url"] == "https://api.fanar.qa/v1"
        assert data["default_model"] == "Fanar-C-2-27B"
        assert data["is_active"] is True
        assert data["is_default"] is False
        assert data["has_api_key"] is True
        assert data["rate_limit_rpm"] == 50
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_provider_minimal(self, client):
        resp = await client.post("/admin/llm-providers", json={
            "name": "Ollama",
            "base_url": "http://localhost:11434/v1",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Ollama"
        assert data["has_api_key"] is False
        assert data["default_model"] == ""

    @pytest.mark.asyncio
    async def test_create_provider_empty_name(self, client):
        resp = await client.post("/admin/llm-providers", json={
            "name": "",
            "base_url": "http://localhost:11434/v1",
        })
        assert resp.status_code == 400
        assert "name" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_provider_empty_url(self, client):
        resp = await client.post("/admin/llm-providers", json={
            "name": "Test",
            "base_url": "",
        })
        assert resp.status_code == 400
        assert "url" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_trims_url(self, client):
        resp = await client.post("/admin/llm-providers", json={
            "name": "Fanar",
            "base_url": "  https://api.fanar.qa/v1/  ",
        })
        assert resp.status_code == 201
        assert resp.json()["base_url"] == "https://api.fanar.qa/v1"


# ---------------------------------------------------------------------------
# List Providers
# ---------------------------------------------------------------------------


class TestListProviders:
    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get("/admin/llm-providers")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_after_create(self, client):
        await client.post("/admin/llm-providers", json={
            "name": "Provider A",
            "base_url": "http://a.com/v1",
        })
        await client.post("/admin/llm-providers", json={
            "name": "Provider B",
            "base_url": "http://b.com/v1",
        })
        resp = await client.get("/admin/llm-providers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = [p["name"] for p in data]
        assert "Provider A" in names
        assert "Provider B" in names


# ---------------------------------------------------------------------------
# Get Provider
# ---------------------------------------------------------------------------


class TestGetProvider:
    @pytest.mark.asyncio
    async def test_get_provider(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Fanar",
            "base_url": "https://api.fanar.qa/v1",
            "default_model": "Fanar-Sadiq",
        })
        pid = create_resp.json()["id"]

        resp = await client.get(f"/admin/llm-providers/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fanar"
        assert resp.json()["default_model"] == "Fanar-Sadiq"

    @pytest.mark.asyncio
    async def test_get_provider_404(self, client):
        resp = await client.get("/admin/llm-providers/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update Provider
# ---------------------------------------------------------------------------


class TestUpdateProvider:
    @pytest.mark.asyncio
    async def test_update_name(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Old Name",
            "base_url": "http://x.com/v1",
        })
        pid = create_resp.json()["id"]

        resp = await client.patch(f"/admin/llm-providers/{pid}", json={
            "name": "New Name",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_update_api_key(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Provider",
            "base_url": "http://x.com/v1",
        })
        pid = create_resp.json()["id"]
        assert create_resp.json()["has_api_key"] is False

        resp = await client.patch(f"/admin/llm-providers/{pid}", json={
            "api_key": "new-secret-key",
        })
        assert resp.status_code == 200
        assert resp.json()["has_api_key"] is True

    @pytest.mark.asyncio
    async def test_update_model(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Fanar",
            "base_url": "https://api.fanar.qa/v1",
            "default_model": "Fanar-C-2-27B",
        })
        pid = create_resp.json()["id"]

        resp = await client.patch(f"/admin/llm-providers/{pid}", json={
            "default_model": "Fanar-Sadiq",
        })
        assert resp.status_code == 200
        assert resp.json()["default_model"] == "Fanar-Sadiq"

    @pytest.mark.asyncio
    async def test_update_404(self, client):
        resp = await client.patch("/admin/llm-providers/nonexistent", json={
            "name": "X",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_deactivate(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Fanar",
            "base_url": "https://api.fanar.qa/v1",
        })
        pid = create_resp.json()["id"]

        resp = await client.patch(f"/admin/llm-providers/{pid}", json={
            "is_active": False,
        })
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False


# ---------------------------------------------------------------------------
# Delete Provider
# ---------------------------------------------------------------------------


class TestDeleteProvider:
    @pytest.mark.asyncio
    async def test_delete_provider(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "ToDelete",
            "base_url": "http://x.com/v1",
        })
        pid = create_resp.json()["id"]

        resp = await client.delete(f"/admin/llm-providers/{pid}")
        assert resp.status_code == 204

        resp = await client.get(f"/admin/llm-providers/{pid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_404(self, client):
        resp = await client.delete("/admin/llm-providers/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Set Default
# ---------------------------------------------------------------------------


class TestSetDefault:
    @pytest.mark.asyncio
    async def test_set_default(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Fanar",
            "base_url": "https://api.fanar.qa/v1",
        })
        pid = create_resp.json()["id"]

        resp = await client.post(f"/admin/llm-providers/{pid}/set-default")
        assert resp.status_code == 200
        assert resp.json()["is_default"] is True

    @pytest.mark.asyncio
    async def test_set_default_replaces_previous(self, client):
        r1 = await client.post("/admin/llm-providers", json={
            "name": "Provider A",
            "base_url": "http://a.com/v1",
        })
        r2 = await client.post("/admin/llm-providers", json={
            "name": "Provider B",
            "base_url": "http://b.com/v1",
        })
        pid_a = r1.json()["id"]
        pid_b = r2.json()["id"]

        await client.post(f"/admin/llm-providers/{pid_a}/set-default")
        await client.post(f"/admin/llm-providers/{pid_b}/set-default")

        resp_a = await client.get(f"/admin/llm-providers/{pid_a}")
        resp_b = await client.get(f"/admin/llm-providers/{pid_b}")
        assert resp_a.json()["is_default"] is False
        assert resp_b.json()["is_default"] is True

    @pytest.mark.asyncio
    async def test_set_default_inactive_rejected(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Inactive",
            "base_url": "http://x.com/v1",
            "is_active": False,
        })
        pid = create_resp.json()["id"]

        resp = await client.post(f"/admin/llm-providers/{pid}/set-default")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_set_default_404(self, client):
        resp = await client.post("/admin/llm-providers/nonexistent/set-default")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test Connectivity
# ---------------------------------------------------------------------------


class TestProviderConnectivity:
    @pytest.mark.asyncio
    async def test_test_provider_success(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Fanar",
            "base_url": "https://api.fanar.qa/v1",
            "api_key": "test-key",
        })
        pid = create_resp.json()["id"]

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {
            "data": [{"id": "Fanar-C-2-27B"}, {"id": "Fanar-Sadiq"}]
        }
        mock_resp.raise_for_status = lambda: None

        async def _mock_get(*args, **kwargs):
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

    @pytest.mark.asyncio
    async def test_test_provider_404(self, client):
        resp = await client.post("/admin/llm-providers/nonexistent/test")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# LLM Status
# ---------------------------------------------------------------------------


class TestLLMStatus:
    @pytest.mark.asyncio
    async def test_status_no_providers(self, client):
        with patch("app.api.llm_providers.settings") as mock_settings:
            mock_settings.llm_base_url = ""
            resp = await client.get("/admin/llm-providers/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["configured"] is False
            assert data["default_provider"] is None

    @pytest.mark.asyncio
    async def test_status_with_default_provider(self, client):
        create_resp = await client.post("/admin/llm-providers", json={
            "name": "Fanar",
            "base_url": "https://api.fanar.qa/v1",
        })
        pid = create_resp.json()["id"]
        await client.post(f"/admin/llm-providers/{pid}/set-default")

        resp = await client.get("/admin/llm-providers/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["default_provider"]["name"] == "Fanar"
        assert data["fallback_to_env"] is False

    @pytest.mark.asyncio
    async def test_status_fallback_to_env(self, client):
        with patch("app.api.llm_providers.settings") as mock_settings:
            mock_settings.llm_base_url = "https://api.openai.com/v1"
            mock_settings.llm_model = "gpt-4o-mini"
            resp = await client.get("/admin/llm-providers/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["configured"] is True
            assert data["fallback_to_env"] is True


# ---------------------------------------------------------------------------
# Config Helper
# ---------------------------------------------------------------------------


class TestGetLLMConfigFromProvider:
    @pytest.mark.asyncio
    async def test_returns_config_from_db_provider(self):
        from app.api.llm_providers import get_llm_config_from_provider

        async with test_sessionmaker() as session:
            from app.auth.crypto import encrypt as enc

            provider = LLMProvider(
                id="test-prov-1",
                name="Fanar",
                base_url="https://api.fanar.qa/v1",
                api_key_enc=enc("secret-key"),
                default_model="Fanar-Sadiq",
                is_active=True,
                is_default=True,
                temperature=0.2,
                max_tokens=4096,
                timeout=30,
            )
            session.add(provider)
            await session.commit()

            config = await get_llm_config_from_provider(session)
            assert config is not None
            assert config.base_url == "https://api.fanar.qa/v1"
            assert config.api_key == "secret-key"
            assert config.model == "Fanar-Sadiq"
            assert config.temperature == 0.2
            assert config.max_tokens == 4096

    @pytest.mark.asyncio
    async def test_model_override(self):
        from app.api.llm_providers import get_llm_config_from_provider

        async with test_sessionmaker() as session:
            from app.auth.crypto import encrypt as enc

            provider = LLMProvider(
                id="test-prov-2",
                name="Fanar",
                base_url="https://api.fanar.qa/v1",
                api_key_enc=enc("key"),
                default_model="Fanar-C-2-27B",
                is_active=True,
                is_default=True,
            )
            session.add(provider)
            await session.commit()

            config = await get_llm_config_from_provider(
                session, model_override="Fanar-Sadiq"
            )
            assert config is not None
            assert config.model == "Fanar-Sadiq"

    @pytest.mark.asyncio
    async def test_specific_provider_id(self):
        from app.api.llm_providers import get_llm_config_from_provider

        async with test_sessionmaker() as session:
            from app.auth.crypto import encrypt as enc

            p1 = LLMProvider(
                id="prov-default",
                name="Default",
                base_url="http://default.com/v1",
                api_key_enc=enc("k1"),
                default_model="model-a",
                is_active=True,
                is_default=True,
            )
            p2 = LLMProvider(
                id="prov-other",
                name="Other",
                base_url="http://other.com/v1",
                api_key_enc=enc("k2"),
                default_model="model-b",
                is_active=True,
                is_default=False,
            )
            session.add_all([p1, p2])
            await session.commit()

            config = await get_llm_config_from_provider(session, provider_id="prov-other")
            assert config is not None
            assert config.base_url == "http://other.com/v1"
            assert config.model == "model-b"

    @pytest.mark.asyncio
    async def test_fallback_to_env(self):
        from app.api.llm_providers import get_llm_config_from_provider

        async with test_sessionmaker() as session:
            with patch("app.api.llm_providers.settings") as mock_settings:
                mock_settings.llm_base_url = "https://api.openai.com/v1"
                mock_settings.llm_api_key = "sk-test"
                mock_settings.llm_model = "gpt-4o-mini"
                mock_settings.llm_temperature = 0.1
                mock_settings.llm_max_tokens = 2048
                mock_settings.llm_timeout = 60

                config = await get_llm_config_from_provider(session)
                assert config is not None
                assert config.base_url == "https://api.openai.com/v1"
                assert config.api_key == "sk-test"

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_configured(self):
        from app.api.llm_providers import get_llm_config_from_provider

        async with test_sessionmaker() as session:
            with patch("app.api.llm_providers.settings") as mock_settings:
                mock_settings.llm_base_url = ""

                config = await get_llm_config_from_provider(session)
                assert config is None


# ---------------------------------------------------------------------------
# API Key Encryption Round-Trip
# ---------------------------------------------------------------------------


class TestAPIKeyEncryption:
    @pytest.mark.asyncio
    async def test_key_is_encrypted_in_db(self, client):
        resp = await client.post("/admin/llm-providers", json={
            "name": "Secret Provider",
            "base_url": "http://x.com/v1",
            "api_key": "my-super-secret-key",
        })
        pid = resp.json()["id"]

        # Read directly from DB
        async with test_sessionmaker() as session:
            provider = await session.get(LLMProvider, pid)
            assert provider is not None
            assert provider.api_key_enc != ""
            assert provider.api_key_enc != "my-super-secret-key"

            # Decrypt should give original
            from app.auth.crypto import decrypt

            assert decrypt(provider.api_key_enc) == "my-super-secret-key"
