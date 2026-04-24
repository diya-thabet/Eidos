"""
Tests for webhook receiver endpoints.

Covers:
- GitHub push webhook (signature verification, event filtering, ingestion trigger)
- GitLab push webhook (token verification, event filtering)
- Generic push webhook (repo matching, branch matching)
- Edge cases: missing fields, unknown repos, non-push events
- HMAC signature verification
"""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed_webhook_data() -> None:
    async with test_sessionmaker() as db:
        db.add(
            Repo(
                id="r-wh",
                name="webhook-test",
                url="https://github.com/example/webhook-test",
                default_branch="main",
                git_provider="github",
            )
        )
        db.add(
            Repo(
                id="r-gl",
                name="gitlab-test",
                url="https://gitlab.com/example/gitlab-test",
                default_branch="main",
                git_provider="gitlab",
            )
        )
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    await _seed_webhook_data()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        mock_trigger = AsyncMock(return_value="mock-snap-id")
        with patch("app.api.webhooks._trigger_ingestion", mock_trigger):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac


# ===================================================================
# GitHub Webhook
# ===================================================================


class TestGitHubWebhook:
    @pytest.mark.asyncio
    async def test_push_event_triggers_ingestion(self, client: AsyncClient):
        payload = {
            "ref": "refs/heads/main",
            "after": "abc123def",
            "repository": {
                "clone_url": "https://github.com/example/webhook-test.git",
                "html_url": "https://github.com/example/webhook-test",
            },
        }
        resp = await client.post(
            "/webhooks/github",
            json=payload,
            headers={"X-GitHub-Event": "push"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert data["snapshot_id"] is not None
        assert "webhook-test" in data["message"]

    @pytest.mark.asyncio
    async def test_non_push_event_ignored(self, client: AsyncClient):
        resp = await client.post(
            "/webhooks/github",
            json={"action": "opened"},
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is False
        assert "Ignored" in data["message"]

    @pytest.mark.asyncio
    async def test_unknown_repo_not_accepted(self, client: AsyncClient):
        payload = {
            "ref": "refs/heads/main",
            "after": "abc123",
            "repository": {
                "clone_url": "https://github.com/unknown/repo.git",
            },
        }
        resp = await client.post(
            "/webhooks/github",
            json=payload,
            headers={"X-GitHub-Event": "push"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is False

    @pytest.mark.asyncio
    async def test_wrong_branch_not_accepted(self, client: AsyncClient):
        payload = {
            "ref": "refs/heads/develop",
            "after": "abc123",
            "repository": {
                "clone_url": "https://github.com/example/webhook-test.git",
            },
        }
        resp = await client.post(
            "/webhooks/github",
            json=payload,
            headers={"X-GitHub-Event": "push"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is False

    @pytest.mark.asyncio
    async def test_no_event_header_treated_as_non_push(self, client: AsyncClient):
        resp = await client.post(
            "/webhooks/github",
            json={"ref": "refs/heads/main"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is False

    @pytest.mark.asyncio
    async def test_html_url_matching(self, client: AsyncClient):
        """Match works via html_url (without .git suffix)."""
        payload = {
            "ref": "refs/heads/main",
            "after": "fff999",
            "repository": {
                "html_url": "https://github.com/example/webhook-test",
            },
        }
        resp = await client.post(
            "/webhooks/github",
            json=payload,
            headers={"X-GitHub-Event": "push"},
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True


# ===================================================================
# GitLab Webhook
# ===================================================================


class TestGitLabWebhook:
    @pytest.mark.asyncio
    async def test_push_hook_triggers_ingestion(self, client: AsyncClient):
        payload = {
            "ref": "refs/heads/main",
            "after": "abc123",
            "project": {
                "http_url": "https://gitlab.com/example/gitlab-test.git",
            },
        }
        resp = await client.post(
            "/webhooks/gitlab",
            json=payload,
            headers={"X-Gitlab-Event": "Push Hook"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert data["snapshot_id"] is not None

    @pytest.mark.asyncio
    async def test_non_push_hook_ignored(self, client: AsyncClient):
        resp = await client.post(
            "/webhooks/gitlab",
            json={},
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] is False

    @pytest.mark.asyncio
    async def test_gitlab_unknown_repo(self, client: AsyncClient):
        payload = {
            "ref": "refs/heads/main",
            "after": "abc",
            "project": {"http_url": "https://gitlab.com/unknown/repo.git"},
        }
        resp = await client.post(
            "/webhooks/gitlab",
            json=payload,
            headers={"X-Gitlab-Event": "Push Hook"},
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] is False


# ===================================================================
# Generic Webhook
# ===================================================================


class TestGenericWebhook:
    @pytest.mark.asyncio
    async def test_generic_push(self, client: AsyncClient):
        resp = await client.post(
            "/webhooks/push",
            json={
                "repo_url": "https://github.com/example/webhook-test",
                "branch": "main",
                "commit_sha": "aaa111",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert data["snapshot_id"] is not None

    @pytest.mark.asyncio
    async def test_generic_missing_repo_url(self, client: AsyncClient):
        resp = await client.post(
            "/webhooks/push",
            json={"branch": "main"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_missing_branch(self, client: AsyncClient):
        resp = await client.post(
            "/webhooks/push",
            json={"repo_url": "https://github.com/example/webhook-test"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_no_matching_repo(self, client: AsyncClient):
        resp = await client.post(
            "/webhooks/push",
            json={
                "repo_url": "https://github.com/unknown/repo",
                "branch": "main",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] is False

    @pytest.mark.asyncio
    async def test_generic_wrong_branch(self, client: AsyncClient):
        resp = await client.post(
            "/webhooks/push",
            json={
                "repo_url": "https://github.com/example/webhook-test",
                "branch": "develop",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] is False


# ===================================================================
# Signature Verification (unit)
# ===================================================================


class TestSignatureVerification:
    def test_valid_github_signature(self):
        from app.api.webhooks import _verify_github_signature

        body = b'{"test": true}'
        secret = "my-secret"
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_github_signature(body, secret, sig) is True

    def test_invalid_github_signature(self):
        from app.api.webhooks import _verify_github_signature

        body = b'{"test": true}'
        assert _verify_github_signature(body, "correct-secret", "sha256=wrong") is False

    def test_tampered_body(self):
        from app.api.webhooks import _verify_github_signature

        secret = "my-secret"
        body = b'{"test": true}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        # Tampered body
        assert _verify_github_signature(b'{"test": false}', secret, sig) is False


# ===================================================================
# Webhook creates snapshot in DB
# ===================================================================


class TestWebhookCreatesSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_created_in_db(self, client: AsyncClient):
        """Webhook with mocked trigger returns snapshot_id."""
        payload = {
            "ref": "refs/heads/main",
            "after": "snap-commit-sha",
            "repository": {
                "html_url": "https://github.com/example/webhook-test",
            },
        }
        resp = await client.post(
            "/webhooks/github",
            json=payload,
            headers={"X-GitHub-Event": "push"},
        )
        data = resp.json()
        assert data["accepted"] is True
        assert data["snapshot_id"] == "mock-snap-id"
