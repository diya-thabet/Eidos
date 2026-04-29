"""
Unified diff parser.

Parses standard unified diff format (as produced by ``git diff``)
into structured ``FileDiff`` / ``DiffHunk`` objects, and maps
changed lines back to code symbols.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.reviews.models import DiffHunk, DiffLine, FileDiff

logger = logging.getLogger(__name__)

# Regex patterns for unified diff
_DIFF_HEADER = re.compile(r"^diff --git a/(.+) b/(.+)$")
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_NEW_FILE = re.compile(r"^new file mode")
_DELETED_FILE = re.compile(r"^deleted file mode")
_RENAME_FROM = re.compile(r"^rename from (.+)")
_RENAME_TO = re.compile(r"^rename to (.+)")
_SIMILARITY = re.compile(r"^similarity index")


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    """
    Parse a unified diff string into a list of ``FileDiff`` objects.

    Handles standard modifications, new/deleted/renamed files,
    multiple hunks per file, and binary files (skipped).
    """
    files: list[FileDiff] = []
    current_file: FileDiff | None = None
    current_hunk: DiffHunk | None = None
    old_line = 0
    new_line = 0

    for raw_line in diff_text.splitlines():
        # New file diff header
        header_match = _DIFF_HEADER.match(raw_line)
        if header_match:
            current_file, current_hunk = _finalize_file(
                files, current_file, current_hunk,
            )
            current_file = FileDiff(
                path=header_match.group(2),
                old_path=header_match.group(1),
            )
            current_hunk = None
            continue

        if current_file is None:
            continue

        # Metadata lines
        if _handle_metadata(raw_line, current_file):
            continue

        # Skip index, ---, +++ lines
        if _is_skip_line(raw_line):
            continue

        # Hunk header
        hunk_match = _HUNK_HEADER.match(raw_line)
        if hunk_match:
            if current_hunk is not None:
                current_file.hunks.append(current_hunk)
            current_hunk, old_line, new_line = _parse_hunk_header(hunk_match)
            continue

        # Diff content lines
        if current_hunk is None:
            continue
        old_line, new_line = _parse_content_line(
            raw_line, current_hunk, old_line, new_line,
        )

    # Finalize last file
    _finalize_file(files, current_file, current_hunk)

    logger.info("Parsed diff: %d files", len(files))
    return files


def _finalize_file(
    files: list[FileDiff],
    current_file: FileDiff | None,
    current_hunk: DiffHunk | None,
) -> tuple[FileDiff | None, DiffHunk | None]:
    """Append current file/hunk to results and reset."""
    if current_file is not None:
        if current_hunk is not None:
            current_file.hunks.append(current_hunk)
        files.append(current_file)
    return None, None


def _handle_metadata(raw_line: str, current_file: FileDiff) -> bool:
    """Handle metadata lines (new/deleted/renamed). Returns True if handled."""
    if _NEW_FILE.match(raw_line):
        current_file.is_new = True
        return True
    if _DELETED_FILE.match(raw_line):
        current_file.is_deleted = True
        return True
    if _RENAME_FROM.match(raw_line):
        current_file.is_renamed = True
        m = _RENAME_FROM.match(raw_line)
        if m:
            current_file.old_path = m.group(1)
        return True
    if _RENAME_TO.match(raw_line):
        current_file.is_renamed = True
        m = _RENAME_TO.match(raw_line)
        if m:
            current_file.path = m.group(1)
        return True
    if _SIMILARITY.match(raw_line):
        return True
    return False


def _is_skip_line(raw_line: str) -> bool:
    """Check if line should be skipped (index, ---, +++)."""
    return (
        raw_line.startswith("index ")
        or raw_line.startswith("---")
        or raw_line.startswith("+++")
    )


def _parse_hunk_header(match: re.Match) -> tuple[DiffHunk, int, int]:  # type: ignore[type-arg]
    """Parse @@ hunk header and return (hunk, old_line, new_line)."""
    old_start = int(match.group(1))
    old_count = int(match.group(2) or "1")
    new_start = int(match.group(3))
    new_count = int(match.group(4) or "1")
    hunk = DiffHunk(
        old_start=old_start, old_count=old_count,
        new_start=new_start, new_count=new_count,
    )
    return hunk, old_start, new_start


def _parse_content_line(
    raw_line: str, hunk: DiffHunk, old_line: int, new_line: int,
) -> tuple[int, int]:
    """Parse a +/-/space content line and return updated line numbers."""
    if raw_line.startswith("+"):
        hunk.lines.append(DiffLine(
            number=new_line, old_number=0,
            content=raw_line[1:], is_added=True,
        ))
        new_line += 1
    elif raw_line.startswith("-"):
        hunk.lines.append(DiffLine(
            number=0, old_number=old_line,
            content=raw_line[1:], is_removed=True,
        ))
        old_line += 1
    elif raw_line.startswith(" "):
        hunk.lines.append(DiffLine(
            number=new_line, old_number=old_line,
            content=raw_line[1:],
        ))
        old_line += 1
        new_line += 1
    return old_line, new_line


def map_lines_to_symbols(
    file_diff: FileDiff,
    symbols: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Map changed lines in a file diff to symbols that overlap those lines.

    Args:
        file_diff: The parsed diff for one file.
        symbols: List of symbol dicts with start_line, end_line, fq_name, kind.

    Returns:
        List of symbol dicts that overlap with changed lines, augmented
        with ``lines_changed`` count and ``change_type``.
    """
    changed_lines = file_diff.changed_line_numbers
    removed_line_numbers = {ln.old_number for ln in file_diff.removed_lines if ln.old_number > 0}

    matched: list[dict[str, Any]] = []
    seen: set[str] = set()

    for sym in symbols:
        fq = sym.get("fq_name", "")
        if fq in seen:
            continue

        start = sym.get("start_line", 0)
        end = sym.get("end_line", 0)
        sym_range = set(range(start, end + 1))

        overlap_added = len(changed_lines & sym_range)
        overlap_removed = len(removed_line_numbers & sym_range)
        total_overlap = overlap_added + overlap_removed

        if total_overlap > 0:
            seen.add(fq)

            if file_diff.is_new:
                change_type = "added"
            elif file_diff.is_deleted:
                change_type = "deleted"
            else:
                change_type = "modified"

            matched.append(
                {
                    **sym,
                    "lines_changed": total_overlap,
                    "change_type": change_type,
                }
            )

    return matched
