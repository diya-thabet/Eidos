"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2025-07-01 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Reusable FK shorthand
_SNAP_FK = sa.ForeignKey("repo_snapshots.id", ondelete="CASCADE")
_USER_FK = sa.ForeignKey("users.id", ondelete="CASCADE")
_PLAN_FK = sa.ForeignKey("plans.id", ondelete="CASCADE")
_REPO_FK = sa.ForeignKey("repos.id", ondelete="CASCADE")
_USER_FK_SET_NULL = sa.ForeignKey("users.id", ondelete="SET NULL")


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("github_login", sa.String(128), unique=True, nullable=True),
        sa.Column("email", sa.String(256), unique=True, nullable=True),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("role", sa.String(32), server_default="user", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_role", "users", ["role"])

    # Repos
    op.create_table(
        "repos",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("owner_id", sa.String(64), _USER_FK_SET_NULL, nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column(
            "default_branch", sa.String(128), server_default="main", nullable=False
        ),
        sa.Column(
            "git_provider", sa.String(32), server_default="github", nullable=False
        ),
        sa.Column("git_token_enc", sa.Text, server_default="", nullable=False),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Snapshot status enum
    snapshot_status = sa.Enum(
        "pending", "running", "completed", "failed", name="snapshot_status"
    )
    snapshot_status.create(op.get_bind(), checkfirst=True)

    # Repo Snapshots
    op.create_table(
        "repo_snapshots",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("repo_id", sa.String(24), _REPO_FK, nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=True),
        sa.Column("status", snapshot_status, server_default="pending"),
        sa.Column("file_count", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("progress_percent", sa.Integer, server_default="0"),
        sa.Column("progress_message", sa.String(256), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Files
    op.create_table(
        "files",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(24), _SNAP_FK, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, server_default="0"),
    )
    op.create_index("ix_files_snapshot_path", "files", ["snapshot_id", "path"])

    # Plans
    op.create_table(
        "plans",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("limits", sa.Text, server_default="{}"),
    )

    # User Subscriptions
    op.create_table(
        "user_subscriptions",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("user_id", sa.String(64), _USER_FK, nullable=False),
        sa.Column("plan_id", sa.String(24), _PLAN_FK, nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscriptions_user", "user_subscriptions", ["user_id"])

    # Usage Records
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), _USER_FK, nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("tokens_used", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_usage_user_action", "usage_records", ["user_id", "action"]
    )

    # Symbols
    op.create_table(
        "symbols",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(24), _SNAP_FK, nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("fq_name", sa.Text, nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("start_line", sa.Integer, nullable=False),
        sa.Column("end_line", sa.Integer, nullable=False),
        sa.Column("namespace", sa.Text, server_default=""),
        sa.Column("parent_fq_name", sa.Text, nullable=True),
        sa.Column("signature", sa.Text, server_default=""),
        sa.Column("modifiers", sa.Text, server_default=""),
        sa.Column("return_type", sa.String(256), server_default=""),
    )
    op.create_index("ix_symbols_snapshot_kind", "symbols", ["snapshot_id", "kind"])
    op.create_index("ix_symbols_snapshot_fq", "symbols", ["snapshot_id", "fq_name"])
    op.create_index(
        "ix_symbols_snapshot_file", "symbols", ["snapshot_id", "file_path"]
    )

    # Edges
    op.create_table(
        "edges",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(24), _SNAP_FK, nullable=False),
        sa.Column("source_fq_name", sa.Text, nullable=False),
        sa.Column("target_fq_name", sa.Text, nullable=False),
        sa.Column("edge_type", sa.String(32), nullable=False),
        sa.Column("file_path", sa.Text, server_default=""),
        sa.Column("line", sa.Integer, nullable=True),
    )
    op.create_index(
        "ix_edges_snapshot_type", "edges", ["snapshot_id", "edge_type"]
    )
    op.create_index(
        "ix_edges_snapshot_source", "edges", ["snapshot_id", "source_fq_name"]
    )
    op.create_index(
        "ix_edges_snapshot_target", "edges", ["snapshot_id", "target_fq_name"]
    )

    # Summaries
    op.create_table(
        "summaries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(24), _SNAP_FK, nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.Text, nullable=False),
        sa.Column("summary_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_summaries_snapshot_scope", "summaries", ["snapshot_id", "scope_type"]
    )
    op.create_index(
        "ix_summaries_snapshot_id_scope_id", "summaries", ["snapshot_id", "scope_id"]
    )

    # Reviews
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(24), _SNAP_FK, nullable=False),
        sa.Column("diff_summary", sa.Text, nullable=False),
        sa.Column("risk_score", sa.Integer, server_default="0"),
        sa.Column("risk_level", sa.String(16), server_default="low"),
        sa.Column("report_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reviews_snapshot", "reviews", ["snapshot_id"])

    # Generated Docs
    op.create_table(
        "generated_docs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(24), _SNAP_FK, nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.Text, server_default=""),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("markdown", sa.Text, nullable=False),
        sa.Column("llm_narrative", sa.Text, server_default=""),
        sa.Column("metadata_json", sa.Text, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_generated_docs_snapshot", "generated_docs", ["snapshot_id"]
    )
    op.create_index(
        "ix_generated_docs_snapshot_type",
        "generated_docs",
        ["snapshot_id", "doc_type"],
    )

    # Evaluations
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(24), _SNAP_FK, nullable=False),
        sa.Column("scope", sa.String(64), server_default="snapshot"),
        sa.Column("overall_score", sa.Float, server_default="0.0"),
        sa.Column("overall_severity", sa.String(16), server_default="pass"),
        sa.Column("checks_json", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluations_snapshot", "evaluations", ["snapshot_id"])


def downgrade() -> None:
    op.drop_table("evaluations")
    op.drop_table("generated_docs")
    op.drop_table("reviews")
    op.drop_table("summaries")
    op.drop_table("edges")
    op.drop_table("symbols")
    op.drop_table("usage_records")
    op.drop_table("user_subscriptions")
    op.drop_table("plans")
    op.drop_table("files")
    op.drop_table("repo_snapshots")
    sa.Enum(name="snapshot_status").drop(op.get_bind(), checkfirst=True)
    op.drop_table("repos")
    op.drop_table("users")
