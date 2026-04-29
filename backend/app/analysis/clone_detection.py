"""
Duplicate / clone detection via AST structural fingerprinting.

For each function, computes a structural hash by walking the tree-sitter
AST and recording node types only (ignoring identifiers and literals).
Functions with identical structural hashes are exact clones.
Functions sharing >60% of statement-level windows are near-clones.

Uses ONLY tree-sitter (already installed). No external dependencies.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from tree_sitter import Node

logger = logging.getLogger(__name__)


@dataclass
class CloneInfo:
    """Clone metadata for a single function."""

    fq_name: str
    name: str
    file_path: str
    start_line: int
    end_line: int
    lines: int
    fingerprint: str  # structural hash


@dataclass
class CloneGroup:
    """A group of functions with the same structural fingerprint."""

    fingerprint: str
    members: list[CloneInfo] = field(default_factory=list)


@dataclass
class NearClonePair:
    """Two functions that share >threshold of structural windows."""

    a: CloneInfo
    b: CloneInfo
    similarity: float  # 0.0 to 1.0


@dataclass
class CloneReport:
    """Complete clone detection result."""

    total_functions: int = 0
    exact_clone_groups: list[CloneGroup] = field(default_factory=list)
    near_clone_pairs: list[NearClonePair] = field(default_factory=list)
    total_exact_clones: int = 0
    total_near_clones: int = 0


# -----------------------------------------------------------------------
# Structural fingerprinting
# -----------------------------------------------------------------------

# Node types to SKIP (they carry semantic content, not structure)
_SKIP_TYPES = frozenset({
    "identifier", "type_identifier", "field_identifier",
    "property_identifier", "shorthand_property_identifier",
    "string", "string_literal", "template_string",
    "number", "integer", "float", "true", "false", "none", "null",
    "comment", "line_comment", "block_comment", "doc_comment",
    "escape_sequence",
})

# Minimum function size (lines) to consider for clone detection
MIN_FUNC_LINES = 5

# Sliding window size for near-clone detection
WINDOW_SIZE = 5

# Similarity threshold for near-clone pairs
NEAR_CLONE_THRESHOLD = 0.6


def structural_fingerprint(node: Node) -> str:
    """
    Compute a structural hash of an AST subtree.

    Walks the tree recording only node types, ignoring identifiers
    and literals. Two functions with identical structure but different
    names/values will produce the same hash.
    """
    parts: list[str] = []
    _collect_structure(node, parts)
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def _collect_structure(node: Node, parts: list[str]) -> None:
    """Recursively collect structural node types."""
    if node.type in _SKIP_TYPES:
        return
    if not node.is_named:
        return
    parts.append(node.type)
    for child in node.children:
        _collect_structure(child, parts)


def statement_windows(node: Node, window_size: int = WINDOW_SIZE) -> list[str]:
    """
    Extract sliding windows of statement-level structural hashes.

    Each window covers `window_size` consecutive top-level statements
    inside the function body. Returns a list of hashes.
    """
    # Find the body/block child
    body = _find_body(node)
    if body is None:
        return []

    # Collect top-level statement types
    stmts: list[str] = []
    for child in body.children:
        if child.is_named and child.type not in _SKIP_TYPES:
            parts: list[str] = []
            _collect_structure(child, parts)
            stmts.append(hashlib.md5(  # noqa: S324
                "|".join(parts).encode(),
            ).hexdigest()[:8])

    if len(stmts) < window_size:
        # If fewer statements than window, hash them all as one window
        if stmts:
            return [hashlib.md5(  # noqa: S324
                "".join(stmts).encode(),
            ).hexdigest()[:8]]
        return []

    windows: list[str] = []
    for i in range(len(stmts) - window_size + 1):
        chunk = "".join(stmts[i : i + window_size])
        windows.append(hashlib.md5(chunk.encode()).hexdigest()[:8])  # noqa: S324
    return windows


def _find_body(node: Node) -> Node | None:
    """Find the body/block child of a function node."""
    for child in node.children:
        if child.type in (
            "block", "statement_block", "function_body",
            "method_body", "compound_statement",
        ):
            return child
    # Fallback: return the node itself if it has named children
    if node.named_child_count > 0:
        return node
    return None


def compute_similarity(windows_a: list[str], windows_b: list[str]) -> float:
    """Jaccard similarity of two window sets."""
    if not windows_a or not windows_b:
        return 0.0
    set_a = set(windows_a)
    set_b = set(windows_b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return intersection / union


def detect_clones(
    functions: list[CloneInfo],
    windows_map: dict[str, list[str]] | None = None,
) -> CloneReport:
    """
    Detect exact and near clones from a list of functions.

    Args:
        functions: List of CloneInfo with fingerprints computed.
        windows_map: Optional mapping of fq_name -> statement windows
                     for near-clone detection.

    Returns:
        CloneReport with exact and near clone groups.
    """
    report = CloneReport(total_functions=len(functions))

    # --- Exact clones ---
    groups: dict[str, list[CloneInfo]] = {}
    for func in functions:
        groups.setdefault(func.fingerprint, []).append(func)

    for fp, members in groups.items():
        if len(members) >= 2:
            report.exact_clone_groups.append(
                CloneGroup(fingerprint=fp, members=members),
            )
            report.total_exact_clones += len(members)

    # --- Near clones ---
    if windows_map:
        # Only check functions that are NOT already exact clones
        exact_fqs = set()
        for grp in report.exact_clone_groups:
            for m in grp.members:
                exact_fqs.add(m.fq_name)

        candidates = [
            f for f in functions
            if f.fq_name not in exact_fqs and f.fq_name in windows_map
        ]

        # O(n^2) but only on non-exact-clone functions with windows
        seen: set[tuple[str, str]] = set()
        for i, a in enumerate(candidates):
            for b in candidates[i + 1 :]:
                key = (min(a.fq_name, b.fq_name), max(a.fq_name, b.fq_name))
                if key in seen:
                    continue
                sim = compute_similarity(
                    windows_map[a.fq_name],
                    windows_map[b.fq_name],
                )
                if sim >= NEAR_CLONE_THRESHOLD:
                    seen.add(key)
                    report.near_clone_pairs.append(
                        NearClonePair(a=a, b=b, similarity=round(sim, 3)),
                    )
                    report.total_near_clones += 1

    return report
