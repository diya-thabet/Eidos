"""
Data models for the PR review engine.

Defines diffs, changed symbols, review findings, and the overall
review report structure.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Severity(enum.StrEnum):
    """How serious a finding is."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingCategory(enum.StrEnum):
    """Category of review finding -- focuses on behaviour, not style."""

    REMOVED_VALIDATION = "removed_validation"
    CHANGED_CONDITION = "changed_condition"
    REMOVED_ERROR_HANDLING = "removed_error_handling"
    NEW_SIDE_EFFECT = "new_side_effect"
    CHANGED_RETURN = "changed_return"
    CHANGED_SIGNATURE = "changed_signature"
    HIGH_FAN_IN_CHANGE = "high_fan_in_change"
    LARGE_METHOD_CHANGE = "large_method_change"
    REMOVED_NULL_CHECK = "removed_null_check"
    CONCURRENCY_RISK = "concurrency_risk"
    SECURITY_SENSITIVE = "security_sensitive"
    GENERAL_RISK = "general_risk"


@dataclass
class DiffLine:
    """A single line in a diff hunk."""

    number: int  # line number in the new file (0 = deleted line)
    old_number: int  # line number in the old file (0 = added line)
    content: str
    is_added: bool = False
    is_removed: bool = False


@dataclass
class DiffHunk:
    """A contiguous block of changes within a file."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    """All changes to a single file."""

    path: str
    old_path: str = ""  # different from path if renamed
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False
    hunks: list[DiffHunk] = field(default_factory=list)

    @property
    def added_lines(self) -> list[DiffLine]:
        return [ln for h in self.hunks for ln in h.lines if ln.is_added]

    @property
    def removed_lines(self) -> list[DiffLine]:
        return [ln for h in self.hunks for ln in h.lines if ln.is_removed]

    @property
    def changed_line_numbers(self) -> set[int]:
        """New-file line numbers that are added or modified."""
        return {ln.number for h in self.hunks for ln in h.lines if ln.is_added and ln.number > 0}


@dataclass
class ChangedSymbol:
    """A symbol that was affected by the diff."""

    fq_name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int
    change_type: str = "modified"  # modified | added | deleted
    lines_changed: int = 0


@dataclass
class ReviewFinding:
    """A single review finding with evidence."""

    category: FindingCategory
    severity: Severity
    title: str
    description: str
    file_path: str
    line: int = 0
    symbol_fq_name: str = ""
    evidence: str = ""  # short code excerpt or explanation
    suggestion: str = ""  # what the developer should check


@dataclass
class ImpactedSymbol:
    """A symbol affected indirectly via the call graph."""

    fq_name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int
    distance: int = 1  # hops from the changed symbol


@dataclass
class ReviewReport:
    """Complete PR review report."""

    snapshot_id: str
    diff_summary: str  # "X files changed, Y additions, Z deletions"
    files_changed: list[str]
    changed_symbols: list[ChangedSymbol] = field(default_factory=list)
    findings: list[ReviewFinding] = field(default_factory=list)
    impacted_symbols: list[ImpactedSymbol] = field(default_factory=list)
    risk_score: int = 0  # 0-100
    risk_level: str = "low"  # low / medium / high / critical
    llm_summary: str = ""  # optional LLM-generated summary
