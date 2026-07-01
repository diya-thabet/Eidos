from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SnapshotStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class UserRole(enum.StrEnum):
    superadmin = "superadmin"
    admin = "admin"
    employee = "employee"
    support = "support"
    user = "user"


class User(Base):
    """An authenticated user (via GitHub OAuth, Google OAuth, or local)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    # github | google | local
    auth_provider: Mapped[str] = mapped_column(String(16), default="github")
    github_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    github_login: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), default="")
    email: Mapped[str] = mapped_column(String(512), default="")
    avatar_url: Mapped[str] = mapped_column(Text, default="")
    github_token_enc: Mapped[str] = mapped_column(Text, default="")
    password_hash: Mapped[str] = mapped_column(Text, default="")  # bcrypt hash for local auth
    role: Mapped[str] = mapped_column(String(32), default=UserRole.user)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    repos: Mapped[list[Repo]] = relationship(back_populates="owner")
    subscriptions: Mapped[list[UserSubscription]] = relationship(back_populates="user")

    __table_args__ = (Index("ix_users_github_login", "github_login"),)


class ApiKey(Base):
    """An API key for programmatic access (CI/CD, scripts)."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    scopes: Mapped[str] = mapped_column(Text, default="*")  # Comma-separated
    is_active: Mapped[bool] = mapped_column(default=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_api_keys_user", "user_id"),
        Index("ix_api_keys_prefix", "prefix"),
    )


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), default="main")
    git_provider: Mapped[str] = mapped_column(
        String(32), default="github"
    )  # github | gitlab | azure_devops | bitbucket | other
    git_token_enc: Mapped[str] = mapped_column(
        Text, default=""
    )  # Fernet-encrypted PAT / token for private repos
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[User | None] = relationship(back_populates="repos")
    snapshots: Mapped[list[RepoSnapshot]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )


class RepoSnapshot(Base):
    __tablename__ = "repo_snapshots"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    commit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[SnapshotStatus] = mapped_column(
        Enum(SnapshotStatus, name="snapshot_status"), default=SnapshotStatus.pending
    )
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    repo: Mapped[Repo] = relationship(back_populates="snapshots")
    files: Mapped[list[File]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    snapshot: Mapped[RepoSnapshot] = relationship(back_populates="files")

    __table_args__ = (Index("ix_files_snapshot_path", "snapshot_id", "path"),)


class SymbolNote(Base):
    """User annotation on a symbol."""

    __tablename__ = "symbol_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False,
    )
    symbol_fq_name: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_symbol_notes_snapshot_fq", "snapshot_id", "symbol_fq_name"),
    )


class CoverageReport(Base):
    """Test coverage report for a snapshot."""

    __tablename__ = "coverage_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    overall_percent: Mapped[float] = mapped_column(default=0.0)
    branch_percent: Mapped[float] = mapped_column(default=0.0)
    covered_lines: Mapped[int] = mapped_column(default=0)
    missing_lines: Mapped[int] = mapped_column(default=0)
    num_statements: Mapped[int] = mapped_column(default=0)
    num_branches: Mapped[int] = mapped_column(default=0)
    covered_branches: Mapped[int] = mapped_column(default=0)
    file_count: Mapped[int] = mapped_column(default=0)
    files_json: Mapped[str] = mapped_column(Text, default="[]")  # Per-file summary list
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_coverage_snapshot", "snapshot_id"),
    )


class QualityGate(Base):
    """Configurable quality gate thresholds for a repo."""

    __tablename__ = "quality_gates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[str] = mapped_column(
        ForeignKey("repos.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_quality_gates_repo", "repo_id"),
    )


class QualityGateResult(Base):
    """Result of evaluating a quality gate against a snapshot."""

    __tablename__ = "quality_gate_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gate_id: Mapped[int] = mapped_column(
        ForeignKey("quality_gates.id", ondelete="CASCADE"), nullable=False,
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # "passed" | "failed"
    violations_json: Mapped[str] = mapped_column(Text, default="[]")
    summary: Mapped[str] = mapped_column(Text, default="")
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_gate_results_snapshot", "snapshot_id", "gate_id"),
    )


class SnapshotTag(Base):
    """Tag attached to a snapshot for organization and filtering."""

    __tablename__ = "snapshot_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False,
    )
    tag: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("snapshot_id", "tag", name="uq_snapshot_tag"),
        Index("ix_snapshot_tags_tag", "tag"),
    )


class HealthScoreHistory(Base):
    """Persisted health score for a snapshot."""

    __tablename__ = "health_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    overall: Mapped[float] = mapped_column(default=0.0)
    grade: Mapped[str] = mapped_column(String(2), default="F")
    category_scores_json: Mapped[str] = mapped_column(Text, default="{}")
    total_findings: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_health_scores_snapshot", "snapshot_id"),
    )


class HealthFindingPersisted(Base):
    """Persisted health finding for incremental analysis."""

    __tablename__ = "health_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False,
    )
    symbol_fq_name: Mapped[str] = mapped_column(Text, default="")
    rule_id: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, default="")
    line: Mapped[int] = mapped_column(Integer, default=0)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_health_findings_snapshot", "snapshot_id"),
        Index("ix_health_findings_fingerprint", "snapshot_id", "fingerprint"),
    )


class RepoPermissionLevel(enum.StrEnum):
    viewer = "viewer"
    editor = "editor"
    owner = "owner"


class RepoPermission(Base):
    """Resource-level permission granting a user access to a repo."""

    __tablename__ = "repo_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[str] = mapped_column(
        ForeignKey("repos.id", ondelete="CASCADE"), nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    granted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("repo_id", "user_id", name="uq_repo_user_perm"),
        Index("ix_repo_perm_user", "user_id"),
        Index("ix_repo_perm_repo", "repo_id"),
    )


class TeamRole(enum.StrEnum):
    admin = "admin"
    member = "member"


class Team(Base):
    """A team/organization grouping users."""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(48), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    """Membership link between a user and a team."""

    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), default="member")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    team = relationship("Team", back_populates="members")

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_user"),
        Index("ix_team_member_user", "user_id"),
    )


class TeamRepoAccess(Base):
    """Grants a team access to a repo at a specific level."""

    __tablename__ = "team_repo_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False,
    )
    repo_id: Mapped[str] = mapped_column(
        ForeignKey("repos.id", ondelete="CASCADE"), nullable=False,
    )
    level: Mapped[str] = mapped_column(String(16), default="viewer")
    granted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("team_id", "repo_id", name="uq_team_repo"),
        Index("ix_team_repo_team", "team_id"),
    )


class AuditEvent(Base):
    """Immutable audit log entry for compliance tracking."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_email: Mapped[str] = mapped_column(String(256), default="")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(256), default="")
    method: Mapped[str] = mapped_column(String(10), default="")
    path: Mapped[str] = mapped_column(Text, default="")
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    success: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_audit_user_time", "user_id", "timestamp"),
        Index("ix_audit_action_time", "action", "timestamp"),
        Index("ix_audit_resource", "resource_type", "resource_id"),
    )


# -------------------------------------------------------------------
# Plans & Metering
# -------------------------------------------------------------------


class Plan(Base):
    """A subscription plan with flexible JSONB limits."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    limits: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON string
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class UserSubscription(Base):
    """Links a user to a plan with optional expiry."""

    __tablename__ = "user_subscriptions"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="subscriptions")
    plan: Mapped[Plan] = relationship()


class UsageRecord(Base):
    """Tracks individual usage events for metering."""

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), default="")
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_usage_user_date", "user_id", "created_at"),)


class Symbol(Base):
    """A code symbol (class, method, interface, etc.) extracted from static analysis."""

    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # class, method, etc.
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    fq_name: Mapped[str] = mapped_column(Text, nullable=False)  # fully qualified name
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    namespace: Mapped[str] = mapped_column(Text, default="")
    parent_fq_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature: Mapped[str] = mapped_column(Text, default="")
    modifiers: Mapped[str] = mapped_column(Text, default="")  # comma-separated
    return_type: Mapped[str] = mapped_column(String(256), default="")
    source_code: Mapped[str] = mapped_column(Text, default="", server_default="")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # extra info as JSON
    cyclomatic_complexity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cognitive_complexity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_author: Mapped[str] = mapped_column(String(256), default="", server_default="")
    last_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    author_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    commit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    authors_json: Mapped[str] = mapped_column(Text, default="", server_default="")

    __table_args__ = (
        Index("ix_symbols_snapshot_fq", "snapshot_id", "fq_name"),
        Index("ix_symbols_snapshot_kind", "snapshot_id", "kind"),
        Index("ix_symbols_snapshot_file", "snapshot_id", "file_path"),
    )


class Edge(Base):
    """A directed relationship between two symbols (call, inheritance, etc.)."""

    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    source_symbol_id: Mapped[int | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=True
    )
    target_symbol_id: Mapped[int | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=True
    )
    source_fq_name: Mapped[str] = mapped_column(Text, nullable=False)
    target_fq_name: Mapped[str] = mapped_column(Text, nullable=False)
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False)  # calls, inherits, etc.
    file_path: Mapped[str] = mapped_column(Text, default="")
    line: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_edges_snapshot_type", "snapshot_id", "edge_type"),
        Index("ix_edges_snapshot_source", "snapshot_id", "source_fq_name"),
        Index("ix_edges_snapshot_target", "snapshot_id", "target_fq_name"),
    )


class Summary(Base):
    """A structured summary (symbol, module, or file level) produced by the indexing pipeline."""

    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)  # symbol | module | file
    scope_id: Mapped[str] = mapped_column(Text, nullable=False)  # fq_name, module name, or path
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)  # full JSON payload
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_summaries_snapshot_scope", "snapshot_id", "scope_type"),
        Index("ix_summaries_snapshot_id_scope_id", "snapshot_id", "scope_id"),
    )


class Review(Base):
    """A PR review report produced by the review engine."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    diff_summary: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    report_json: Mapped[str] = mapped_column(Text, nullable=False)  # full JSON payload
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_reviews_snapshot", "snapshot_id"),)


class GeneratedDoc(Base):
    """An auto-generated documentation artifact."""

    __tablename__ = "generated_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # readme | architecture | module | flow | runbook
    scope_id: Mapped[str] = mapped_column(Text, default="")  # module name, entry fq_name, etc.
    title: Mapped[str] = mapped_column(Text, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    llm_narrative: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_generated_docs_snapshot", "snapshot_id"),
        Index(
            "ix_generated_docs_snapshot_type",
            "snapshot_id",
            "doc_type",
        ),
    )


class Evaluation(Base):
    """An evaluation / guardrails report for a snapshot or artifact."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(
        String(64), default="snapshot"
    )  # snapshot | answer | doc | review
    overall_score: Mapped[float] = mapped_column(default=0.0)
    overall_severity: Mapped[str] = mapped_column(String(16), default="pass")
    checks_json: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_evaluations_snapshot", "snapshot_id"),)


class Dependency(Base):
    """A declared dependency from a manifest file."""

    __tablename__ = "dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[str] = mapped_column(String(256), default="*")
    ecosystem: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    is_dev: Mapped[bool] = mapped_column(default=False)
    is_pinned: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index("ix_deps_snapshot", "snapshot_id"),
        Index("ix_deps_snapshot_eco", "snapshot_id", "ecosystem"),
    )


class LLMProvider(Base):
    """A configured LLM provider (Fanar, OpenAI, Ollama, etc.)."""

    __tablename__ = "llm_providers"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_enc: Mapped[str] = mapped_column(Text, default="")
    default_model: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    temperature: Mapped[float] = mapped_column(Float, default=0.1)
    timeout: Mapped[int] = mapped_column(Integer, default=60)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
