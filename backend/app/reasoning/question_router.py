"""
Question router.

Classifies user questions into types and determines the optimal
retrieval strategy for each type.
"""

from __future__ import annotations

import logging
import re

from app.reasoning.models import Question, QuestionType

logger = logging.getLogger(__name__)

# Keyword patterns for question classification
_PATTERNS: list[tuple[QuestionType, list[str]]] = [
    (
        QuestionType.ARCHITECTURE,
        [
            r"\barchitect",
            r"\bstructur",
            r"\borganiz",
            r"\blayer",
            r"\bmodul",
            r"\bnamespace",
            r"\boverall",
            r"\bhigh.?level",
            r"\bdesign",
        ],
    ),
    (
        QuestionType.FLOW,
        [
            r"\bflow\b",
            r"\bwhat happens",
            r"\bcall chain",
            r"\bsequence",
            r"\bwhen .* (call|invok|trigger|click|submit)",
            r"\bstep.?by.?step",
            r"\bexecut",
            r"\bpipeline",
            r"\bprocess\b",
            r"\bdata flow",
        ],
    ),
    (
        QuestionType.IMPACT,
        [
            r"\bimpact",
            r"\bbreak",
            r"\baffect",
            r"\bdepend",
            r"\bchange.*what",
            r"\bwhat.*change",
            r"\bregress",
            r"\bblast.?radius",
            r"\bripple",
            r"\bside.?effect",
        ],
    ),
    (
        QuestionType.COMPONENT,
        [
            r"\bclass\b",
            r"\bmethod\b",
            r"\bfunction\b",
            r"\binterface\b",
            r"\bservice\b",
            r"\bcontroller\b",
            r"\bwhat does .* do",
            r"\bexplain\b",
            r"\bdescribe\b",
            r"\bpurpose of",
            r"\brole of",
        ],
    ),
]


def classify_question(text: str) -> QuestionType:
    """
    Classify a question into a QuestionType based on keyword patterns.

    Falls back to GENERAL if no pattern matches.
    """
    lower = text.lower()
    scores: dict[QuestionType, int] = {}
    for qtype, patterns in _PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lower):
                scores[qtype] = scores.get(qtype, 0) + 1
    if not scores:
        return QuestionType.GENERAL
    return max(scores, key=lambda k: scores[k])


def extract_target_symbol(text: str) -> str:
    """
    Attempt to extract a symbol name (fully qualified or simple) from the
    question text.

    Looks for patterns like:
    - backtick-quoted names: `MyApp.Services.UserService`
    - PascalCase identifiers: UserService, GetById
    - dotted identifiers: MyApp.Services.UserService
    """
    # Backtick-quoted
    backtick = re.findall(r"`([A-Za-z_][\w.]*)`", text)
    if backtick:
        return backtick[0]

    # Dotted identifier (at least two parts)
    dotted = re.findall(r"\b([A-Z][a-zA-Z0-9]*(?:\.[A-Z][a-zA-Z0-9]*)+)\b", text)
    if dotted:
        # Return the longest match
        return max(dotted, key=len)

    # PascalCase (at least 2 capital letters)
    pascal = re.findall(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b", text)
    if pascal:
        return pascal[0]

    return ""


def build_question(text: str, snapshot_id: str) -> Question:
    """
    Parse user text into a structured Question with classification
    and optional target symbol.
    """
    qtype = classify_question(text)
    target = extract_target_symbol(text)

    # Adjust graph expansion depth based on question type
    max_hops = 2
    if qtype == QuestionType.IMPACT:
        max_hops = 3
    elif qtype == QuestionType.ARCHITECTURE:
        max_hops = 1

    return Question(
        text=text,
        snapshot_id=snapshot_id,
        question_type=qtype,
        target_symbol=target,
        max_hops=max_hops,
    )
