"""
Hallucination detector.

Verifies that LLM-generated text only references symbols, files,
and relationships that actually exist in the code graph.
"""

from __future__ import annotations

import re

from app.guardrails.models import EvalCategory, EvalCheck, EvalSeverity


def check_hallucinated_symbols(
    text: str,
    known_symbols: set[str],
    known_files: set[str],
) -> EvalCheck:
    """
    Check whether text references symbols or files that don't exist.

    Extracts backtick-quoted identifiers and dotted names from the text,
    then verifies each against the known sets.
    """
    referenced = _extract_references(text)

    if not referenced:
        return EvalCheck(
            category=EvalCategory.HALLUCINATION,
            name="hallucinated_symbols",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No symbol/file references found in text.",
        )

    hallucinated: list[str] = []
    for ref in referenced:
        if ref not in known_symbols and ref not in known_files:
            # Also check partial match (substring in known symbols/files)
            combined = known_symbols | known_files
            if not any(ref in s or s in ref for s in combined):
                hallucinated.append(ref)

    if not hallucinated:
        return EvalCheck(
            category=EvalCategory.HALLUCINATION,
            name="hallucinated_symbols",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message=f"All {len(referenced)} references verified.",
        )

    ratio = len(hallucinated) / len(referenced)
    score = max(0.0, 1.0 - ratio)
    severity = EvalSeverity.FAIL if ratio > 0.3 else EvalSeverity.WARNING

    return EvalCheck(
        category=EvalCategory.HALLUCINATION,
        name="hallucinated_symbols",
        passed=False,
        severity=severity,
        score=score,
        message=(f"{len(hallucinated)}/{len(referenced)} references not found in codebase."),
        details={
            "hallucinated": hallucinated[:10],
            "total_references": len(referenced),
        },
    )


def check_hallucinated_relationships(
    text: str,
    known_edges: set[tuple[str, str]],
) -> EvalCheck:
    """
    Check whether text claims relationships (X calls Y, X inherits Y)
    that don't exist in the edge set.
    """
    claimed = _extract_relationships(text)

    if not claimed:
        return EvalCheck(
            category=EvalCategory.HALLUCINATION,
            name="hallucinated_relationships",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No relationship claims found in text.",
        )

    false_claims: list[tuple[str, str]] = []
    for src, tgt in claimed:
        if (src, tgt) not in known_edges:
            false_claims.append((src, tgt))

    if not false_claims:
        return EvalCheck(
            category=EvalCategory.HALLUCINATION,
            name="hallucinated_relationships",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message=f"All {len(claimed)} relationship claims verified.",
        )

    ratio = len(false_claims) / len(claimed)
    score = max(0.0, 1.0 - ratio)

    return EvalCheck(
        category=EvalCategory.HALLUCINATION,
        name="hallucinated_relationships",
        passed=False,
        severity=EvalSeverity.WARNING,
        score=score,
        message=(
            f"{len(false_claims)}/{len(claimed)} relationship claims not found in code graph."
        ),
        details={
            "false_claims": [{"source": s, "target": t} for s, t in false_claims[:10]],
        },
    )


# -------------------------------------------------------------------
# Extraction helpers
# -------------------------------------------------------------------

_BACKTICK_RE = re.compile(r"`([A-Za-z_][\w.]*)`")
_DOTTED_RE = re.compile(r"\b([A-Z][a-zA-Z0-9]*(?:\.[A-Z][a-zA-Z0-9]*)+)\b")
_CALLS_RE = re.compile(
    r"`?([A-Za-z_][\w.]*)`?\s+"
    r"(?:calls|invokes|delegates to|sends to)\s+"
    r"`?([A-Za-z_][\w.]*)`?",
    re.IGNORECASE,
)
_INHERITS_RE = re.compile(
    r"`?([A-Za-z_][\w.]*)`?\s+"
    r"(?:inherits|extends|implements)\s+"
    r"`?([A-Za-z_][\w.]*)`?",
    re.IGNORECASE,
)


def _extract_references(text: str) -> set[str]:
    """Extract all symbol/file references from text."""
    refs: set[str] = set()
    refs.update(_BACKTICK_RE.findall(text))
    refs.update(_DOTTED_RE.findall(text))
    # Filter out very short or common words
    return {r for r in refs if len(r) > 2 and r not in _COMMON_WORDS}


def _extract_relationships(text: str) -> list[tuple[str, str]]:
    """Extract claimed relationships from text."""
    rels: list[tuple[str, str]] = []
    for pattern in (_CALLS_RE, _INHERITS_RE):
        for match in pattern.finditer(text):
            rels.append((match.group(1), match.group(2)))
    return rels


_COMMON_WORDS = {
    "The",
    "This",
    "That",
    "Not",
    "None",
    "True",
    "False",
    "Any",
    "All",
    "Type",
    "List",
    "Dict",
    "Set",
    "Int",
    "String",
    "Boolean",
}
