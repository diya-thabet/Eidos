"""
Usage metering engine.

Checks whether a user has remaining quota under their active plan.
Plan limits are stored as JSON and interpreted at runtime, so the
criteria can be changed without code modifications.

Supported limit types:
    - unlimited    -- no restrictions
    - time_based   -- trial_days from subscription start
    - token_based  -- daily_tokens ceiling
    - scan_based   -- monthly_scans ceiling
    - combo        -- all criteria must pass
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.storage.models import Plan, UsageRecord, UserSubscription

logger = logging.getLogger(__name__)

_UNLIMITED: dict[str, str] = {"type": "unlimited"}


async def check_quota(
    user_id: str,
    action: str,
    db: AsyncSession,
) -> tuple[bool, str]:
    """
    Check if the user may perform *action*.

    Returns (allowed, reason).
    """
    sub = await _get_active_subscription(user_id, db)
    if sub is None:
        return False, "No active subscription"

    limits = _parse_limits(sub.plan)
    limit_type = limits.get("type", "")

    if limit_type == "unlimited":
        return True, "unlimited"

    if limit_type == "time_based":
        return _check_time(sub, limits)

    if limit_type == "token_based":
        return await _check_tokens(user_id, limits, db)

    if limit_type == "scan_based":
        return await _check_scans(user_id, action, limits, db)

    if limit_type == "combo":
        time_ok, time_msg = _check_time(sub, limits)
        if not time_ok:
            return False, time_msg
        scan_ok, scan_msg = await _check_scans(user_id, action, limits, db)
        if not scan_ok:
            return False, scan_msg
        tok_ok, tok_msg = await _check_tokens(user_id, limits, db)
        if not tok_ok:
            return False, tok_msg
        return True, "combo: all checks passed"

    return False, f"Unknown limit type: {limit_type}"


async def record_usage(
    user_id: str,
    action: str,
    db: AsyncSession,
    resource_id: str = "",
    tokens_used: int = 0,
) -> None:
    """Record a usage event."""
    db.add(
        UsageRecord(
            user_id=user_id,
            action=action,
            resource_id=resource_id,
            tokens_used=tokens_used,
        )
    )
    await db.flush()


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------


async def _get_active_subscription(user_id: str, db: AsyncSession) -> UserSubscription | None:
    result = await db.execute(
        select(UserSubscription)
        .options(selectinload(UserSubscription.plan))
        .where(
            UserSubscription.user_id == user_id,
            UserSubscription.is_active.is_(True),
        )
        .order_by(UserSubscription.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _parse_limits(plan: Plan) -> dict[str, Any]:
    try:
        return json.loads(plan.limits) if plan.limits else _UNLIMITED
    except (json.JSONDecodeError, TypeError):
        logger.warning("Invalid plan limits JSON for plan %s", plan.id)
        return _UNLIMITED


def _check_time(sub: UserSubscription, limits: dict[str, Any]) -> tuple[bool, str]:
    trial_days = limits.get("trial_days", 0)
    if trial_days <= 0:
        return True, "no time limit"
    started = sub.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    expires = started + timedelta(days=trial_days)
    now = datetime.now(UTC)
    if now < expires:
        remaining = (expires - now).days
        return True, f"trial: {remaining} days remaining"
    return False, "Free trial expired"


async def _check_tokens(user_id: str, limits: dict[str, Any], db: AsyncSession) -> tuple[bool, str]:
    daily_limit = limits.get("daily_tokens", 0)
    if daily_limit <= 0:
        return True, "no token limit"
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(UsageRecord.tokens_used), 0)).where(
            UsageRecord.user_id == user_id,
            UsageRecord.created_at >= today_start,
        )
    )
    used = result.scalar() or 0
    if used < daily_limit:
        return True, f"tokens: {used}/{daily_limit} today"
    return False, f"Daily token limit reached ({daily_limit})"


async def _check_scans(
    user_id: str, action: str, limits: dict[str, Any], db: AsyncSession
) -> tuple[bool, str]:
    monthly_limit = limits.get("monthly_scans", 0)
    if monthly_limit <= 0:
        return True, "no scan limit"
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count()).where(
            UsageRecord.user_id == user_id,
            UsageRecord.action == action,
            UsageRecord.created_at >= month_start,
        )
    )
    count = result.scalar() or 0
    if count < monthly_limit:
        return True, f"scans: {count}/{monthly_limit} this month"
    return False, f"Monthly scan limit reached ({monthly_limit})"
