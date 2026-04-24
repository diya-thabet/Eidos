"""
Webhook receiver for Git provider events.

Supports:
- GitHub push events (auto-trigger ingestion on push to default branch)
- GitLab push events
- Generic push payload

Webhook secret verification via HMAC-SHA256 for GitHub.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class WebhookResponse(BaseModel):
    accepted: bool
    message: str
    snapshot_id: str | None = None


# ---------------------------------------------------------------------------
# GitHub webhook
# ---------------------------------------------------------------------------


@router.post(
    "/webhooks/github",
    response_model=WebhookResponse,
    summary="Receive GitHub push events",
)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Receive a GitHub webhook push event and auto-trigger ingestion.

    Verifies HMAC-SHA256 signature if ``EIDOS_WEBHOOK_SECRET`` is set.
    Only processes ``push`` events to the repo's default branch.
    """
    body = await request.body()

    # Verify signature if webhook secret is configured
    webhook_secret = getattr(settings, "webhook_secret", "")
    if webhook_secret:
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing signature header")
        if not _verify_github_signature(body, webhook_secret, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Only process push events
    if x_github_event != "push":
        return WebhookResponse(accepted=False, message=f"Ignored event: {x_github_event}")

    payload = await request.json()
    return await _process_push(db, payload, provider="github")


# ---------------------------------------------------------------------------
# GitLab webhook
# ---------------------------------------------------------------------------


@router.post(
    "/webhooks/gitlab",
    response_model=WebhookResponse,
    summary="Receive GitLab push events",
)
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: str | None = Header(None),
    x_gitlab_event: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Receive a GitLab webhook push event and auto-trigger ingestion.

    Verifies shared secret token if ``EIDOS_WEBHOOK_SECRET`` is set.
    Only processes ``Push Hook`` events.
    """
    webhook_secret = getattr(settings, "webhook_secret", "")
    if webhook_secret:
        if x_gitlab_token != webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid token")

    if x_gitlab_event != "Push Hook":
        return WebhookResponse(accepted=False, message=f"Ignored event: {x_gitlab_event}")

    payload = await request.json()
    return await _process_push(db, payload, provider="gitlab")


# ---------------------------------------------------------------------------
# Generic webhook (any provider)
# ---------------------------------------------------------------------------


@router.post(
    "/webhooks/push",
    response_model=WebhookResponse,
    summary="Generic push webhook (any provider)",
)
async def generic_push_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Generic webhook for any Git provider.

    Expects JSON body with: ``repo_url``, ``branch``, and optionally ``commit_sha``.
    """
    payload = await request.json()
    repo_url = payload.get("repo_url", "")
    branch = payload.get("branch", "")
    commit_sha = payload.get("commit_sha")

    if not repo_url:
        raise HTTPException(status_code=400, detail="Missing repo_url")
    if not branch:
        raise HTTPException(status_code=400, detail="Missing branch")

    # Find matching repo
    result = await db.execute(
        select(Repo).where(Repo.url == repo_url, Repo.default_branch == branch)
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        return WebhookResponse(accepted=False, message="No matching repo found")

    snapshot_id = await _trigger_ingestion(db, repo, commit_sha)
    return WebhookResponse(
        accepted=True,
        message=f"Ingestion triggered for {repo.name}",
        snapshot_id=snapshot_id,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _process_push(
    db: AsyncSession, payload: dict[str, Any], provider: str
) -> WebhookResponse:
    """Process a push event from GitHub or GitLab."""
    if provider == "github":
        repo_url = payload.get("repository", {}).get("clone_url", "")
        # Also try html_url since that's what users register
        if not repo_url:
            repo_url = payload.get("repository", {}).get("html_url", "")
        ref = payload.get("ref", "")  # refs/heads/main
        branch = ref.split("/")[-1] if "/" in ref else ref
        commit_sha = payload.get("after")
    elif provider == "gitlab":
        repo_url = payload.get("project", {}).get("http_url", "")
        ref = payload.get("ref", "")
        branch = ref.split("/")[-1] if "/" in ref else ref
        commit_sha = payload.get("after")
    else:
        return WebhookResponse(accepted=False, message=f"Unknown provider: {provider}")

    if not repo_url:
        return WebhookResponse(accepted=False, message="Could not extract repo URL from payload")

    # Normalize URL (strip .git suffix for matching)
    normalized = repo_url.rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]

    # Find matching repo (try both with and without .git)
    result = await db.execute(
        select(Repo).where(Repo.default_branch == branch)
    )
    repos = result.scalars().all()
    matched_repo = None
    for r in repos:
        r_url = r.url.rstrip("/")
        if r_url.endswith(".git"):
            r_url = r_url[:-4]
        if r_url == normalized:
            matched_repo = r
            break

    if matched_repo is None:
        return WebhookResponse(
            accepted=False,
            message=f"No registered repo matches {normalized} on branch {branch}",
        )

    snapshot_id = await _trigger_ingestion(db, matched_repo, commit_sha)
    logger.info(
        "Webhook (%s): triggered ingestion for repo=%s snapshot=%s",
        provider,
        matched_repo.id,
        snapshot_id,
    )
    return WebhookResponse(
        accepted=True,
        message=f"Ingestion triggered for {matched_repo.name}",
        snapshot_id=snapshot_id,
    )


async def _trigger_ingestion(
    db: AsyncSession, repo: Repo, commit_sha: str | None
) -> str:
    """Create a snapshot and trigger background ingestion."""
    from fastapi import BackgroundTasks

    from app.core.tasks import run_ingestion

    snapshot = RepoSnapshot(
        id=uuid.uuid4().hex[:12],
        repo_id=repo.id,
        commit_sha=commit_sha,
    )
    db.add(snapshot)
    await db.commit()

    # Fire-and-forget ingestion (in production, use a task queue)
    import asyncio

    asyncio.create_task(run_ingestion(snapshot.id))

    return snapshot.id


def _verify_github_signature(body: bytes, secret: str, signature_header: str) -> bool:
    """Verify GitHub HMAC-SHA256 webhook signature."""
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
