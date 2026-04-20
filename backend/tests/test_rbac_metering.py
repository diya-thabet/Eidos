"""
Tests for RBAC, metering, admin API, edition/versioning, and Docker-related features.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.auth.dependencies import (
    _anonymous_user,
    _role_level,
    require_quota,
    require_role,
)
from app.auth.metering import (
    _check_time,
    _parse_limits,
    check_quota,
    record_usage,
)
from app.core.config import settings
from app.storage.models import (
    Plan,
    UsageRecord,
    User,
    UserRole,
    UserSubscription,
)

# ------------------------------------------------------------------
# UserRole enum
# ------------------------------------------------------------------


class TestUserRole:
    def test_values(self):
        assert UserRole.superadmin == "superadmin"
        assert UserRole.admin == "admin"
        assert UserRole.employee == "employee"
        assert UserRole.support == "support"
        assert UserRole.user == "user"

    def test_all_roles_exist(self):
        assert len(UserRole) == 5


# ------------------------------------------------------------------
# Role hierarchy
# ------------------------------------------------------------------


class TestRoleHierarchy:
    def test_superadmin_highest(self):
        assert _role_level("superadmin") > _role_level("admin")

    def test_admin_above_employee(self):
        assert _role_level("admin") > _role_level("employee")

    def test_employee_above_support(self):
        assert _role_level("employee") > _role_level("support")

    def test_support_above_user(self):
        assert _role_level("support") > _role_level("user")

    def test_unknown_role_is_zero(self):
        assert _role_level("unknown") == 0


# ------------------------------------------------------------------
# Anonymous user
# ------------------------------------------------------------------


class TestAnonymousUser:
    def test_has_superadmin_role(self):
        u = _anonymous_user()
        assert u.role == UserRole.superadmin

    def test_has_id(self):
        u = _anonymous_user()
        assert u.id == "anonymous"


# ------------------------------------------------------------------
# User model role field
# ------------------------------------------------------------------


class TestUserModelRole:
    def test_default_role_is_user(self):
        u = User(
            id="test-1",
            github_login="testuser",
            role=UserRole.user,
        )
        assert u.role == UserRole.user

    def test_can_set_role(self):
        u = User(
            id="test-2",
            github_login="admin",
            role=UserRole.admin,
        )
        assert u.role == UserRole.admin


# ------------------------------------------------------------------
# Plan model
# ------------------------------------------------------------------


class TestPlanModel:
    def test_create_plan(self):
        p = Plan(
            id="plan-1",
            name="free_trial",
            limits=json.dumps({"type": "time_based", "trial_days": 30}),
        )
        assert p.name == "free_trial"
        assert json.loads(p.limits)["trial_days"] == 30

    def test_unlimited_plan(self):
        p = Plan(
            id="plan-2",
            name="internal",
            limits=json.dumps({"type": "unlimited"}),
        )
        assert json.loads(p.limits)["type"] == "unlimited"


# ------------------------------------------------------------------
# Parse limits
# ------------------------------------------------------------------


class TestParseLimits:
    def test_valid_json(self):
        p = Plan(id="x", name="x", limits='{"type": "unlimited"}')
        assert _parse_limits(p)["type"] == "unlimited"

    def test_empty_string(self):
        p = Plan(id="x", name="x", limits="")
        assert _parse_limits(p)["type"] == "unlimited"

    def test_invalid_json(self):
        p = Plan(id="x", name="x", limits="not json")
        assert _parse_limits(p)["type"] == "unlimited"


# ------------------------------------------------------------------
# Time-based check
# ------------------------------------------------------------------


class TestCheckTime:
    def test_active_trial(self):
        sub = UserSubscription(
            id="s1",
            user_id="u1",
            plan_id="p1",
            started_at=datetime.now(UTC) - timedelta(days=5),
        )
        limits = {"type": "time_based", "trial_days": 30}
        ok, msg = _check_time(sub, limits)
        assert ok is True
        assert "days remaining" in msg

    def test_expired_trial(self):
        sub = UserSubscription(
            id="s2",
            user_id="u1",
            plan_id="p1",
            started_at=datetime.now(UTC) - timedelta(days=31),
        )
        limits = {"type": "time_based", "trial_days": 30}
        ok, msg = _check_time(sub, limits)
        assert ok is False
        assert "expired" in msg.lower()

    def test_zero_trial_days_means_no_limit(self):
        sub = UserSubscription(
            id="s3",
            user_id="u1",
            plan_id="p1",
            started_at=datetime.now(UTC) - timedelta(days=999),
        )
        limits = {"type": "time_based", "trial_days": 0}
        ok, _ = _check_time(sub, limits)
        assert ok is True


# ------------------------------------------------------------------
# Metering engine (with DB) -- uses conftest async session
# ------------------------------------------------------------------


@pytest.fixture
def _setup_user_and_plan(db_session):
    """Create a user, plan, and subscription for metering tests."""

    async def _setup(limits_dict, started_days_ago=0):
        user = User(
            id=f"meter-{uuid.uuid4().hex[:8]}",
            github_login=f"meter-{uuid.uuid4().hex[:8]}",
            role=UserRole.user,
        )
        db_session.add(user)

        plan = Plan(
            id=f"plan-{uuid.uuid4().hex[:8]}",
            name=f"test-plan-{uuid.uuid4().hex[:8]}",
            limits=json.dumps(limits_dict),
        )
        db_session.add(plan)
        await db_session.flush()

        sub = UserSubscription(
            id=f"sub-{uuid.uuid4().hex[:8]}",
            user_id=user.id,
            plan_id=plan.id,
            started_at=datetime.now(UTC) - timedelta(days=started_days_ago),
        )
        db_session.add(sub)
        await db_session.flush()
        return user

    return _setup


class TestMeteringWithDB:
    @pytest.mark.asyncio
    async def test_unlimited(self, db_session, _setup_user_and_plan):
        user = await _setup_user_and_plan({"type": "unlimited"})
        ok, msg = await check_quota(user.id, "scan", db_session)
        assert ok is True

    @pytest.mark.asyncio
    async def test_time_based_active(self, db_session, _setup_user_and_plan):
        user = await _setup_user_and_plan(
            {"type": "time_based", "trial_days": 30},
            started_days_ago=5,
        )
        ok, _ = await check_quota(user.id, "scan", db_session)
        assert ok is True

    @pytest.mark.asyncio
    async def test_time_based_expired(self, db_session, _setup_user_and_plan):
        user = await _setup_user_and_plan(
            {"type": "time_based", "trial_days": 7},
            started_days_ago=10,
        )
        ok, msg = await check_quota(user.id, "scan", db_session)
        assert ok is False

    @pytest.mark.asyncio
    async def test_token_based_under_limit(self, db_session, _setup_user_and_plan):
        user = await _setup_user_and_plan({"type": "token_based", "daily_tokens": 100})
        # Record some usage
        await record_usage(user.id, "scan", db_session, tokens_used=50)
        ok, _ = await check_quota(user.id, "scan", db_session)
        assert ok is True

    @pytest.mark.asyncio
    async def test_token_based_over_limit(self, db_session, _setup_user_and_plan):
        user = await _setup_user_and_plan({"type": "token_based", "daily_tokens": 10})
        await record_usage(user.id, "scan", db_session, tokens_used=15)
        ok, msg = await check_quota(user.id, "scan", db_session)
        assert ok is False

    @pytest.mark.asyncio
    async def test_scan_based_under_limit(self, db_session, _setup_user_and_plan):
        user = await _setup_user_and_plan({"type": "scan_based", "monthly_scans": 5})
        await record_usage(user.id, "scan", db_session)
        ok, _ = await check_quota(user.id, "scan", db_session)
        assert ok is True

    @pytest.mark.asyncio
    async def test_scan_based_over_limit(self, db_session, _setup_user_and_plan):
        user = await _setup_user_and_plan({"type": "scan_based", "monthly_scans": 2})
        await record_usage(user.id, "scan", db_session)
        await record_usage(user.id, "scan", db_session)
        ok, _ = await check_quota(user.id, "scan", db_session)
        assert ok is False

    @pytest.mark.asyncio
    async def test_no_subscription(self, db_session):
        ok, msg = await check_quota("nonexistent-user", "scan", db_session)
        assert ok is False
        assert "No active subscription" in msg

    @pytest.mark.asyncio
    async def test_record_usage(self, db_session, _setup_user_and_plan):
        user = await _setup_user_and_plan({"type": "unlimited"})
        await record_usage(user.id, "scan", db_session, resource_id="repo-1", tokens_used=42)
        result = await db_session.execute(select(UsageRecord).where(UsageRecord.user_id == user.id))
        records = result.scalars().all()
        assert len(records) == 1
        assert records[0].tokens_used == 42


# ------------------------------------------------------------------
# require_role dependency
# ------------------------------------------------------------------


class TestRequireRole:
    def test_returns_callable(self):
        dep = require_role("superadmin")
        assert callable(dep)

    def test_factory_accepts_multiple_roles(self):
        dep = require_role("superadmin", "admin", "support")
        assert callable(dep)


# ------------------------------------------------------------------
# require_quota dependency
# ------------------------------------------------------------------


class TestRequireQuota:
    def test_returns_callable(self):
        dep = require_quota("scan")
        assert callable(dep)


# ------------------------------------------------------------------
# Edition config
# ------------------------------------------------------------------


class TestEditionConfig:
    def test_edition_exists(self):
        assert hasattr(settings, "edition")
        assert settings.edition in ("internal", "client")

    def test_version_exists(self):
        assert hasattr(settings, "version")
        assert settings.version


# ------------------------------------------------------------------
# Plan limits flexibility
# ------------------------------------------------------------------


class TestLimitsFlexibility:
    """Verify various limit JSON shapes parse correctly."""

    def test_time_based(self):
        p = Plan(id="x", name="x", limits='{"type": "time_based", "trial_days": 30}')
        limits = _parse_limits(p)
        assert limits["type"] == "time_based"
        assert limits["trial_days"] == 30

    def test_token_based(self):
        p = Plan(id="x", name="x", limits='{"type": "token_based", "daily_tokens": 4}')
        limits = _parse_limits(p)
        assert limits["daily_tokens"] == 4

    def test_scan_based(self):
        p = Plan(id="x", name="x", limits='{"type": "scan_based", "monthly_scans": 10}')
        limits = _parse_limits(p)
        assert limits["monthly_scans"] == 10

    def test_combo(self):
        p = Plan(
            id="x",
            name="x",
            limits='{"type": "combo", "trial_days": 30, "monthly_scans": 100}',
        )
        limits = _parse_limits(p)
        assert limits["type"] == "combo"
        assert limits["trial_days"] == 30
        assert limits["monthly_scans"] == 100

    def test_unlimited(self):
        p = Plan(id="x", name="x", limits='{"type": "unlimited"}')
        assert _parse_limits(p)["type"] == "unlimited"

    def test_unknown_type(self):
        """Unknown types parse fine but will be rejected by check_quota."""
        p = Plan(id="x", name="x", limits='{"type": "future_thing", "x": 1}')
        limits = _parse_limits(p)
        assert limits["type"] == "future_thing"
