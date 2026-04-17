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

    Handles:
    - Standard file modifications
    - New files
    - Deleted files
    - Renamed files
    - Multiple hunks per file
    - Binary files (skipped)
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
            if current_file is not None:
                if current_hunk is not None:
                    current_file.hunks.append(current_hunk)
                files.append(current_file)

            old_path = header_match.group(1)
            new_path = header_match.group(2)
            current_file = FileDiff(path=new_path, old_path=old_path)
            current_hunk = None
            continue

        if current_file is None:
            continue

        # Metadata lines
        if _NEW_FILE.match(raw_line):
            current_file.is_new = True
            continue
        if _DELETED_FILE.match(raw_line):
            current_file.is_deleted = True
            continue
        if _RENAME_FROM.match(raw_line):
            current_file.is_renamed = True
            m = _RENAME_FROM.match(raw_line)
            if m:
                current_file.old_path = m.group(1)
            continue
        if _RENAME_TO.match(raw_line):
            current_file.is_renamed = True
            m = _RENAME_TO.match(raw_line)
            if m:
                current_file.path = m.group(1)
            continue
        if _SIMILARITY.match(raw_line):
            continue

        # Skip index, ---, +++ lines
        if (
            raw_line.startswith("index ")
            or raw_line.startswith("---")
            or raw_line.startswith("+++")
        ):
            continue

        # Hunk header
        hunk_match = _HUNK_HEADER.match(raw_line)
        if hunk_match:
            if current_hunk is not None:
                current_file.hunks.append(current_hunk)

            old_start = int(hunk_match.group(1))
            old_count = int(hunk_match.group(2) or "1")
            new_start = int(hunk_match.group(3))
            new_count = int(hunk_match.group(4) or "1")

            current_hunk = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
            )
            old_line = old_start
            new_line = new_start
            continue

        # Diff content lines
        if current_hunk is None:
            continue

        if raw_line.startswith("+"):
            current_hunk.lines.append(
                DiffLine(
                    number=new_line,
                    old_number=0,
                    content=raw_line[1:],
                    is_added=True,
                )
            )
            new_line += 1
        elif raw_line.startswith("-"):
            current_hunk.lines.append(
                DiffLine(
                    number=0,
                    old_number=old_line,
                    content=raw_line[1:],
                    is_removed=True,
                )
            )
            old_line += 1
        elif raw_line.startswith(" "):
            current_hunk.lines.append(
                DiffLine(
                    number=new_line,
                    old_number=old_line,
                    content=raw_line[1:],
                )
            )
            old_line += 1
            new_line += 1
        elif raw_line.startswith("\\"):
            # "\ No newline at end of file"
            continue

    # Finalize last file
    if current_file is not None:
        if current_hunk is not None:
            current_file.hunks.append(current_hunk)
        files.append(current_file)

    logger.info("Parsed diff: %d files", len(files))
    return files


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
