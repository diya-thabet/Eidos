from __future__ import annotations

from typing import Any

from pydantic import BaseModel, HttpUrl, field_validator

from app.storage.models import SnapshotStatus

# Blocked hosts that should never appear in repo URLs
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]", "metadata.google.internal"}
_VALID_PROVIDERS = {"github", "gitlab", "azure_devops", "bitbucket", "other"}


class RepoCreate(BaseModel):
    name: str
    url: HttpUrl
    default_branch: str = "main"
    git_provider: str = "github"  # github | gitlab | azure_devops | bitbucket | other
    git_token: str = ""  # PAT for private repos (stored encrypted, never returned)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Repository name must not be empty")
        if len(v) > 256:
            raise ValueError("Repository name must be 256 characters or fewer")
        return v

    @field_validator("url")
    @classmethod
    def url_must_be_safe(cls, v: HttpUrl) -> HttpUrl:
        host = str(v.host or "").lower()
        if host in _BLOCKED_HOSTS:
            raise ValueError(f"URL host '{host}' is not allowed")
        scheme = str(v.scheme).lower()
        if scheme not in ("http", "https"):
            raise ValueError("Only http/https URLs are allowed")
        return v

    @field_validator("default_branch")
    @classmethod
    def branch_safe(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Branch must not be empty")
        if ".." in v or v.startswith("/"):
            raise ValueError("Invalid branch name")
        if len(v) > 128:
            raise ValueError("Branch name too long")
        return v

    @field_validator("git_provider")
    @classmethod
    def provider_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _VALID_PROVIDERS:
            raise ValueError(f"git_provider must be one of: {', '.join(sorted(_VALID_PROVIDERS))}")
        return v

    @field_validator("git_token")
    @classmethod
    def token_length(cls, v: str) -> str:
        if len(v) > 1024:
            raise ValueError("Git token too long (max 1024)")
        return v


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


# ---------------------------------------------------------------------------
# Evaluation schemas (Phase 7)
# ---------------------------------------------------------------------------


class EvalCheckOut(BaseModel):
    """A single evaluation check result."""

    category: str
    name: str
    passed: bool
    severity: str
    score: float
    message: str
    details: dict[str, Any] = {}


class EvalReportOut(BaseModel):
    """Complete evaluation report."""

    id: int | None = None
    snapshot_id: str
    scope: str
    overall_score: float
    overall_severity: str
    checks: list[EvalCheckOut]
    summary: str
