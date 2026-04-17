"""
Adapter wrapping the existing C# parser to conform to :class:`LanguageParser`.
"""

from __future__ import annotations

from app.analysis.base_parser import LanguageParser
from app.analysis.csharp_parser import parse_file as _cs_parse
from app.analysis.models import FileAnalysis


class CSharpParser(LanguageParser):
    """Thin adapter around the original ``csharp_parser.parse_file``."""

    @property
    def language_id(self) -> str:
        return "csharp"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        return _cs_parse(source, file_path)
