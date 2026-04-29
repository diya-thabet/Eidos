"""
Git blame and churn analysis.

Extracts per-line authorship from git blame and aggregates it
per function/method symbol. Uses GitPython (already installed).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import git

logger = logging.getLogger(__name__)


@dataclass
class BlameInfo:
    """Aggregated blame data for one symbol."""

    last_author: str = ""
    last_modified_at: datetime | None = None
    author_count: int = 0
    commit_count: int = 0


@dataclass
class LineBlameLine:
    """Blame data for a single line."""

    line_no: int
    author: str
    committed_date: datetime
    commit_hex: str


@dataclass
class FileBlame:
    """Blame data for every line in a file."""

    path: str
    lines: list[LineBlameLine] = field(default_factory=list)


def extract_file_blame(
    repo: git.Repo, file_path: str,
) -> FileBlame | None:
    """Run git blame on a single file."""
    try:
        blame_data: Any = repo.blame("HEAD", file_path)
    except Exception:
        logger.debug("Blame failed for %s", file_path)
        return None

    result = FileBlame(path=file_path)
    line_no = 1

    for entry in blame_data:
        commit: Any = entry[0]
        lines_list: Any = entry[1]
        try:
            author = commit.author.name or commit.author.email or "unknown"
        except Exception:
            author = "unknown"
        try:
            cdate = datetime.fromtimestamp(
                commit.committed_date, tz=UTC,
            )
        except Exception:
            cdate = datetime(2000, 1, 1, tzinfo=UTC)

        for _line_text in lines_list:
            result.lines.append(LineBlameLine(
                line_no=line_no,
                author=str(author),
                committed_date=cdate,
                commit_hex=str(commit.hexsha)[:12],
            ))
            line_no += 1

    return result


def blame_for_range(
    file_blame: FileBlame,
    start_line: int,
    end_line: int,
) -> BlameInfo:
    """Aggregate blame data for a line range."""
    authors: set[str] = set()
    commits: set[str] = set()
    latest_date: datetime | None = None
    latest_author = ""

    for bl in file_blame.lines:
        if bl.line_no < start_line or bl.line_no > end_line:
            continue
        authors.add(bl.author)
        commits.add(bl.commit_hex)
        if latest_date is None or bl.committed_date > latest_date:
            latest_date = bl.committed_date
            latest_author = bl.author

    return BlameInfo(
        last_author=latest_author,
        last_modified_at=latest_date,
        author_count=len(authors),
        commit_count=len(commits),
    )


def extract_blame_for_snapshot(
    clone_path: Path,
    symbols: list[dict[str, Any]],
) -> dict[str, BlameInfo]:
    """Extract blame data for all symbols in a snapshot."""
    try:
        repo = git.Repo(clone_path)
    except Exception:
        logger.warning("Not a git repo: %s", clone_path)
        return {}

    file_symbols: dict[str, list[dict[str, Any]]] = {}
    for sym in symbols:
        fp = sym["file_path"]
        file_symbols.setdefault(fp, []).append(sym)

    result: dict[str, BlameInfo] = {}
    cache: dict[str, FileBlame | None] = {}

    for fp, syms in file_symbols.items():
        if fp not in cache:
            cache[fp] = extract_file_blame(repo, fp)
        fb = cache[fp]
        if fb is None:
            continue
        for sym in syms:
            info = blame_for_range(
                fb, sym["start_line"], sym["end_line"],
            )
            result[sym["fq_name"]] = info

    logger.info(
        "Blame extracted for %d symbols across %d files",
        len(result), len(cache),
    )
    return result
