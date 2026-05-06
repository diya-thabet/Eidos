"""API endpoints for resource-level repo permissions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.scopes import protected
from app.storage.database import get_db
from app.storage.models import (
    Repo,
    RepoPermission,
    RepoPermissionLevel,
    User,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PermissionGrant(BaseModel):
    user_id: str
    level: str = "viewer"  # viewer, editor, owner


class PermissionOut(BaseModel):
    id: int
    repo_id: str
    user_id: str
    level: str
    granted_by: str | None
    granted_at: str


class PermissionUpdate(BaseModel):
    level: str


# ---------------------------------------------------------------------------
# Grant permission
# ---------------------------------------------------------------------------


@router.post(
    "/{repo_id}/permissions",
    response_model=PermissionOut,
    status_code=201,
    summary="Grant a user access to a repo",
    dependencies=[Depends(protected(
        scope="write:repos",
        require_repo_owner=True,
    ))],
)
async def grant_permission(
    repo_id: str,
    body: PermissionGrant,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PermissionOut:
    """Grant or update a user's access level to a repo.

    Only repo owners and admins can grant permissions.
    """
    # Validate level
    if body.level not in [e.value for e in RepoPermissionLevel]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid level. Must be one of: {[e.value for e in RepoPermissionLevel]}",
        )

    # Verify repo exists
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    # Verify target user exists
    target = await db.get(User, body.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target user not found")

    # Cannot grant to self
    if body.user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot grant permissions to yourself")

    # Check existing
    result = await db.execute(
        select(RepoPermission).where(
            RepoPermission.repo_id == repo_id,
            RepoPermission.user_id == body.user_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.level = body.level
        existing.granted_by = user.id
    else:
        existing = RepoPermission(
            repo_id=repo_id,
            user_id=body.user_id,
            level=body.level,
            granted_by=user.id,
        )
        db.add(existing)

    await db.commit()
    await db.refresh(existing)

    # Invalidate permission cache for target user
    from app.auth.permission_cache import permission_cache
    permission_cache.invalidate_user(body.user_id)

    # Audit log
    from app.auth.audit_helpers import build_permission_change_event
    db.add(build_permission_change_event(
        user_id=user.id,
        action="permission.granted",
        resource_type="repo",
        resource_id=repo_id,
        metadata={"target_user": body.user_id, "level": body.level},
    ))
    await db.commit()

    return PermissionOut(
        id=existing.id,
        repo_id=existing.repo_id,
        user_id=existing.user_id,
        level=existing.level,
        granted_by=existing.granted_by,
        granted_at=existing.granted_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# List permissions
# ---------------------------------------------------------------------------


@router.get(
    "/{repo_id}/permissions",
    response_model=list[PermissionOut],
    summary="List who has access to a repo",
    dependencies=[Depends(protected(scope="read:repos", require_repo_owner=True))],
)
async def list_permissions(
    repo_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[PermissionOut]:
    """List all permissions for a repo."""
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    result = await db.execute(
        select(RepoPermission)
        .where(RepoPermission.repo_id == repo_id)
        .order_by(RepoPermission.granted_at.desc())
    )
    perms = result.scalars().all()
    return [
        PermissionOut(
            id=p.id,
            repo_id=p.repo_id,
            user_id=p.user_id,
            level=p.level,
            granted_by=p.granted_by,
            granted_at=p.granted_at.isoformat(),
        )
        for p in perms
    ]


# ---------------------------------------------------------------------------
# Revoke permission
# ---------------------------------------------------------------------------


@router.delete(
    "/{repo_id}/permissions/{user_id}",
    status_code=204,
    summary="Revoke a user's access to a repo",
    dependencies=[Depends(protected(scope="write:repos", require_repo_owner=True))],
)
async def revoke_permission(
    repo_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke a user's access to a repo."""
    result = await db.execute(
        select(RepoPermission).where(
            RepoPermission.repo_id == repo_id,
            RepoPermission.user_id == user_id,
        )
    )
    perm = result.scalar_one_or_none()
    if perm is None:
        raise HTTPException(status_code=404, detail="Permission not found")
    await db.delete(perm)
    await db.commit()

    # Invalidate permission cache
    from app.auth.permission_cache import permission_cache
    permission_cache.invalidate_user(user_id)

    # Audit log
    from app.auth.audit_helpers import build_permission_change_event
    db.add(build_permission_change_event(
        user_id=user_id,
        action="permission.revoked",
        resource_type="repo",
        resource_id=repo_id,
        metadata={"revoked_user": user_id},
    ))
    await db.commit()
