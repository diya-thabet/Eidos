"""
Tests for the answer builder.

Covers: deterministic answers, LLM answer building (mocked),
confidence assessment, verification checklist, and edge cases.
"""

from unittest.mock import AsyncMock

import pytest

from app.reasoning.answer_builder import _assess_confidence, _build_verification, build_answer
from app.reasoning.llm_client import StubLLMClient
from app.reasoning.models import (
    Answer,
    Confidence,
    Question,
    QuestionType,
    RetrievalContext,
)


def _make_question(qtype=QuestionType.COMPONENT, target="MyApp.Foo"):
    return Question(
        text="What does MyApp.Foo do?",
        snapshot_id="snap-001",
        question_type=qtype,
        target_symbol=target,
    )


def _make_context(*, symbols=True, edges=True, summaries=True):
    ctx = RetrievalContext()
    if symbols:
        ctx.symbols = [
            {
                "fq_name": "MyApp.Foo",
                "kind": "class",
                "name": "Foo",
                "file_path": "Foo.cs",
                "start_line": 5,
                "end_line": 30,
                "namespace": "MyApp",
                "parent_fq_name": None,
                "signature": "public class Foo",
                "modifiers": "public",
                "return_type": "",
            }
        ]
    if edges:
        ctx.edges = [
            {
                "source_fq_name": "MyApp.Foo.DoWork",
                "target_fq_name": "MyApp.Bar.Save",
                "edge_type": "calls",
                "file_path": "Foo.cs",
                "line": 15,
            },
        ]
    if summaries:
        ctx.summaries = [
            {
                "text": "Class Foo with 3 members.",
                "scope_type": "symbol_summary",
                "refs": [{"file_path": "Foo.cs", "start_line": 5, "end_line": 30}],
                "metadata": {"fq_name": "MyApp.Foo"},
            }
        ]
    if symbols or edges:
        ctx.graph_neighborhood = ["MyApp.Foo", "MyApp.Foo.DoWork", "MyApp.Bar.Save"]
    return ctx


class TestDeterministicAnswer:
    @pytest.mark.asyncio
    async def test_builds_answer_without_llm(self):
        question = _make_question()
        context = _make_context()
        answer = await build_answer(question, context, llm=None)
        assert isinstance(answer, Answer)
        assert answer.question == question.text
        assert answer.question_type == "component"
        assert len(answer.answer_text) > 0

    @pytest.mark.asyncio
    async def test_answer_includes_symbol_info(self):
        question = _make_question()
        context = _make_context()
        answer = await build_answer(question, context)
        assert "MyApp.Foo" in answer.answer_text
        assert "Foo.cs" in answer.answer_text

    @pytest.mark.asyncio
    async def test_answer_includes_call_edges(self):
        question = _make_question()
        context = _make_context()
        answer = await build_answer(question, context)
        assert "calls" in answer.answer_text.lower() or "Call" in answer.answer_text

    @pytest.mark.asyncio
    async def test_answer_has_evidence(self):
        question = _make_question()
        context = _make_context()
        answer = await build_answer(question, context)
        assert len(answer.evidence) > 0
        assert any(e.file_path == "Foo.cs" for e in answer.evidence)

    @pytest.mark.asyncio
    async def test_answer_has_verification(self):
        question = _make_question()
        context = _make_context()
        answer = await build_answer(question, context)
        assert len(answer.verification) > 0

    @pytest.mark.asyncio
    async def test_answer_has_related_symbols(self):
        question = _make_question()
        context = _make_context()
        answer = await build_answer(question, context)
        assert "MyApp.Foo" in answer.related_symbols

    @pytest.mark.asyncio
    async def test_empty_context_returns_low_confidence(self):
        question = _make_question()
        context = RetrievalContext()
        answer = await build_answer(question, context)
        assert answer.confidence == Confidence.LOW
        assert "no relevant" in answer.answer_text.lower()

    @pytest.mark.asyncio
    async def test_stub_llm_uses_deterministic(self):
        question = _make_question()
        context = _make_context()
        stub = StubLLMClient()
        answer = await build_answer(question, context, llm=stub)
        # Should still produce deterministic answer
        assert len(answer.answer_text) > 0
        assert answer.error == ""


class TestLLMAnswer:
    @pytest.mark.asyncio
    async def test_llm_answer_uses_response(self):
        question = _make_question()
        context = _make_context()

        mock_llm = AsyncMock()
        mock_llm.chat_json.return_value = {
            "answer": "Foo is a service class that handles business logic.",
            "confidence": "high",
            "evidence": [
                {"file_path": "Foo.cs", "symbol_fq_name": "MyApp.Foo", "relevance": "Main class"}
            ],
            "verification": [{"description": "Check Foo.cs", "how_to_verify": "Open the file"}],
        }
        # Make it NOT a StubLLMClient
        mock_llm.__class__ = type("MockLLM", (), {})

        answer = await build_answer(question, context, llm=mock_llm)
        assert answer.answer_text == "Foo is a service class that handles business logic."
        assert answer.confidence == Confidence.HIGH
        assert len(answer.evidence) == 1
        assert len(answer.verification) == 1

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(self):
        question = _make_question()
        context = _make_context()

        mock_llm = AsyncMock()
        mock_llm.chat_json.side_effect = Exception("API timeout")
        mock_llm.__class__ = type("MockLLM", (), {})

        answer = await build_answer(question, context, llm=mock_llm)
        # Should fall back to deterministic
        assert "MyApp.Foo" in answer.answer_text
        assert "API timeout" in answer.error


class TestConfidenceAssessment:
    def test_full_context_is_high(self):
        ctx = _make_context()
        assert _assess_confidence(ctx) == Confidence.HIGH

    def test_symbols_only_is_medium(self):
        ctx = _make_context(edges=False, summaries=False)
        assert _assess_confidence(ctx) == Confidence.MEDIUM

    def test_empty_is_low(self):
        ctx = RetrievalContext()
        assert _assess_confidence(ctx) == Confidence.LOW


class TestVerification:
    def test_impact_verification(self):
        q = _make_question(qtype=QuestionType.IMPACT)
        ctx = _make_context()
        items = _build_verification(q, ctx)
        assert any("caller" in v.description.lower() for v in items)

    def test_flow_verification(self):
        q = _make_question(qtype=QuestionType.FLOW)
        ctx = _make_context()
        items = _build_verification(q, ctx)
        descriptions = " ".join(v.description + " " + v.how_to_verify for v in items).lower()
        assert "breakpoint" in descriptions or "step" in descriptions or "debug" in descriptions

    def test_component_verification(self):
        q = _make_question(qtype=QuestionType.COMPONENT)
        ctx = _make_context()
        items = _build_verification(q, ctx)
        assert len(items) > 0

    def test_includes_symbol_review(self):
        q = _make_question()
        ctx = _make_context()
        items = _build_verification(q, ctx)
        assert any("Foo.cs" in v.how_to_verify for v in items)
