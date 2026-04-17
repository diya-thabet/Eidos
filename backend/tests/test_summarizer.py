"""
Tests for the summariser interface and implementations.

Covers: StubSummariser pass-through, LLMSummariser fallback,
factory function, and interface contract.
"""

import pytest

from app.indexing.summarizer import (
    LLMSummariser,
    StubSummariser,
    Summariser,
    create_summariser,
)
from app.indexing.summary_schema import (
    Citation,
    Confidence,
    FileSummary,
    ModuleSummary,
    SymbolSummary,
)


def _make_symbol_summary() -> SymbolSummary:
    return SymbolSummary(
        fq_name="MyApp.Foo.Bar",
        kind="method",
        purpose="Test method.",
        inputs=["int x"],
        outputs=["string"],
        side_effects=["writes to DB"],
        citations=[
            Citation(file_path="Foo.cs", symbol_fq_name="MyApp.Foo.Bar", start_line=10, end_line=20)
        ],
        confidence=Confidence.HIGH,
    )


def _make_module_summary() -> ModuleSummary:
    return ModuleSummary(
        name="MyApp.Services",
        purpose="Service module.",
        key_classes=["MyApp.Services.Foo"],
        dependencies=["System"],
        citations=[Citation(file_path="Foo.cs")],
    )


def _make_file_summary() -> FileSummary:
    return FileSummary(
        path="Services/Foo.cs",
        purpose="Defines Foo.",
        symbols=["MyApp.Services.Foo"],
        namespace="MyApp.Services",
    )


class TestStubSummariser:
    @pytest.mark.asyncio
    async def test_symbol_passthrough(self):
        stub = StubSummariser()
        original = _make_symbol_summary()
        result = await stub.summarise_symbol(original, code_snippet="class Foo {}")
        assert result.fq_name == original.fq_name
        assert result.purpose == original.purpose
        assert result.side_effects == original.side_effects

    @pytest.mark.asyncio
    async def test_module_passthrough(self):
        stub = StubSummariser()
        original = _make_module_summary()
        result = await stub.summarise_module(original)
        assert result.name == original.name
        assert result.purpose == original.purpose

    @pytest.mark.asyncio
    async def test_file_passthrough(self):
        stub = StubSummariser()
        original = _make_file_summary()
        result = await stub.summarise_file(original)
        assert result.path == original.path


class TestLLMSummariser:
    """LLM is not configured, so it should fall back gracefully."""

    @pytest.mark.asyncio
    async def test_symbol_returns_facts_unchanged(self):
        llm = LLMSummariser(api_key="", model="gpt-4o-mini")
        original = _make_symbol_summary()
        result = await llm.summarise_symbol(original)
        assert result.fq_name == original.fq_name

    @pytest.mark.asyncio
    async def test_module_returns_facts_unchanged(self):
        llm = LLMSummariser()
        original = _make_module_summary()
        result = await llm.summarise_module(original)
        assert result.name == original.name

    @pytest.mark.asyncio
    async def test_file_returns_facts_unchanged(self):
        llm = LLMSummariser()
        original = _make_file_summary()
        result = await llm.summarise_file(original)
        assert result.path == original.path


class TestFactory:
    def test_no_key_returns_stub(self):
        s = create_summariser("")
        assert isinstance(s, StubSummariser)

    def test_with_key_returns_llm(self):
        s = create_summariser("sk-test-key")
        assert isinstance(s, LLMSummariser)

    def test_both_implement_interface(self):
        assert isinstance(StubSummariser(), Summariser)
        assert isinstance(LLMSummariser(), Summariser)
