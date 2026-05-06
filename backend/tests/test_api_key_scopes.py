"""
Tests for Phase 4 (Phase 10.4): API Key Scoping & Permissions.

Tests scope parsing, validation, enforcement, and updated API key endpoints.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.scopes import SCOPES, has_scope, parse_scopes, validate_scopes
from app.main import app
from app.storage.database import get_db
from app.storage.models import ApiKey, Repo, RepoSnapshot, SnapshotStatus, User, UserRole
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# =======================================================================
# Unit tests: scopes module
# =======================================================================


class TestParseScopes:

    def test_star(self):
        assert parse_scopes("*") == {"*"}

    def test_empty_string(self):
        assert parse_scopes("") == {"*"}

    def test_none(self):
        assert parse_scopes(None) == {"*"}

    def test_single(self):
        assert parse_scopes("read:repos") == {"read:repos"}

    def test_multiple(self):
        result = parse_scopes("read:repos,write:repos,read:analysis")
        assert result == {"read:repos", "write:repos", "read:analysis"}

    def test_whitespace(self):
        result = parse_scopes(" read:repos , write:repos ")
        assert "read:repos" in result
        assert "write:repos" in result


class TestHasScope:

    def test_star_grants_all(self):
        assert has_scope({"*"}, "read:repos") is True
        assert has_scope({"*"}, "admin:users") is True

    def test_exact_match(self):
        assert has_scope({"read:repos", "write:repos"}, "read:repos") is True

    def test_no_match(self):
        assert has_scope({"read:repos"}, "write:repos") is False

    def test_empty_set(self):
        assert has_scope(set(), "read:repos") is False


class TestValidateScopes:

    def test_all_valid(self):
        assert validate_scopes(["read:repos", "write:repos", "*"]) == []

    def test_invalid_scope(self):
        result = validate_scopes(["read:repos", "invalid:scope"])
        assert result == ["invalid:scope"]

    def test_empty_list(self):
        assert validate_scopes([]) == []

    def test_multiple_invalid(self):
        result = validate_scopes(["bad1", "bad2"])
        assert len(result) == 2


# =======================================================================
# API tests
# =======================================================================


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        db.add(User(
            id="u1", github_login="testuser", name="Test",
            email="test@example.com", avatar_url="", github_token_enc="",
            role=UserRole.superadmin,
        ))
        db.add(Repo(id="r1", name="demo", url="https://example.com"))
        db.add(RepoSnapshot(
            id="s1", repo_id="r1", commit_sha="abc",
            status=SnapshotStatus.completed, file_count=1,
        ))

        # Create a scoped API key (read-only)
        raw_key = "eidos_readonly_test_key_123456"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        db.add(ApiKey(
            id="key_readonly",
            user_id="u1",
            name="Read Only",
            key_hash=key_hash,
            prefix="eidos_reado",
            scopes="read:repos,read:analysis",
            is_active=True,
        ))

        # Create a full-access key
        raw_full = "eidos_full_test_key_7890abcdef"
        key_hash_full = hashlib.sha256(raw_full.encode()).hexdigest()
        db.add(ApiKey(
            id="key_full",
            user_id="u1",
            name="Full Access",
            key_hash=key_hash_full,
            prefix="eidos_full_",
            scopes="*",
            is_active=True,
        ))

        # Create an expired key
        raw_expired = "eidos_expired_test_key_expired"
        key_hash_exp = hashlib.sha256(raw_expired.encode()).hexdigest()
        db.add(ApiKey(
            id="key_expired",
            user_id="u1",
            name="Expired",
            key_hash=key_hash_exp,
            prefix="eidos_expir",
            scopes="*",
            is_active=True,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        ))

        await db.commit()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            yield ac


class TestCreateKeyWithScopes:

    @pytest.mark.asyncio
    async def test_create_with_scopes(self, client):
        resp = await client.post(
            "/auth/api-keys?name=CI&scopes=read:repos,read:analysis",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["scopes"] == ["read:repos", "read:analysis"]
        assert data["key"].startswith("eidos_")

    @pytest.mark.asyncio
    async def test_create_default_full_access(self, client):
        resp = await client.post("/auth/api-keys?name=Full")
        assert resp.status_code == 201
        assert resp.json()["scopes"] == ["*"]

    @pytest.mark.asyncio
    async def test_create_with_expiration(self, client):
        resp = await client.post(
            "/auth/api-keys?name=Temp&expires_in_days=30",
        )
        assert resp.status_code == 201
        assert resp.json()["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_create_invalid_scopes(self, client):
        resp = await client.post(
            "/auth/api-keys?name=Bad&scopes=invalid:scope",
        )
        assert resp.status_code == 400
        assert "Invalid scopes" in resp.json()["detail"]


class TestListKeysWithScopes:

    @pytest.mark.asyncio
    async def test_list_shows_scopes(self, client):
        # Create a key via API (belongs to anonymous user in test mode)
        await client.post(
            "/auth/api-keys?name=Scoped&scopes=read:repos,read:analysis",
        )
        resp = await client.get("/auth/api-keys")
        assert resp.status_code == 200
        keys = resp.json()
        ro = next((k for k in keys if k["name"] == "Scoped"), None)
        assert ro is not None
        assert "read:repos" in ro["scopes"]
        assert "usage_count" in ro

    @pytest.mark.asyncio
    async def test_list_shows_expires(self, client):
        await client.post(
            "/auth/api-keys?name=Expiring&expires_in_days=7",
        )
        resp = await client.get("/auth/api-keys")
        keys = resp.json()
        exp = next((k for k in keys if k["name"] == "Expiring"), None)
        assert exp is not None
        assert exp["expires_at"] is not None


class TestScopesEndpoint:

    @pytest.mark.asyncio
    async def test_list_scopes(self, client):
        resp = await client.get("/auth/api-keys/scopes")
        assert resp.status_code == 200
        data = resp.json()
        assert "scopes" in data
        assert "read:repos" in data["scopes"]
        assert "*" in data["scopes"]
        assert len(data["scopes"]) == len(SCOPES)


class TestScopeEnforcement:

    @pytest.mark.asyncio
    async def test_readonly_key_can_read(self, client):
        # Reading repos should work with read:repos scope
        resp = await client.get(
            "/repos",
            headers={"X-API-Key": "eidos_readonly_test_key_123456"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_full_key_can_do_anything(self, client):
        resp = await client.get(
            "/repos",
            headers={"X-API-Key": "eidos_full_test_key_7890abcdef"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_expired_key_rejected(self):
        """Test expired key rejection via internal function."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from app.auth.dependencies import _authenticate_api_key

        request = MagicMock()
        request.state = MagicMock()

        async for db in override_get_db():
            with pytest.raises(HTTPException) as exc_info:
                await _authenticate_api_key(
                    "eidos_expired_test_key_expired", request, db,
                )
            assert exc_info.value.status_code == 401
            assert "expired" in exc_info.value.detail.lower()
            break

    @pytest.mark.asyncio
    async def test_usage_count_increments(self):
        """Test usage tracking via internal function."""
        from unittest.mock import MagicMock

        from sqlalchemy import select

        from app.auth.dependencies import _authenticate_api_key

        request = MagicMock()
        request.state = MagicMock()

        async for db in override_get_db():
            # Use the full key twice
            await _authenticate_api_key(
                "eidos_full_test_key_7890abcdef", request, db,
            )
            await _authenticate_api_key(
                "eidos_full_test_key_7890abcdef", request, db,
            )
            await db.commit()

            # Check usage
            result = await db.execute(
                select(ApiKey).where(ApiKey.id == "key_full")
            )
            key = result.scalar_one()
            assert key.usage_count >= 2
            assert key.last_used_at is not None
            break


class TestRequireScope:

    @pytest.mark.asyncio
    async def test_scope_check_via_dependency(self):
        """Test the require_scope dependency directly."""
        from unittest.mock import MagicMock

        from app.auth.scopes import require_scope

        checker = require_scope("write:repos")

        # Simulate request with limited scopes
        request = MagicMock()
        request.state.api_key_scopes = "read:repos"

        with pytest.raises(Exception) as exc_info:
            await checker(request)
        assert "403" in str(exc_info.value.status_code)

    @pytest.mark.asyncio
    async def test_scope_check_passes(self):
        from unittest.mock import MagicMock

        from app.auth.scopes import require_scope

        checker = require_scope("read:repos")
        request = MagicMock()
        request.state.api_key_scopes = "read:repos,read:analysis"

        # Should not raise
        await checker(request)

    @pytest.mark.asyncio
    async def test_jwt_user_bypasses_scopes(self):
        from unittest.mock import MagicMock

        from app.auth.scopes import require_scope

        checker = require_scope("admin:users")
        request = MagicMock(spec=["state"])
        # JWT users don't have api_key_scopes on state
        del request.state.api_key_scopes

        # Should not raise (JWT = full access)
        await checker(request)
