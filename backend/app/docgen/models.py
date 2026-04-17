"""
Data models for the documentation generation engine.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class DocType(enum.StrEnum):
    """Kind of generated document."""

    README = "readme"
    ARCHITECTURE = "architecture"
    MODULE = "module"
    FLOW = "flow"
    RUNBOOK = "runbook"


@dataclass
class Citation:
    """Link back to source code."""

    file_path: str
    symbol_fq_name: str = ""
    start_line: int = 0
    end_line: int = 0

    def to_link(self) -> str:
        """Render as a Markdown-friendly reference."""
        loc = self.file_path
        if self.start_line:
            loc += f"#L{self.start_line}"
            if self.end_line and self.end_line != self.start_line:
                loc += f"-L{self.end_line}"
        if self.symbol_fq_name:
            return f"[`{self.symbol_fq_name}`]({loc})"
        return f"[{self.file_path}]({loc})"


@dataclass
class DocSection:
    """A single section within a generated document."""

    heading: str
    body: str = ""
    citations: list[Citation] = field(default_factory=list)
    subsections: list[DocSection] = field(default_factory=list)
    order: int = 0


@dataclass
class GeneratedDocument:
    """A complete generated document ready for rendering."""

    doc_type: DocType
    title: str
    snapshot_id: str
    scope_id: str = ""  # module name, flow entry point, etc.
    sections: list[DocSection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
