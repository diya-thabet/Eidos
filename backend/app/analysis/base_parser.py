"""
Abstract base for language parsers.

Every language parser must implement ``parse_file`` which takes raw bytes
and a relative path and returns a :class:`FileAnalysis`.  Parsers are
registered via :mod:`app.analysis.parser_registry`.

To add a new language:
1. Create ``<lang>_parser.py`` implementing :class:`LanguageParser`.
2. Register it in ``parser_registry.py``.
3. Map the file extensions in ``core/ingestion.py`` ``LANGUAGE_MAP``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.analysis.models import FileAnalysis


class LanguageParser(ABC):
    """Interface that every language parser must implement."""

    @property
    @abstractmethod
    def language_id(self) -> str:
        """Short identifier for the language (e.g. ``'csharp'``, ``'java'``)."""
        ...

    @abstractmethod
    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        """
        Parse a single source file and return its analysis.

        Args:
            source: Raw file content as bytes (UTF-8).
            file_path: Relative path inside the repo.

        Returns:
            A :class:`FileAnalysis` with symbols, edges, and metadata.
        """
        ...
