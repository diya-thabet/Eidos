"""
Tests for local authentication (signup + login).

Uses the shared conftest in-memory SQLite engine -- no PostgreSQL needed.
Run with: pytest backend/tests/test_local_auth.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.storage.database import get_db
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and drop after."""
    await drop_tables()
    await create_tables()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client with auth enabled for local auth tests."""
    with (
        patch("app.auth.dependencies.settings") as dep_settings,
        patch("app.api.auth.settings") as api_settings,
        patch("app.api.repos.run_ingestion", new_callable=AsyncMock),
    ):
        # Enable auth in the dependencies used by the endpoints under test
        dep_settings.auth_enabled = True
        dep_settings.edition = settings.edition
        dep_settings.secret_key = settings.secret_key
        dep_settings.superadmin_email = ""
        dep_settings.github_client_id = ""
        dep_settings.google_client_id = ""

        api_settings.auth_enabled = True
        api_settings.github_client_id = ""
        api_settings.google_client_id = ""
        api_settings.superadmin_email = ""

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# Signup Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_success(client):
    """Test successful user registration."""
    resp = await client.post("/auth/signup", json={
        "email": "alice@example.com",
        "password": "secret123",
        "name": "Alice"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["name"] == "Alice"
    assert data["user"]["role"] == "user"


@pytest.mark.asyncio
async def test_signup_duplicate_email(client):
    """Test that duplicate emails are rejected."""
    payload = {"email": "bob@example.com", "password": "pass1234", "name": "Bob"}
    resp1 = await client.post("/auth/signup", json=payload)
    assert resp1.status_code == 200

    resp2 = await client.post("/auth/signup", json=payload)
    assert resp2.status_code == 409
    assert "already registered" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_signup_short_password(client):
    """Test that short passwords are rejected."""
    resp = await client.post("/auth/signup", json={
        "email": "short@example.com",
        "password": "12345"
    })
    assert resp.status_code == 422
    assert "at least 6" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_signup_missing_fields(client):
    """Test that missing fields are rejected."""
    resp = await client.post("/auth/signup", json={"email": "", "password": ""})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success(client):
    """Test successful login after signup."""
    # First signup
    await client.post("/auth/signup", json={
        "email": "carol@example.com",
        "password": "mypass99",
        "name": "Carol"
    })

    # Then login
    resp = await client.post("/auth/login", json={
        "email": "carol@example.com",
        "password": "mypass99"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "carol@example.com"
    assert data["user"]["name"] == "Carol"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    """Test login with wrong password."""
    await client.post("/auth/signup", json={
        "email": "dave@example.com",
        "password": "correct123"
    })

    resp = await client.post("/auth/login", json={
        "email": "dave@example.com",
        "password": "wrong999"
    })
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    """Test login with non-existent email."""
    resp = await client.post("/auth/login", json={
        "email": "nobody@example.com",
        "password": "anything"
    })
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Token / Me Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_with_token(client):
    """Test /auth/me returns user info when authenticated."""
    # Signup
    resp = await client.post("/auth/signup", json={
        "email": "eve@example.com",
        "password": "secure456",
        "name": "Eve"
    })
    token = resp.json()["access_token"]

    # Get /me
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "eve@example.com"
    assert data["name"] == "Eve"
    assert data["role"] == "user"
    assert data["auth_provider"] == "local"


@pytest.mark.asyncio
async def test_me_without_token(client):
    """Test /auth/me returns 401 without token."""
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_case_insensitive_email(client):
    """Test that email matching is case-insensitive."""
    await client.post("/auth/signup", json={
        "email": "Frank@Example.COM",
        "password": "pass1234"
    })

    resp = await client.post("/auth/login", json={
        "email": "frank@example.com",
        "password": "pass1234"
    })
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Password Module Unit Tests
# ---------------------------------------------------------------------------


def test_password_hash_and_verify():
    """Test password hashing and verification directly."""
    from app.auth.password import hash_password, verify_password

    pw = "mySecret!123"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("wrongPassword", hashed) is False


def test_empty_hash():
    """Test that empty hash returns False."""
    from app.auth.password import verify_password

    assert verify_password("anything", "") is False
    assert verify_password("anything", None) is False
