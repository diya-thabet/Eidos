"""
Coverage report parser.

Parses coverage.py JSON output (produced by `coverage json` or
`pytest --cov-report=json`) into a normalized structure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileCoverage:
    """Coverage stats for a single file."""

    path: str
    percent: float = 0.0
    covered_lines: int = 0
    missing_lines: int = 0
    num_statements: int = 0
    branch_percent: float = 0.0
    missing_line_numbers: list[int] = field(default_factory=list)


@dataclass
class CoverageData:
    """Parsed coverage data from coverage.json."""

    overall_percent: float = 0.0
    branch_percent: float = 0.0
    covered_lines: int = 0
    missing_lines: int = 0
    num_statements: int = 0
    num_branches: int = 0
    covered_branches: int = 0
    file_count: int = 0
    files: list[FileCoverage] = field(default_factory=list)
    format_version: str = ""
    timestamp: str = ""


def parse_coverage_json(data: dict[str, Any]) -> CoverageData:
    """Parse a coverage.py JSON dict into a CoverageData object.

    Expected input format (coverage.py JSON 2.x/3.x):
    {
        "meta": {"format": 3, "timestamp": "...", "branch_coverage": true},
        "totals": {
            "covered_lines": 546, "num_statements": 9611,
            "percent_covered": 5.11, "missing_lines": 9065,
            "num_branches": 3216, "covered_branches": 110,
            "percent_branches_covered": 3.42, ...
        },
        "files": {
            "path/to/file.py": {
                "summary": {...}, "missing_lines": [12, 15], ...
            }
        }
    }
    """
    if not isinstance(data, dict):
        raise ValueError("Coverage data must be a dict")

    meta = data.get("meta") or {}
    totals = data.get("totals") or {}
    files_dict = data.get("files") or {}

    if not totals and not files_dict:
        raise ValueError("Coverage data missing 'totals' and 'files'")

    result = CoverageData(
        overall_percent=round(float(totals.get("percent_covered", 0.0)), 2),
        branch_percent=round(
            float(totals.get("percent_branches_covered", 0.0)), 2,
        ),
        covered_lines=int(totals.get("covered_lines", 0)),
        missing_lines=int(totals.get("missing_lines", 0)),
        num_statements=int(totals.get("num_statements", 0)),
        num_branches=int(totals.get("num_branches", 0)),
        covered_branches=int(totals.get("covered_branches", 0)),
        file_count=len(files_dict),
        format_version=str(meta.get("format", "")),
        timestamp=str(meta.get("timestamp", "")),
    )

    for path, info in files_dict.items():
        if not isinstance(info, dict):
            continue
        summary = info.get("summary") or {}
        result.files.append(FileCoverage(
            path=_normalize_path(path),
            percent=round(float(summary.get("percent_covered", 0.0)), 2),
            covered_lines=int(summary.get("covered_lines", 0)),
            missing_lines=int(summary.get("missing_lines", 0)),
            num_statements=int(summary.get("num_statements", 0)),
            branch_percent=round(
                float(summary.get("percent_branches_covered", 0.0)), 2,
            ),
            missing_line_numbers=list(info.get("missing_lines") or []),
        ))

    # Sort files by lowest coverage first (most actionable)
    result.files.sort(key=lambda f: (f.percent, f.path))

    return result


def parse_coverage_text(text: str) -> CoverageData:
    """Parse coverage from a JSON string."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    return parse_coverage_json(data)


def _normalize_path(path: str) -> str:
    """Normalize a file path to forward slashes."""
    return path.replace("\\", "/")


def coverage_grade(percent: float) -> str:
    """Convert coverage percentage to a letter grade."""
    if percent >= 90:
        return "A"
    if percent >= 80:
        return "B"
    if percent >= 70:
        return "C"
    if percent >= 60:
        return "D"
    return "F"
