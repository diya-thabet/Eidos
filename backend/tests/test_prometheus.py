"""
Tests for Prometheus metrics endpoint (P3.14).

Covers:
- /metrics endpoint returns Prometheus text format
- MetricsMiddleware records request counts and durations
- Path normalization (IDs collapsed)
- record_ingestion counter
- Metric format validation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.metrics import (
    _normalize_path,
    record_ingestion,
)
from app.main import app
from app.storage.database import get_db
from tests.conftest import create_tables, drop_tables, override_get_db

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


class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200(self, client: AsyncClient):
        resp = await client.get("/metrics")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_text_format(self, client: AsyncClient):
        resp = await client.get("/metrics")
        assert "text/plain" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_contains_help_lines(self, client: AsyncClient):
        resp = await client.get("/metrics")
        body = resp.text
        assert "# HELP eidos_requests_total" in body
        assert "# TYPE eidos_requests_total counter" in body

    @pytest.mark.asyncio
    async def test_contains_request_counter_after_call(self, client: AsyncClient):
        await client.get("/health")
        resp = await client.get("/metrics")
        assert "eidos_requests_total" in resp.text

    @pytest.mark.asyncio
    async def test_contains_duration_metrics(self, client: AsyncClient):
        await client.get("/health")
        resp = await client.get("/metrics")
        assert "eidos_request_duration_seconds" in resp.text

    @pytest.mark.asyncio
    async def test_ingestion_counter_in_output(self, client: AsyncClient):
        record_ingestion("completed")
        record_ingestion("completed")
        record_ingestion("failed")
        resp = await client.get("/metrics")
        body = resp.text
        assert 'eidos_ingestions_total{status="completed"}' in body
        assert 'eidos_ingestions_total{status="failed"}' in body


class TestPathNormalization:
    def test_simple_path_unchanged(self):
        assert _normalize_path("/health") == "/health"

    def test_id_collapsed(self):
        result = _normalize_path("/repos/abc123def456/status")
        assert "{id}" in result

    def test_short_segments_kept(self):
        result = _normalize_path("/repos/abc/status")
        assert "abc" in result

    def test_uuid_collapsed(self):
        result = _normalize_path("/repos/550e8400-e29b-41d4-a716-446655440000/status")
        assert "{id}" in result

    def test_root_path(self):
        assert _normalize_path("/") == "/"

    def test_multiple_ids(self):
        result = _normalize_path("/repos/abcdef123456/snapshots/789012345678")
        assert result.count("{id}") == 2


class TestRecordIngestion:
    def test_increments_counter(self):
        from app.api.metrics import _ingestion_counts
        before = _ingestion_counts.get("test_status", 0)
        record_ingestion("test_status")
        assert _ingestion_counts["test_status"] == before + 1
