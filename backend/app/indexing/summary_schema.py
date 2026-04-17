"""
Data models for structured summaries.

These schemas define the shape of every summary produced by the indexing
pipeline.  They are JSON-serialisable so they can be stored in the DB,
embedded in a vector store, and returned by the API verbatim.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class ScopeType(enum.StrEnum):
    """What level of code the summary describes."""

    SYMBOL = "symbol"
    MODULE = "module"
    FILE = "file"
    FLOW = "flow"


class Confidence(enum.StrEnum):
    """How confident we are in the summary."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Citation:
    """Pointer back to a specific location in the source code."""

    file_path: str
    symbol_fq_name: str = ""
    start_line: int = 0
    end_line: int = 0


@dataclass
class SymbolSummary:
    """Structured summary for a single code symbol (method, class, etc.)."""

    fq_name: str
    kind: str
    purpose: str  # one-sentence description
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    confidence: Confidence = Confidence.HIGH


@dataclass
class ModuleSummary:
    """Structured summary for a namespace / module."""

    name: str
    purpose: str
    responsibilities: list[str] = field(default_factory=list)
    key_classes: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    confidence: Confidence = Confidence.HIGH


@dataclass
class FileSummary:
    """Structured summary for a single source file."""

    path: str
    purpose: str
    symbols: list[str] = field(default_factory=list)  # fq_names declared here
    namespace: str = ""
    imports: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    confidence: Confidence = Confidence.HIGH
