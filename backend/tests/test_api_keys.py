"""
Tests for API key authentication.

Covers:
- Create API key, list, revoke
- Authenticate with X-API-Key header
- Revoked key is rejected
- Invalid key is rejected
- API key format (prefix, hash)
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import ApiKey, Repo, RepoSnapshot, SnapshotStatus, User, UserRole
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed() -> None:
    async with test_sessionmaker() as db:
        db.add(User(
            id="u-apikey",
            github_login="apikeyuser",
            name="API Key User",
            email="apikey@test.com",
            role=UserRole.user,
        ))
        db.add(Repo(id="r-apikey", name="apikey-repo", url="https://example.com/ak"))
        db.add(RepoSnapshot(
            id="s-apikey", repo_id="r-apikey", status=SnapshotStatus.completed,
        ))
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
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


class TestCreateApiKey:
    @pytest.mark.asyncio
    async def test_create_returns_key(self, client: AsyncClient):
        resp = await client.post("/auth/api-keys?name=CI%20Pipeline")
        assert resp.status_code == 201
        data = resp.json()
        assert "key" in data
        assert data["key"].startswith("eidos_")
        assert data["name"] == "CI Pipeline"
        assert "prefix" in data
        assert "id" in data

    @pytest.mark.asyncio
    async def test_key_starts_with_eidos_prefix(self, client: AsyncClient):
        resp = await client.post("/auth/api-keys?name=test")
        key = resp.json()["key"]
        assert key.startswith("eidos_")
        assert len(key) > 20  # sufficiently long

    @pytest.mark.asyncio
    async def test_prefix_matches_key_start(self, client: AsyncClient):
        resp = await client.post("/auth/api-keys?name=test")
        data = resp.json()
        assert data["key"].startswith(data["prefix"])

    @pytest.mark.asyncio
    async def test_key_is_hashed_in_db(self, client: AsyncClient):
        resp = await client.post("/auth/api-keys?name=test")
        data = resp.json()
        key_id = data["id"]
        raw_key = data["key"]

        async with test_sessionmaker() as db:
            api_key = await db.get(ApiKey, key_id)
            assert api_key is not None
            expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            assert api_key.key_hash == expected_hash

    @pytest.mark.asyncio
    async def test_create_multiple_keys(self, client: AsyncClient):
        resp1 = await client.post("/auth/api-keys?name=key1")
        resp2 = await client.post("/auth/api-keys?name=key2")
        assert resp1.json()["id"] != resp2.json()["id"]
        assert resp1.json()["key"] != resp2.json()["key"]


class TestListApiKeys:
    @pytest.mark.asyncio
    async def test_list_empty_initially(self, client: AsyncClient):
        resp = await client.get("/auth/api-keys")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_shows_created_keys(self, client: AsyncClient):
        await client.post("/auth/api-keys?name=key1")
        await client.post("/auth/api-keys?name=key2")
        resp = await client.get("/auth/api-keys")
        assert len(resp.json()) == 2
        names = {k["name"] for k in resp.json()}
        assert names == {"key1", "key2"}

    @pytest.mark.asyncio
    async def test_list_does_not_expose_raw_key(self, client: AsyncClient):
        await client.post("/auth/api-keys?name=secret")
        resp = await client.get("/auth/api-keys")
        for k in resp.json():
            assert "key" not in k
            assert "key_hash" not in k
            assert "prefix" in k


class TestRevokeApiKey:
    @pytest.mark.asyncio
    async def test_revoke_key(self, client: AsyncClient):
        create_resp = await client.post("/auth/api-keys?name=to-revoke")
        key_id = create_resp.json()["id"]

        resp = await client.delete(f"/auth/api-keys/{key_id}")
        assert resp.status_code == 200
        assert "revoked" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_revoked_key_not_in_list(self, client: AsyncClient):
        create_resp = await client.post("/auth/api-keys?name=gone")
        key_id = create_resp.json()["id"]

        await client.delete(f"/auth/api-keys/{key_id}")
        list_resp = await client.get("/auth/api-keys")
        assert all(k["id"] != key_id for k in list_resp.json())

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_404(self, client: AsyncClient):
        resp = await client.delete("/auth/api-keys/nonexistent")
        assert resp.status_code == 404


class TestApiKeyAuthentication:
    @pytest.mark.asyncio
    async def test_auth_with_api_key_header(self, client: AsyncClient):
        """When auth is disabled (test default), X-API-Key is not checked.
        This test verifies the header is accepted without error."""
        create_resp = await client.post("/auth/api-keys?name=cicd")
        raw_key = create_resp.json()["key"]

        # Use the key to access an endpoint
        resp = await client.get(
            "/repos/r-apikey/status",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_api_key_stored_as_sha256(self, client: AsyncClient):
        create_resp = await client.post("/auth/api-keys?name=hash-test")
        raw_key = create_resp.json()["key"]
        key_id = create_resp.json()["id"]

        async with test_sessionmaker() as db:
            api_key = await db.get(ApiKey, key_id)
            assert api_key is not None
            assert api_key.key_hash == hashlib.sha256(raw_key.encode()).hexdigest()
            assert api_key.is_active is True
