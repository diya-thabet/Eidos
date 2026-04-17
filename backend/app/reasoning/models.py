"""
Data models for the reasoning engine.

Defines the shape of questions, answers, evidence, and verification
checklists that flow through the Q&A pipeline.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class QuestionType(enum.StrEnum):
    """Category of question -- drives retrieval strategy."""

    ARCHITECTURE = "architecture"  # "How is the system structured?"
    FLOW = "flow"  # "What happens when X is called?"
    COMPONENT = "component"  # "What does class X do?"
    IMPACT = "impact"  # "What would break if I change X?"
    GENERAL = "general"  # Fallback


class Confidence(enum.StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Evidence:
    """A single piece of evidence backing an answer."""

    file_path: str
    symbol_fq_name: str = ""
    start_line: int = 0
    end_line: int = 0
    snippet: str = ""  # short code excerpt
    relevance: str = ""  # why this evidence matters


@dataclass
class VerificationItem:
    """A single item in the verification checklist."""

    description: str
    how_to_verify: str = ""


@dataclass
class Question:
    """A user question with routing metadata."""

    text: str
    snapshot_id: str
    question_type: QuestionType = QuestionType.GENERAL
    target_symbol: str = ""  # optional: focus on a specific symbol
    max_hops: int = 2  # graph expansion depth


@dataclass
class Answer:
    """Structured answer with evidence and verification checklist."""

    question: str
    question_type: str
    answer_text: str
    evidence: list[Evidence] = field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    verification: list[VerificationItem] = field(default_factory=list)
    related_symbols: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class RetrievalContext:
    """Bundle of retrieved information used to build an answer."""

    summaries: list[dict[str, Any]] = field(default_factory=list)
    symbols: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    code_snippets: list[dict[str, Any]] = field(default_factory=list)
    graph_neighborhood: list[str] = field(default_factory=list)
