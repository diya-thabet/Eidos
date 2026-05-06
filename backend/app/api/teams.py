"""API endpoints for team/organization management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.scopes import require_scope
from app.storage.database import get_db
from app.storage.models import (
    Repo,
    RepoPermissionLevel,
    Team,
    TeamMember,
    TeamRepoAccess,
    TeamRole,
    User,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TeamCreate(BaseModel):
    name: str
    description: str = ""


class TeamUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class TeamOut(BaseModel):
    id: str
    name: str
    description: str
    created_by: str
    created_at: str
    member_count: int = 0


class TeamMemberOut(BaseModel):
    user_id: str
    role: str
    joined_at: str


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "member"


class TeamRepoAccessRequest(BaseModel):
    repo_id: str
    level: str = "viewer"


class TeamRepoAccessOut(BaseModel):
    id: int
    team_id: str
    repo_id: str
    level: str
    granted_by: str | None
    granted_at: str


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=TeamOut,
    status_code=201,
    summary="Create a team",
    dependencies=[Depends(require_scope("write:repos"))],
)
async def create_team(
    body: TeamCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamOut:
    """Create a new team. Creator becomes admin member."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name required")

    team = Team(
        id=uuid.uuid4().hex[:12],
        name=name,
        description=body.description.strip(),
        created_by=user.id,
    )
    db.add(team)
    # Creator is automatically admin
    db.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.admin))
    await db.commit()
    await db.refresh(team)

    return TeamOut(
        id=team.id, name=team.name, description=team.description,
        created_by=team.created_by, created_at=team.created_at.isoformat(),
        member_count=1,
    )


@router.get(
    "",
    response_model=list[TeamOut],
    summary="List my teams",
    dependencies=[Depends(require_scope("read:repos"))],
)
async def list_teams(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamOut]:
    """List teams the current user belongs to."""
    result = await db.execute(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
        .order_by(Team.created_at.desc())
    )
    teams = result.scalars().all()
    out = []
    for t in teams:
        count_result = await db.execute(
            select(TeamMember).where(TeamMember.team_id == t.id)
        )
        count = len(count_result.scalars().all())
        out.append(TeamOut(
            id=t.id, name=t.name, description=t.description,
            created_by=t.created_by, created_at=t.created_at.isoformat(),
            member_count=count,
        ))
    return out


@router.get(
    "/{team_id}",
    response_model=TeamOut,
    summary="Get team details",
    dependencies=[Depends(require_scope("read:repos"))],
)
async def get_team(
    team_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamOut:
    """Get team details. Must be a member."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    # Check membership
    await _require_membership(db, team_id, user.id)

    count_result = await db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id)
    )
    count = len(count_result.scalars().all())

    return TeamOut(
        id=team.id, name=team.name, description=team.description,
        created_by=team.created_by, created_at=team.created_at.isoformat(),
        member_count=count,
    )


@router.patch(
    "/{team_id}",
    response_model=TeamOut,
    summary="Update team",
    dependencies=[Depends(require_scope("write:repos"))],
)
async def update_team(
    team_id: str,
    body: TeamUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamOut:
    """Update team name/description. Must be team admin."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    await _require_team_admin(db, team_id, user)

    if body.name is not None:
        team.name = body.name.strip()
    if body.description is not None:
        team.description = body.description.strip()
    await db.commit()
    await db.refresh(team)

    count_result = await db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id)
    )
    count = len(count_result.scalars().all())

    return TeamOut(
        id=team.id, name=team.name, description=team.description,
        created_by=team.created_by, created_at=team.created_at.isoformat(),
        member_count=count,
    )


@router.delete(
    "/{team_id}",
    status_code=204,
    summary="Delete team",
    dependencies=[Depends(require_scope("write:repos"))],
)
async def delete_team(
    team_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a team. Must be team admin."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    await _require_team_admin(db, team_id, user)
    await db.delete(team)
    await db.commit()


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.get(
    "/{team_id}/members",
    response_model=list[TeamMemberOut],
    summary="List team members",
    dependencies=[Depends(require_scope("read:repos"))],
)
async def list_members(
    team_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamMemberOut]:
    """List all members of a team."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    await _require_membership(db, team_id, user.id)

    result = await db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id)
    )
    members = result.scalars().all()
    return [
        TeamMemberOut(
            user_id=m.user_id, role=m.role, joined_at=m.joined_at.isoformat(),
        )
        for m in members
    ]


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberOut,
    status_code=201,
    summary="Add a member to team",
    dependencies=[Depends(require_scope("write:repos"))],
)
async def add_member(
    team_id: str,
    body: AddMemberRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamMemberOut:
    """Add a user to the team. Must be team admin."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    await _require_team_admin(db, team_id, user)

    if body.role not in [e.value for e in TeamRole]:
        raise HTTPException(status_code=400, detail="Invalid role")

    target = await db.get(User, body.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Check existing
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == body.user_id,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="User already a member")

    member = TeamMember(team_id=team_id, user_id=body.user_id, role=body.role)
    db.add(member)
    await db.commit()
    await db.refresh(member)

    return TeamMemberOut(
        user_id=member.user_id, role=member.role,
        joined_at=member.joined_at.isoformat(),
    )


@router.delete(
    "/{team_id}/members/{member_user_id}",
    status_code=204,
    summary="Remove a member from team",
    dependencies=[Depends(require_scope("write:repos"))],
)
async def remove_member(
    team_id: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a user from the team. Must be team admin."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    await _require_team_admin(db, team_id, user)

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == member_user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    await db.delete(member)
    await db.commit()


# ---------------------------------------------------------------------------
# Team repo access
# ---------------------------------------------------------------------------


@router.post(
    "/{team_id}/repos",
    response_model=TeamRepoAccessOut,
    status_code=201,
    summary="Grant team access to a repo",
    dependencies=[Depends(require_scope("write:repos"))],
)
async def grant_team_repo_access(
    team_id: str,
    body: TeamRepoAccessRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamRepoAccessOut:
    """Grant a team access to a repo. Must be team admin."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    await _require_team_admin(db, team_id, user)

    if body.level not in [e.value for e in RepoPermissionLevel]:
        raise HTTPException(status_code=400, detail="Invalid level")

    repo = await db.get(Repo, body.repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    # Upsert
    result = await db.execute(
        select(TeamRepoAccess).where(
            TeamRepoAccess.team_id == team_id,
            TeamRepoAccess.repo_id == body.repo_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.level = body.level
        existing.granted_by = user.id
    else:
        existing = TeamRepoAccess(
            team_id=team_id, repo_id=body.repo_id,
            level=body.level, granted_by=user.id,
        )
        db.add(existing)

    await db.commit()
    await db.refresh(existing)

    return TeamRepoAccessOut(
        id=existing.id, team_id=existing.team_id,
        repo_id=existing.repo_id, level=existing.level,
        granted_by=existing.granted_by,
        granted_at=existing.granted_at.isoformat(),
    )


@router.get(
    "/{team_id}/repos",
    response_model=list[TeamRepoAccessOut],
    summary="List team's repo access",
    dependencies=[Depends(require_scope("read:repos"))],
)
async def list_team_repos(
    team_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamRepoAccessOut]:
    """List repos a team has access to."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    await _require_membership(db, team_id, user.id)

    result = await db.execute(
        select(TeamRepoAccess).where(TeamRepoAccess.team_id == team_id)
    )
    accesses = result.scalars().all()
    return [
        TeamRepoAccessOut(
            id=a.id, team_id=a.team_id, repo_id=a.repo_id,
            level=a.level, granted_by=a.granted_by,
            granted_at=a.granted_at.isoformat(),
        )
        for a in accesses
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_membership(db: AsyncSession, team_id: str, user_id: str) -> None:
    """Raise 404 if user is not a member of the team."""
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Team not found")


async def _require_team_admin(db: AsyncSession, team_id: str, user: User) -> None:
    """Raise 403 if user is not a team admin (or app admin)."""
    # App admins bypass
    if user.role in ("superadmin", "admin"):
        return

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user.id,
            TeamMember.role == TeamRole.admin,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Team admin required")
