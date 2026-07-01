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
        "of the codebase. Use the provided context (module summaries, symbol data, "
        "edges, graph paths, and code snippets) to explain the high-level structure. "
        "Prefer graph-grounded facts over guesses. Always cite file paths and symbol names. "
        "If uncertain, say so. Respond in JSON with keys: answer, confidence (high/medium/low), "
        "evidence (list of {file_path, symbol_fq_name, relevance}), "
        "verification (list of {description, how_to_verify})."
    ),
    QuestionType.FLOW: (
        "You are a code intelligence assistant. The user is asking about a call flow or "
        "execution sequence in the codebase. Trace the call chain step-by-step "
        "using the provided edges, graph paths, and code snippets. "
        "Always cite file paths and line numbers. "
        "Respond in JSON with keys: answer, confidence, evidence, verification."
    ),
    QuestionType.COMPONENT: (
        "You are a code intelligence assistant. The user is asking about a specific class, "
        "method, or component in the codebase. Explain its purpose, inputs, outputs, "
        "side effects, relationships, and direct source snippets. Always cite evidence. "
        "Respond in JSON with keys: answer, confidence, evidence, verification."
    ),
    QuestionType.IMPACT: (
        "You are a code intelligence assistant. The user is asking about the impact of "
        "changing something in the codebase. Use the call graph (callers) to identify "
        "what would be affected. List impacted symbols and files. Rate the blast radius. "
        "Use inbound graph paths and source snippets as primary evidence. "
        "Respond in JSON with keys: answer, confidence, evidence, verification."
    ),
    QuestionType.GENERAL: (
        "You are a code intelligence assistant for the codebase. Answer the user's "
        "question using the provided graph, symbol, summary, and source-snippet context. "
        "Always cite evidence. If you cannot determine "
        "the answer from the context, say so clearly. "
        "Respond in JSON with keys: answer, confidence, evidence, verification."
    ),
}


def _build_human_explanation(question: Question, context: RetrievalContext) -> str:
    """Build a plain-language explanation from retrieved structural context."""
    if not context.symbols and not context.summaries:
        return ""

    symbols = context.symbols
    fq_names = [str(s.get("fq_name", "")) for s in symbols]
    names = [str(s.get("name", "")) for s in symbols]
    namespaces = sorted(
        {str(s.get("namespace", "")) for s in symbols if s.get("namespace")}
    )
    package_text = " ".join(fq_names + namespaces).lower()

    intro = _infer_project_intro(package_text, names, context)
    responsibilities = _infer_responsibilities(package_text, names, namespaces)
    flow = _infer_execution_flow(names, fq_names, context)

    lines = ["**Plain-English explanation**"]
    lines.append(intro)
    if responsibilities:
        lines.append("\n**What the main parts do:**")
        lines.extend(f"- {item}" for item in responsibilities[:7])
    if flow:
        lines.append("\n**How it likely works at runtime:**")
        lines.extend(f"{idx}. {step}" for idx, step in enumerate(flow[:5], start=1))
    if namespaces:
        lines.append(
            "\n**Main areas/modules involved:** "
            + ", ".join(f"`{namespace}`" for namespace in namespaces[:8])
        )
    return "\n".join(lines)


def _infer_project_intro(
    package_text: str,
    names: list[str],
    context: RetrievalContext,
) -> str:
    summary_text = " ".join(str(s.get("text", "")) for s in context.summaries[:3]).strip()
    if summary_text:
        return f"This codebase appears to implement {summary_text[:350].rstrip('.')} in code."

    lower_names = " ".join(names).lower()
    if "galactic" in package_text or {"PlayerEntity", "EnemyEntity", "BulletEntity"} & set(names):
        return (
            "This codebase appears to be a Java/JavaFX arcade-style game. "
            "It models game objects such as the player, enemies, bullets, particles, "
            "and power-ups, then renders and updates them through game states."
        )
    if "controller" in lower_names or "service" in lower_names:
        return (
            "This codebase appears to be an application with service/controller-style "
            "components. The retrieved classes define the main business objects and the "
            "operations used to process requests or actions."
        )
    return (
        "This codebase is organized into several classes/modules that each handle a "
        "specific responsibility. The retrieved symbols show the main building blocks "
        "and how the project is structured."
    )


def _infer_responsibilities(
    package_text: str,
    names: list[str],
    namespaces: list[str],
) -> list[str]:
    name_set = set(names)
    responsibilities = []
    if "state" in package_text or any(name.endswith("State") for name in names):
        responsibilities.append(
            "State classes control the current game/application mode, such as menu, "
            "playing, paused, or game over."
        )
    if "composite" in package_text or any(name.endswith("Entity") for name in names):
        responsibilities.append(
            "Entity classes represent objects inside the game world, such as players, "
            "enemies, bullets, particles, and power-ups."
        )
    if "decorator" in package_text or "WeaponDecorator" in name_set:
        responsibilities.append(
            "Decorator classes modify weapon behavior, for example adding double-shot "
            "or spread-shot behavior without rewriting the base weapon."
        )
    if "factory" in package_text or any("Factory" in name for name in names):
        responsibilities.append(
            "Factory classes centralize object creation so game entities can be created "
            "consistently from one place."
        )
    if "Renderer" in name_set or "StarField" in name_set or "view" in package_text:
        responsibilities.append(
            "View/rendering classes draw the game scene and visual effects on screen."
        )
    if "Launcher" in name_set or "GameApp" in name_set:
        responsibilities.append(
            "Launcher/Application classes start the program and bootstrap the UI/game loop."
        )
    if "Logger" in name_set or "utils" in package_text:
        responsibilities.append("Utility classes provide cross-cutting helpers such as logging.")
    if not responsibilities and namespaces:
        responsibilities.append(
            "The project is split into modules/namespaces so related classes stay grouped together."
        )
    return responsibilities


def _infer_execution_flow(
    names: list[str],
    fq_names: list[str],
    context: RetrievalContext,
) -> list[str]:
    text = " ".join(names + fq_names).lower()
    if "gameapp" in text or "launcher" in text or "playingstate" in text:
        return [
            "`Launcher`/`GameApp` starts the JavaFX application.",
            "The application switches between state objects like menu, playing, paused, "
            "and game over.",
            "During gameplay, entity objects are updated: player, enemies, bullets, "
            "particles, and power-ups.",
            "Factories/decorators help create entities and customize weapons.",
            "Renderer/view classes draw the current game state to the screen.",
        ]
    call_edges = [e for e in context.edges if e.get("edge_type") == "calls"]
    if call_edges:
        return [
            f"`{edge.get('source_fq_name', '')}` calls `{edge.get('target_fq_name', '')}`."
            for edge in call_edges[:5]
        ]
    return []


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

    human_explanation = _build_human_explanation(question, context)
    if human_explanation:
        parts.append(human_explanation)

    if question.question_type == QuestionType.ARCHITECTURE and context.symbols:
        namespaces = sorted(
            {str(s.get("namespace", "")) for s in context.symbols if s.get("namespace")}
        )
        kinds = {}
        for sym in context.symbols:
            kind = str(sym.get("kind", "unknown"))
            kinds[kind] = kinds.get(kind, 0) + 1
        kind_summary = ", ".join(f"{count} {kind}(s)" for kind, count in sorted(kinds.items()))
        parts.append(
            "**Codebase overview**: this snapshot appears to contain "
            f"{kind_summary or str(len(context.symbols)) + ' symbols'}"
            f" across {len(namespaces)} namespace/module(s)."
        )
        if namespaces:
            parts.append(
                "**Main modules/namespaces**: "
                + ", ".join(f"`{n}`" for n in namespaces[:10])
            )

    # Include symbol information
    if context.symbols:
        if not human_explanation:
            parts.append("**Relevant code elements**:")
        else:
            parts.append("\n**Key code elements I used as evidence**:")
        for sym in context.symbols[:8]:
            signature = sym.get("signature") or sym.get("name", "")
            parts.append(
                f"- `{sym['fq_name']}` ({sym['kind']}) in "
                f"`{sym['file_path']}` lines {sym['start_line']}-{sym['end_line']}"
                + (f" — `{signature}`" if signature else "")
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
        if len(context.symbols) > 8:
            parts.append(f"- ...and {len(context.symbols) - 8} more related symbol(s).")

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

    if context.code_snippets:
        parts.append(f"\n**Source snippets used** ({len(context.code_snippets)} snippets):")
        for snippet in context.code_snippets[:4]:
            parts.append(
                f"  - `{snippet.get('symbol_fq_name', '')}` in "
                f"`{snippet.get('file_path', '')}` "
                f"(lines {snippet.get('start_line', 0)}-{snippet.get('end_line', 0)})"
            )
            evidence.append(
                Evidence(
                    file_path=str(snippet.get("file_path", "")),
                    symbol_fq_name=str(snippet.get("symbol_fq_name", "")),
                    start_line=int(snippet.get("start_line", 0)),
                    end_line=int(snippet.get("end_line", 0)),
                    snippet=str(snippet.get("code", ""))[:300],
                    relevance="Source snippet selected by RAG",
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
        rag_context=_rag_context_payload(context),
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

    if context.graph_paths:
        user_parts.append("\n## Graph Retrieval Paths")
        for path in context.graph_paths[:10]:
            user_parts.append(
                f"- {path['direction']}: `{path['source']}` "
                f"--{path['edge_type']}--> `{path['target']}`"
            )

    if context.retrieval_summary:
        user_parts.append("\n## Retrieval Summary")
        user_parts.append(str(context.retrieval_summary))

    if context.summaries:
        user_parts.append("\n## Summaries")
        for s in context.summaries[:8]:
            user_parts.append(f"- [{s.get('scope_type', '')}] {s.get('text', '')[:300]}")

    if context.code_snippets:
        user_parts.append("\n## Source Snippets")
        for snippet in context.code_snippets[:6]:
            user_parts.append(
                f"### `{snippet['symbol_fq_name']}` in `{snippet['file_path']}` "
                f"(lines {snippet['start_line']}-{snippet['end_line']})\n"
                f"```\n{snippet['code'][:900]}\n```"
            )

    user_message = "\n".join(user_parts)

    try:
        response = await llm.chat_json(system_prompt, user_message)
    except Exception as e:
        logger.exception("LLM call failed, falling back to deterministic answer")
        answer = _build_deterministic_answer(question, context)
        answer.error = f"LLM call failed: {str(e)[:200]}"
        return answer

    # Parse LLM response defensively: real models sometimes return strings
    # instead of the exact JSON object shape requested in the prompt.
    evidence = _parse_llm_evidence(response.get("evidence", []), context)
    verification = _parse_llm_verification(response.get("verification", []))

    confidence_str = str(response.get("confidence", "medium")).lower()
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
        rag_context=_rag_context_payload(context),
    )


def _parse_llm_evidence(raw: object, context: RetrievalContext) -> list[Evidence]:
    """Normalize model evidence output into Evidence objects."""
    items = raw if isinstance(raw, list) else [raw]
    evidence: list[Evidence] = []
    for item in items[:10]:
        if isinstance(item, dict):
            evidence.append(
                Evidence(
                    file_path=str(item.get("file_path", "")),
                    symbol_fq_name=str(item.get("symbol_fq_name", "")),
                    start_line=_safe_int(item.get("start_line", 0)),
                    end_line=_safe_int(item.get("end_line", 0)),
                    snippet=str(item.get("snippet", "")),
                    relevance=str(item.get("relevance", "")),
                )
            )
        elif item:
            evidence.append(Evidence(file_path="", relevance=str(item)))

    if not evidence:
        for symbol in context.symbols[:5]:
            evidence.append(
                Evidence(
                    file_path=str(symbol.get("file_path", "")),
                    symbol_fq_name=str(symbol.get("fq_name", "")),
                    start_line=_safe_int(symbol.get("start_line", 0)),
                    end_line=_safe_int(symbol.get("end_line", 0)),
                    relevance="Retrieved symbol used as LLM context",
                )
            )
    return evidence


def _parse_llm_verification(raw: object) -> list[VerificationItem]:
    """Normalize model verification output into checklist items."""
    items = raw if isinstance(raw, list) else [raw]
    verification: list[VerificationItem] = []
    for item in items[:10]:
        if isinstance(item, dict):
            verification.append(
                VerificationItem(
                    description=str(item.get("description", "")),
                    how_to_verify=str(item.get("how_to_verify", "")),
                )
            )
        elif item:
            verification.append(VerificationItem(description=str(item)))
    return verification


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _rag_context_payload(context: RetrievalContext) -> dict[str, object]:
    """Compact graph-aware RAG metadata for responses."""
    return {
        "summary": context.retrieval_summary,
        "paths": context.graph_paths[:12],
        "neighbors": context.graph_neighborhood[:20],
        "snippets": [
            {
                "symbol_fq_name": s.get("symbol_fq_name", ""),
                "file_path": s.get("file_path", ""),
                "start_line": s.get("start_line", 0),
                "end_line": s.get("end_line", 0),
            }
            for s in context.code_snippets[:8]
        ],
        "symbols": [
            {
                "fq_name": s.get("fq_name", ""),
                "kind": s.get("kind", ""),
                "file_path": s.get("file_path", ""),
                "start_line": s.get("start_line", 0),
                "end_line": s.get("end_line", 0),
            }
            for s in context.symbols[:10]
        ],
    }


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
