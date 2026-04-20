"""
Admin API endpoints.

All endpoints require ``superadmin`` or ``admin`` role (except where noted).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.core.config import settings
from app.storage.database import get_db
from app.storage.models import Plan, UsageRecord, User, UserRole, UserSubscription

router = APIRouter()


# -------------------------------------------------------------------
# Schemas
# -------------------------------------------------------------------


class UserOut(BaseModel):
    id: str
    github_login: str
    name: str
    email: str
    role: str
    created_at: str

    model_config = {"from_attributes": True}


class RoleUpdate(BaseModel):
    role: str


class PlanCreate(BaseModel):
    name: str
    description: str = ""
    limits: dict[str, Any]


class PlanOut(BaseModel):
    id: str
    name: str
    description: str
    limits: str
    is_active: bool

    model_config = {"from_attributes": True}


class SubscriptionAssign(BaseModel):
    plan_id: str
    expires_at: str | None = None


class UsageOut(BaseModel):
    user_id: str
    action: str
    tokens_used: int
    created_at: str


class SystemInfo(BaseModel):
    edition: str
    version: str
    auth_enabled: bool
    parsers: int
    users: int
    repos: int


# -------------------------------------------------------------------
# System info (superadmin only)
# -------------------------------------------------------------------


@router.get(
    "/system",
    response_model=SystemInfo,
    dependencies=[Depends(require_role("superadmin"))],
)
async def system_info(db: AsyncSession = Depends(get_db)) -> Any:
    from app.analysis.parser_registry import supported_languages
    from app.storage.models import Repo

    user_count = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    repo_count = (await db.execute(select(func.count()).select_from(Repo))).scalar() or 0
    return SystemInfo(
        edition=settings.edition,
        version=settings.version,
        auth_enabled=settings.auth_enabled,
        parsers=len(supported_languages()),
        users=user_count,
        repos=repo_count,
    )


# -------------------------------------------------------------------
# User management
# -------------------------------------------------------------------


@router.get(
    "/users",
    response_model=list[UserOut],
    dependencies=[Depends(require_role("superadmin", "admin", "support"))],
)
async def list_users(db: AsyncSession = Depends(get_db)) -> Any:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        UserOut(
            id=u.id,
            github_login=u.github_login,
            name=u.name,
            email=u.email,
            role=u.role,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]


@router.put(
    "/users/{user_id}/role",
    response_model=UserOut,
    dependencies=[Depends(require_role("superadmin"))],
)
async def update_user_role(
    user_id: str,
    body: RoleUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    valid_roles = {r.value for r in UserRole}
    if body.role not in valid_roles:
        raise HTTPException(status_code=422, detail=f"Invalid role. Must be one of: {valid_roles}")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = body.role
    await db.commit()
    await db.refresh(user)
    return UserOut(
        id=user.id,
        github_login=user.github_login,
        name=user.name,
        email=user.email,
        role=user.role,
        created_at=user.created_at.isoformat(),
    )


# -------------------------------------------------------------------
# Plan management
# -------------------------------------------------------------------


@router.get(
    "/plans",
    response_model=list[PlanOut],
    dependencies=[Depends(require_role("superadmin", "admin"))],
)
async def list_plans(db: AsyncSession = Depends(get_db)) -> Any:
    result = await db.execute(select(Plan).order_by(Plan.name))
    return result.scalars().all()


@router.post(
    "/plans",
    response_model=PlanOut,
    status_code=201,
    dependencies=[Depends(require_role("superadmin"))],
)
async def create_plan(
    body: PlanCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    plan = Plan(
        id=uuid.uuid4().hex[:12],
        name=body.name,
        description=body.description,
        limits=json.dumps(body.limits),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


# -------------------------------------------------------------------
# Subscription management
# -------------------------------------------------------------------


@router.put(
    "/users/{user_id}/subscription",
    dependencies=[Depends(require_role("superadmin", "admin", "support"))],
)
async def assign_subscription(
    user_id: str,
    body: SubscriptionAssign,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    plan = await db.get(Plan, body.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Deactivate existing subscriptions
    result = await db.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user_id,
            UserSubscription.is_active.is_(True),
        )
    )
    for sub in result.scalars().all():
        sub.is_active = False

    from datetime import datetime

    new_sub = UserSubscription(
        id=uuid.uuid4().hex[:12],
        user_id=user_id,
        plan_id=body.plan_id,
        expires_at=(datetime.fromisoformat(body.expires_at) if body.expires_at else None),
    )
    db.add(new_sub)
    await db.commit()
    return {"status": "ok", "subscription_id": new_sub.id, "plan": plan.name}


# -------------------------------------------------------------------
# Usage analytics
# -------------------------------------------------------------------


@router.get(
    "/usage",
    response_model=list[UsageOut],
    dependencies=[Depends(require_role("superadmin", "admin", "support"))],
)
async def list_usage(
    user_id: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> Any:
    q = select(UsageRecord).order_by(UsageRecord.created_at.desc()).limit(limit)
    if user_id:
        q = q.where(UsageRecord.user_id == user_id)
    result = await db.execute(q)
    return [
        UsageOut(
            user_id=r.user_id,
            action=r.action,
            tokens_used=r.tokens_used,
            created_at=r.created_at.isoformat(),
        )
        for r in result.scalars().all()
    ]
