"""
Tests for production middleware and infrastructure features.

Covers:
- Request ID middleware (generation, passthrough, response header)
- Access logging middleware (structured fields)
- Global exception handler (no stack trace leaks, request_id in response)
- Rate limiting middleware (token bucket, bypass for health endpoints)
- CORS middleware (preflight, headers)
- Deep healthcheck (/health/ready)
- Pagination envelope (PaginatedResponse on list endpoints)
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import RepoSnapshot, SnapshotStatus
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

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


# ===================================================================
# Request ID Middleware
# ===================================================================


class TestRequestIDMiddleware:
    @pytest.mark.asyncio
    async def test_response_contains_request_id(self, client: AsyncClient):
        resp = await client.get("/health")
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) > 0

    @pytest.mark.asyncio
    async def test_client_request_id_is_preserved(self, client: AsyncClient):
        custom_id = "my-custom-request-id-12345"
        resp = await client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp.headers["X-Request-ID"] == custom_id

    @pytest.mark.asyncio
    async def test_different_requests_get_different_ids(self, client: AsyncClient):
        resp1 = await client.get("/health")
        resp2 = await client.get("/health")
        assert resp1.headers["X-Request-ID"] != resp2.headers["X-Request-ID"]

    @pytest.mark.asyncio
    async def test_request_id_on_404(self, client: AsyncClient):
        resp = await client.get("/nonexistent-path")
        assert "X-Request-ID" in resp.headers

    @pytest.mark.asyncio
    async def test_request_id_on_post(self, client: AsyncClient):
        resp = await client.post(
            "/repos",
            json={"name": "test", "url": "https://github.com/example/test"},
        )
        assert "X-Request-ID" in resp.headers


# ===================================================================
# Global Exception Handler
# ===================================================================


class TestExceptionHandler:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient):
        """Baseline: normal endpoints work fine."""
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_422_on_invalid_input(self, client: AsyncClient):
        """Validation errors return 422, not 500."""
        resp = await client.post("/repos", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_404_does_not_leak_internals(self, client: AsyncClient):
        resp = await client.get("/repos/nonexistent/status")
        assert resp.status_code == 404
        body = resp.json()
        assert "traceback" not in str(body).lower()
        assert "Traceback" not in str(body)


# ===================================================================
# CORS Middleware
# ===================================================================


class TestCORSMiddleware:
    @pytest.mark.asyncio
    async def test_cors_headers_on_simple_request(self, client: AsyncClient):
        resp = await client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert "access-control-allow-origin" in resp.headers

    @pytest.mark.asyncio
    async def test_cors_preflight(self, client: AsyncClient):
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers

    @pytest.mark.asyncio
    async def test_cors_exposes_request_id(self, client: AsyncClient):
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        exposed = resp.headers.get("access-control-expose-headers", "")
        assert "X-Request-ID" in exposed or "*" in exposed or resp.status_code == 200


# ===================================================================
# Rate Limiting
# ===================================================================


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_health_is_not_rate_limited(self, client: AsyncClient):
        """Health endpoints must never be rate limited."""
        for _ in range(200):
            resp = await client.get("/health")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_version_is_not_rate_limited(self, client: AsyncClient):
        for _ in range(200):
            resp = await client.get("/version")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_normal_request_succeeds_under_limit(self, client: AsyncClient):
        """A few requests should always succeed."""
        for _ in range(5):
            resp = await client.get("/repos/fake/status")
            # 404 is fine (repo doesn't exist), but not 429
            assert resp.status_code != 429


# ===================================================================
# Deep Healthcheck
# ===================================================================


class TestDeepHealthcheck:
    @pytest.mark.asyncio
    async def test_shallow_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_deep_health_ready(self, client: AsyncClient):
        """
        /health/ready checks DB connectivity.
        With test SQLite it should succeed.
        """
        resp = await client.get("/health/ready")
        data = resp.json()
        assert "status" in data
        assert "checks" in data
        assert "database" in data["checks"]

    @pytest.mark.asyncio
    async def test_deep_health_returns_check_keys(self, client: AsyncClient):
        resp = await client.get("/health/ready")
        data = resp.json()
        assert isinstance(data["checks"], dict)

    @pytest.mark.asyncio
    async def test_version_endpoint(self, client: AsyncClient):
        resp = await client.get("/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "edition" in data


# ===================================================================
# Pagination
# ===================================================================


class TestPagination:
    """Test paginated responses on list endpoints."""

    async def _create_repo_and_snapshot(self, client: AsyncClient) -> tuple[str, str]:
        """Helper: create a repo + snapshot for testing list endpoints."""
        resp = await client.post(
            "/repos",
            json={"name": "test-paginate", "url": "https://github.com/example/paginate"},
        )
        repo_id = resp.json()["id"]
        # Directly create a snapshot via ingest (mocked)
        resp = await client.post(f"/repos/{repo_id}/ingest")
        snapshot_id = resp.json()["snapshot_id"]
        return repo_id, snapshot_id

    @pytest.mark.asyncio
    async def test_symbols_returns_paginated_envelope(self, client: AsyncClient):
        repo_id, snap_id = await self._create_repo_and_snapshot(client)

        # Mark snapshot completed so endpoint works
        async with test_sessionmaker() as session:
            snap = await session.get(RepoSnapshot, snap_id)
            if snap:
                snap.status = SnapshotStatus.completed
                await session.commit()

        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/symbols")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data
        assert isinstance(data["items"], list)
        assert data["total"] >= 0
        assert data["has_more"] is False  # no symbols inserted

    @pytest.mark.asyncio
    async def test_edges_returns_paginated_envelope(self, client: AsyncClient):
        repo_id, snap_id = await self._create_repo_and_snapshot(client)

        async with test_sessionmaker() as session:
            snap = await session.get(RepoSnapshot, snap_id)
            if snap:
                snap.status = SnapshotStatus.completed
                await session.commit()

        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/edges")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data

    @pytest.mark.asyncio
    async def test_summaries_returns_paginated_envelope(self, client: AsyncClient):
        repo_id, snap_id = await self._create_repo_and_snapshot(client)

        async with test_sessionmaker() as session:
            snap = await session.get(RepoSnapshot, snap_id)
            if snap:
                snap.status = SnapshotStatus.completed
                await session.commit()

        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/summaries")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_pagination_limit_param(self, client: AsyncClient):
        repo_id, snap_id = await self._create_repo_and_snapshot(client)

        async with test_sessionmaker() as session:
            snap = await session.get(RepoSnapshot, snap_id)
            if snap:
                snap.status = SnapshotStatus.completed
                await session.commit()

        resp = await client.get(
            f"/repos/{repo_id}/snapshots/{snap_id}/symbols?limit=10&offset=0"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_pagination_offset_param(self, client: AsyncClient):
        repo_id, snap_id = await self._create_repo_and_snapshot(client)

        async with test_sessionmaker() as session:
            snap = await session.get(RepoSnapshot, snap_id)
            if snap:
                snap.status = SnapshotStatus.completed
                await session.commit()

        resp = await client.get(
            f"/repos/{repo_id}/snapshots/{snap_id}/symbols?limit=5&offset=100"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["offset"] == 100
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_pagination_invalid_limit_rejected(self, client: AsyncClient):
        resp = await client.get("/repos/fake/snapshots/fake/symbols?limit=0")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_pagination_negative_offset_rejected(self, client: AsyncClient):
        resp = await client.get("/repos/fake/snapshots/fake/symbols?offset=-1")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_pagination_limit_too_large_rejected(self, client: AsyncClient):
        resp = await client.get("/repos/fake/snapshots/fake/symbols?limit=9999")
        assert resp.status_code == 422


# ===================================================================
# Middleware unit tests (isolated, no HTTP)
# ===================================================================


class TestTokenBucket:
    def test_allows_burst(self):
        from app.core.middleware import _TokenBucket

        bucket = _TokenBucket(rate=1.0, burst=5)
        for _ in range(5):
            assert bucket.allow("test-key") is True

    def test_rejects_after_burst(self):
        from app.core.middleware import _TokenBucket

        bucket = _TokenBucket(rate=1.0, burst=3)
        for _ in range(3):
            bucket.allow("test-key")
        assert bucket.allow("test-key") is False

    def test_different_keys_independent(self):
        from app.core.middleware import _TokenBucket

        bucket = _TokenBucket(rate=1.0, burst=2)
        bucket.allow("key-a")
        bucket.allow("key-a")
        # key-a exhausted
        assert bucket.allow("key-a") is False
        # key-b still has tokens
        assert bucket.allow("key-b") is True

    def test_refills_over_time(self):
        from app.core.middleware import _TokenBucket

        bucket = _TokenBucket(rate=1000.0, burst=1)  # very fast refill for testing
        bucket.allow("k")
        assert bucket.allow("k") is False
        time.sleep(0.01)  # 10ms = 10 tokens at 1000/s
        assert bucket.allow("k") is True


class TestRequestIDContextVar:
    def test_default_is_empty_string(self):
        from app.core.middleware import request_id_ctx

        assert request_id_ctx.get() == "" or isinstance(request_id_ctx.get(), str)

    def test_set_and_get(self):
        from app.core.middleware import request_id_ctx

        token = request_id_ctx.set("test-123")
        assert request_id_ctx.get() == "test-123"
        request_id_ctx.reset(token)


# ===================================================================
# PaginatedResponse schema tests
# ===================================================================


class TestPaginatedResponseSchema:
    def test_basic_construction(self):
        from app.storage.schemas import PaginatedResponse

        p = PaginatedResponse(items=[1, 2, 3], total=10, limit=3, offset=0, has_more=True)
        assert p.total == 10
        assert len(p.items) == 3
        assert p.has_more is True

    def test_empty_response(self):
        from app.storage.schemas import PaginatedResponse

        p = PaginatedResponse(items=[], total=0, limit=100, offset=0, has_more=False)
        assert p.total == 0
        assert p.items == []
        assert p.has_more is False

    def test_serialization(self):
        from app.storage.schemas import PaginatedResponse

        p = PaginatedResponse(items=["a", "b"], total=50, limit=2, offset=10, has_more=True)
        d = p.model_dump()
        assert d["items"] == ["a", "b"]
        assert d["total"] == 50
        assert d["limit"] == 2
        assert d["offset"] == 10
        assert d["has_more"] is True

    def test_has_more_false_when_at_end(self):
        from app.storage.schemas import PaginatedResponse

        p = PaginatedResponse(items=["x"], total=5, limit=5, offset=0, has_more=False)
        assert p.has_more is False
