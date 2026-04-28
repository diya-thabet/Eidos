"""
LLM-based summariser interface.

Defines a protocol for summary generation so the system can work with
**any** LLM backend (OpenAI, Claude, local models, or a no-op stub).

For now the only concrete implementation is ``StubSummariser`` which
returns the deterministic facts unchanged.  When LLM access is approved,
drop in ``LLMSummariser`` without touching any other code.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.indexing.summary_schema import (
    FileSummary,
    ModuleSummary,
    SymbolSummary,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class Summariser(ABC):
    """
    Strategy interface for generating natural-language summaries.

    Implementations receive pre-extracted facts and may optionally
    enrich them with LLM-generated prose.
    """

    @abstractmethod
    async def summarise_symbol(self, facts: SymbolSummary, code_snippet: str = "") -> SymbolSummary:
        """Enrich a symbol summary.  *code_snippet* is optional context."""
        ...

    @abstractmethod
    async def summarise_module(self, facts: ModuleSummary) -> ModuleSummary:
        """Enrich a module summary."""
        ...

    @abstractmethod
    async def summarise_file(self, facts: FileSummary) -> FileSummary:
        """Enrich a file summary."""
        ...


# ---------------------------------------------------------------------------
# Stub implementation (deterministic, no LLM)
# ---------------------------------------------------------------------------


class StubSummariser(Summariser):
    """
    Pass-through summariser that returns facts **as-is**.

    This is the default when no LLM is configured.  It guarantees that
    every field is populated from deterministic analysis only -- no
    hallucination risk.
    """

    async def summarise_symbol(self, facts: SymbolSummary, code_snippet: str = "") -> SymbolSummary:
        return facts

    async def summarise_module(self, facts: ModuleSummary) -> ModuleSummary:
        return facts

    async def summarise_file(self, facts: FileSummary) -> FileSummary:
        return facts


# ---------------------------------------------------------------------------
# LLM implementation placeholder
# ---------------------------------------------------------------------------


class LLMSummariser(Summariser):
    """
    LLM-powered summariser (placeholder).

    When LLM access is approved, implement the three methods below.
    The expected flow:

    1. Serialise *facts* + *code_snippet* into a structured prompt.
    2. Call the LLM API with a JSON-schema response format.
    3. Parse the response back into the dataclass.
    4. Preserve original citations; lower confidence if the model
       response is incomplete.

    The prompt should instruct the LLM to:
    - Narrate the facts, not invent new ones.
    - Keep citations from the input.
    - Flag uncertainty explicitly.
    """

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini"):
        self._api_key = api_key
        self._model = model

    async def summarise_symbol(self, facts: SymbolSummary, code_snippet: str = "") -> SymbolSummary:
        # LLM enrichment not yet wired; returns deterministic facts (works without API key)
        logger.warning(
            "LLMSummariser.summarise_symbol called but LLM is not configured; returning facts."
        )
        return facts

    async def summarise_module(self, facts: ModuleSummary) -> ModuleSummary:
        logger.warning(
            "LLMSummariser.summarise_module called but LLM is not configured; returning facts."
        )
        return facts

    async def summarise_file(self, facts: FileSummary) -> FileSummary:
        logger.warning(
            "LLMSummariser.summarise_file called but LLM is not configured; returning facts."
        )
        return facts


def create_summariser(api_key: str = "") -> Summariser:
    """
    Factory: returns an LLM summariser if an API key is provided,
    otherwise falls back to the deterministic stub.
    """
    if api_key:
        return LLMSummariser(api_key=api_key)
    return StubSummariser()
