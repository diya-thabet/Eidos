from __future__ import annotations

from typing import Any

from pydantic import BaseModel, HttpUrl

from app.storage.models import SnapshotStatus


class RepoCreate(BaseModel):
    name: str
    url: HttpUrl
    default_branch: str = "main"


class RepoOut(BaseModel):
    id: str
    name: str
    url: str
    default_branch: str
    created_at: str
    last_indexed_at: str | None = None

    model_config = {"from_attributes": True}


class IngestRequest(BaseModel):
    commit_sha: str | None = None


class SnapshotOut(BaseModel):
    id: str
    repo_id: str
    commit_sha: str | None
    status: SnapshotStatus
    file_count: int
    error_message: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


class IngestOut(BaseModel):
    snapshot_id: str
    status: SnapshotStatus


class RepoStatus(BaseModel):
    repo_id: str
    name: str
    snapshots: list[SnapshotOut]


class FileOut(BaseModel):
    id: int
    path: str
    language: str | None
    hash: str
    size_bytes: int

    model_config = {"from_attributes": True}


class SnapshotDetail(BaseModel):
    id: str
    repo_id: str
    commit_sha: str | None
    status: SnapshotStatus
    file_count: int
    created_at: str
    files: list[FileOut]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Analysis schemas (Phase 2)
# ---------------------------------------------------------------------------


class SymbolOut(BaseModel):
    """A code symbol returned by the analysis API."""

    id: int
    kind: str
    name: str
    fq_name: str
    file_path: str
    start_line: int
    end_line: int
    namespace: str = ""
    parent_fq_name: str | None = None
    signature: str = ""
    modifiers: str = ""
    return_type: str = ""

    model_config = {"from_attributes": True}


class EdgeOut(BaseModel):
    """A directed relationship between symbols."""

    id: int
    source_fq_name: str
    target_fq_name: str
    edge_type: str
    file_path: str = ""
    line: int = 0

    model_config = {"from_attributes": True}


class GraphNeighborhood(BaseModel):
    """Callers and callees for a symbol."""

    symbol: SymbolOut
    callers: list[SymbolOut]
    callees: list[SymbolOut]
    children: list[SymbolOut]


class EntryPointOut(BaseModel):
    """An identified entry point."""

    symbol_fq_name: str
    kind: str
    file_path: str
    line: int
    route: str = ""


class MetricsOut(BaseModel):
    """Computed metrics for a symbol."""

    fq_name: str
    kind: str
    lines_of_code: int
    fan_in: int
    fan_out: int
    child_count: int
    is_public: bool
    is_static: bool


class ModuleOut(BaseModel):
    """A namespace-based module."""

    name: str
    file_count: int
    symbol_count: int
    files: list[str]
    dependencies: list[str]


class AnalysisOverview(BaseModel):
    """High-level analysis summary for a snapshot."""

    snapshot_id: str
    total_symbols: int
    total_edges: int
    total_modules: int
    symbols_by_kind: dict[str, int]
    entry_points: list[EntryPointOut]
    hotspots: list[MetricsOut]


# ---------------------------------------------------------------------------
# Indexing schemas (Phase 3)
# ---------------------------------------------------------------------------


class CitationOut(BaseModel):
    """A citation pointing back to source code."""

    file_path: str
    symbol_fq_name: str = ""
    start_line: int = 0
    end_line: int = 0


class SummaryOut(BaseModel):
    """A persisted summary record."""

    id: int
    snapshot_id: str
    scope_type: str
    scope_id: str
    summary: dict[str, Any]  # parsed JSON payload
    created_at: str

    model_config = {"from_attributes": True}


class IndexingStats(BaseModel):
    """Statistics from an indexing run."""

    symbol_summaries: int
    module_summaries: int
    file_summaries: int
    vectors_stored: int


class SearchResultOut(BaseModel):
    """A vector search result."""

    scope_type: str
    text: str
    score: float
    refs: list[dict[str, Any]]
    metadata: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Review schemas (Phase 5)
# ---------------------------------------------------------------------------


class ReviewRequest(BaseModel):
    """Request body for PR review."""

    diff: str
    max_hops: int = 3


class ChangedSymbolOut(BaseModel):
    fq_name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int
    change_type: str = "modified"
    lines_changed: int = 0


class ReviewFindingOut(BaseModel):
    category: str
    severity: str
    title: str
    description: str
    file_path: str
    line: int = 0
    symbol_fq_name: str = ""
    evidence: str = ""
    suggestion: str = ""


class ImpactedSymbolOut(BaseModel):
    fq_name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int
    distance: int = 1


class ReviewReportOut(BaseModel):
    """Full review report response."""

    id: int | None = None
    snapshot_id: str
    diff_summary: str
    files_changed: list[str]
    changed_symbols: list[ChangedSymbolOut]
    findings: list[ReviewFindingOut]
    impacted_symbols: list[ImpactedSymbolOut]
    risk_score: int
    risk_level: str
    llm_summary: str = ""


# ---------------------------------------------------------------------------
# Documentation schemas (Phase 6)
# ---------------------------------------------------------------------------


class GenerateDocsRequest(BaseModel):
    """Request body for doc generation."""

    doc_type: str | None = None  # None = generate all
    scope_id: str = ""


class GeneratedDocOut(BaseModel):
    """A single generated document."""

    id: int | None = None
    doc_type: str
    title: str
    scope_id: str = ""
    markdown: str
    llm_narrative: str = ""


class GenerateDocsResponse(BaseModel):
    """Response from doc generation."""

    snapshot_id: str
    documents: list[GeneratedDocOut]
    total: int
