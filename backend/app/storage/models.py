from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SnapshotStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), default="main")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    snapshots: Mapped[list[RepoSnapshot]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )


class RepoSnapshot(Base):
    __tablename__ = "repo_snapshots"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[SnapshotStatus] = mapped_column(
        Enum(SnapshotStatus, name="snapshot_status"), default=SnapshotStatus.pending
    )
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # extra info as JSON

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
