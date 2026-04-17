"""
Answer builder.

Assembles retrieved context into a prompt, calls the LLM (or stub),
and structures the response with evidence, confidence, and verification.
"""

from __future__ import annotations

import logging

from app.reasoning.llm_client import LLMClient, StubLLMClient
from app.reasoning.models import (
    Answer,
    Confidence,
    Evidence,
    Question,
    QuestionType,
    RetrievalContext,
    VerificationItem,
)

logger = logging.getLogger(__name__)

# System prompts per question type
_SYSTEM_PROMPTS: dict[QuestionType, str] = {
    QuestionType.ARCHITECTURE: (
        "You are a code intelligence assistant. The user is asking about the architecture "
        "of a legacy C# codebase. Use the provided context (module summaries, symbol data, "
        "edges) to explain the high-level structure. Always cite file paths and symbol names. "
        "If uncertain, say so. Respond in JSON with keys: answer, confidence (high/medium/low), "
        "evidence (list of {file_path, symbol_fq_name, relevance}), "
        "verification (list of {description, how_to_verify})."
    ),
    QuestionType.FLOW: (
        "You are a code intelligence assistant. The user is asking about a call flow or "
        "execution sequence in a legacy C# codebase. Trace the call chain step-by-step "
        "using the provided edges and symbols. Always cite file paths and line numbers. "
        "Respond in JSON with keys: answer, confidence, evidence, verification."
    ),
    QuestionType.COMPONENT: (
        "You are a code intelligence assistant. The user is asking about a specific class, "
        "method, or component in a legacy C# codebase. Explain its purpose, inputs, outputs, "
        "side effects, and relationships. Always cite evidence. "
        "Respond in JSON with keys: answer, confidence, evidence, verification."
    ),
    QuestionType.IMPACT: (
        "You are a code intelligence assistant. The user is asking about the impact of "
        "changing something in a legacy C# codebase. Use the call graph (callers) to identify "
        "what would be affected. List impacted symbols and files. Rate the blast radius. "
        "Respond in JSON with keys: answer, confidence, evidence, verification."
    ),
    QuestionType.GENERAL: (
        "You are a code intelligence assistant for a legacy C# codebase. Answer the user's "
        "question using the provided context. Always cite evidence. If you cannot determine "
        "the answer from the context, say so clearly. "
        "Respond in JSON with keys: answer, confidence, evidence, verification."
    ),
}


async def build_answer(
    question: Question,
    context: RetrievalContext,
    llm: LLMClient | None = None,
) -> Answer:
    """
    Build a structured answer from retrieved context.

    If an LLM client is provided, uses it for natural-language generation.
    Otherwise, builds a deterministic answer from the context alone.
    """
    if llm is None or isinstance(llm, StubLLMClient):
        return _build_deterministic_answer(question, context)

    return await _build_llm_answer(question, context, llm)


def _build_deterministic_answer(question: Question, context: RetrievalContext) -> Answer:
    """
    Build an answer purely from structural data -- no LLM involved.

    This always works and produces accurate (if less fluent) answers.
    """
    parts: list[str] = []
    evidence: list[Evidence] = []
    related: list[str] = []

    # Include symbol information
    if context.symbols:
        for sym in context.symbols:
            parts.append(
                f"**{sym['kind'].title()} `{sym['fq_name']}`**: "
                f"declared in `{sym['file_path']}` (lines {sym['start_line']}-{sym['end_line']}). "
                f"Signature: `{sym.get('signature', 'N/A')}`."
            )
            evidence.append(
                Evidence(
                    file_path=sym["file_path"],
                    symbol_fq_name=sym["fq_name"],
                    start_line=sym["start_line"],
                    end_line=sym["end_line"],
                    relevance="Direct symbol match",
                )
            )
            related.append(sym["fq_name"])

    # Include call graph edges
    if context.edges:
        call_edges = [e for e in context.edges if e["edge_type"] == "calls"]
        if call_edges:
            parts.append(f"\n**Call relationships** ({len(call_edges)} edges):")
            for edge in call_edges[:10]:
                parts.append(f"  - `{edge['source_fq_name']}` calls `{edge['target_fq_name']}`")
                if edge.get("file_path"):
                    evidence.append(
                        Evidence(
                            file_path=edge["file_path"],
                            start_line=edge.get("line", 0),
                            relevance=(
                                f"Call from {edge['source_fq_name']} to {edge['target_fq_name']}"
                            ),
                        )
                    )

    # Include vector search results
    if context.summaries:
        parts.append(f"\n**Related summaries** ({len(context.summaries)} found):")
        for summary in context.summaries[:5]:
            parts.append(
                f"  - [{summary.get('scope_type', 'unknown')}] {summary.get('text', '')[:200]}"
            )
            for ref in summary.get("refs", [])[:2]:
                if isinstance(ref, dict) and ref.get("file_path"):
                    evidence.append(
                        Evidence(
                            file_path=ref["file_path"],
                            symbol_fq_name=ref.get("symbol_fq_name", ""),
                            start_line=ref.get("start_line", 0),
                            end_line=ref.get("end_line", 0),
                            relevance="Vector search match",
                        )
                    )

    # Include graph neighborhood
    if context.graph_neighborhood:
        related.extend(context.graph_neighborhood[:10])

    # Build confidence assessment
    confidence = _assess_confidence(context)

    # Build verification checklist
    verification = _build_verification(question, context)

    # Assemble answer text
    if not parts:
        answer_text = (
            "No relevant information found in the indexed codebase for this question. "
            "Try rephrasing, or ensure the target snapshot has been fully ingested and analysed."
        )
        confidence = Confidence.LOW
    else:
        answer_text = "\n".join(parts)

    return Answer(
        question=question.text,
        question_type=question.question_type.value,
        answer_text=answer_text,
        evidence=evidence,
        confidence=confidence,
        verification=verification,
        related_symbols=sorted(set(related))[:20],
    )


async def _build_llm_answer(
    question: Question,
    context: RetrievalContext,
    llm: LLMClient,
) -> Answer:
    """Build an LLM-enriched answer."""
    system_prompt = _SYSTEM_PROMPTS.get(
        question.question_type, _SYSTEM_PROMPTS[QuestionType.GENERAL]
    )

    # Build user message with context
    user_parts = [f"Question: {question.text}\n"]

    if context.symbols:
        user_parts.append("## Symbols")
        for sym in context.symbols[:10]:
            user_parts.append(
                f"- {sym['kind']} `{sym['fq_name']}` in `{sym['file_path']}` "
                f"(lines {sym['start_line']}-{sym['end_line']})"
            )
            if sym.get("signature"):
                user_parts.append(f"  Signature: `{sym['signature']}`")

    if context.edges:
        user_parts.append("\n## Call Graph Edges")
        for edge in context.edges[:15]:
            user_parts.append(
                f"- `{edge['source_fq_name']}` --{edge['edge_type']}--> `{edge['target_fq_name']}`"
            )

    if context.summaries:
        user_parts.append("\n## Summaries")
        for s in context.summaries[:8]:
            user_parts.append(f"- [{s.get('scope_type', '')}] {s.get('text', '')[:300]}")

    user_message = "\n".join(user_parts)

    try:
        response = await llm.chat_json(system_prompt, user_message)
    except Exception as e:
        logger.exception("LLM call failed, falling back to deterministic answer")
        answer = _build_deterministic_answer(question, context)
        answer.error = f"LLM call failed: {str(e)[:200]}"
        return answer

    # Parse LLM response
    evidence = []
    for ev in response.get("evidence", []):
        evidence.append(
            Evidence(
                file_path=ev.get("file_path", ""),
                symbol_fq_name=ev.get("symbol_fq_name", ""),
                relevance=ev.get("relevance", ""),
            )
        )

    verification = []
    for v in response.get("verification", []):
        verification.append(
            VerificationItem(
                description=v.get("description", ""),
                how_to_verify=v.get("how_to_verify", ""),
            )
        )

    confidence_str = response.get("confidence", "medium").lower()
    try:
        confidence = Confidence(confidence_str)
    except ValueError:
        confidence = Confidence.MEDIUM

    return Answer(
        question=question.text,
        question_type=question.question_type.value,
        answer_text=response.get("answer", ""),
        evidence=evidence,
        confidence=confidence,
        verification=verification,
        related_symbols=sorted(set(context.graph_neighborhood[:20])),
    )


def _assess_confidence(context: RetrievalContext) -> Confidence:
    """Assess confidence based on how much context we found."""
    score = 0
    if context.symbols:
        score += 2
    if context.edges:
        score += 1
    if context.summaries:
        score += 1
    if context.graph_neighborhood:
        score += 1
    if score >= 4:
        return Confidence.HIGH
    if score >= 2:
        return Confidence.MEDIUM
    return Confidence.LOW


def _build_verification(question: Question, context: RetrievalContext) -> list[VerificationItem]:
    """Build a verification checklist tailored to the question type."""
    items: list[VerificationItem] = []

    if question.question_type == QuestionType.IMPACT:
        items.append(
            VerificationItem(
                description="Verify all listed callers are still active",
                how_to_verify="Search for usages of the target symbol in the IDE",
            )
        )
        items.append(
            VerificationItem(
                description="Check for indirect callers via interfaces or reflection",
                how_to_verify="Search for the interface type in the codebase",
            )
        )
    elif question.question_type == QuestionType.FLOW:
        items.append(
            VerificationItem(
                description="Verify the call chain by stepping through with a debugger",
                how_to_verify="Set breakpoints at each listed method and trigger the flow",
            )
        )
    elif question.question_type == QuestionType.COMPONENT:
        items.append(
            VerificationItem(
                description="Verify the component's behaviour matches the description",
                how_to_verify="Read the source code at the cited file and line range",
            )
        )

    if context.symbols:
        for sym in context.symbols[:3]:
            items.append(
                VerificationItem(
                    description=f"Review `{sym['fq_name']}` in `{sym['file_path']}`",
                    how_to_verify=f"Open {sym['file_path']} at line {sym['start_line']}",
                )
            )

    return items[:7]
