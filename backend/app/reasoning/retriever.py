"""
Hybrid retriever.

Combines vector similarity search with graph-based expansion
to gather rich context for answering questions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.indexing.embedder import Embedder
from app.indexing.indexer import COLLECTION_NAME
from app.indexing.vector_store import VectorStore
from app.reasoning.models import Question, QuestionType, RetrievalContext
from app.storage.models import Edge, Summary, Symbol

logger = logging.getLogger(__name__)

# Maximum items per retrieval category
MAX_VECTOR_RESULTS = 10
MAX_GRAPH_SYMBOLS = 20
MAX_EDGES = 30
MAX_CODE_SNIPPETS = 8
MAX_SNIPPET_CHARS = 1200
STOPWORDS = {
    "the", "and", "for", "with", "what", "when", "where", "which", "how",
    "does", "this", "that", "would", "break", "change", "explain", "about",
    "code", "class", "method", "function", "system", "overall",
}


async def retrieve_context(
    db: AsyncSession,
    question: Question,
    *,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
) -> RetrievalContext:
    """
    Gather all context needed to answer a question.

    Strategy varies by question type:
    - COMPONENT: vector search + direct symbol lookup
    - FLOW: symbol lookup + call edges (callees chain)
    - IMPACT: symbol lookup + call edges (callers chain)
    - ARCHITECTURE: module summaries + broad vector search
    - GENERAL: vector search
    """
    ctx = RetrievalContext()

    # Step 1: Vector similarity search (always)
    ctx.summaries = await _vector_search(question, embedder, vector_store)

    # Step 2: Direct symbol lookup (if target symbol specified)
    if question.target_symbol:
        ctx.symbols = await _lookup_symbol(db, question.snapshot_id, question.target_symbol)
    else:
        ctx.symbols = await _search_symbols_from_question(
            db, question.snapshot_id, question.text
        )
        if ctx.symbols:
            question.target_symbol = ctx.symbols[0]["fq_name"]

    # Step 3: Graph expansion (based on question type)
    if question.target_symbol:
        if question.question_type == QuestionType.FLOW:
            ctx.edges = await _get_call_edges(
                db,
                question.snapshot_id,
                question.target_symbol,
                direction="out",
                max_hops=question.max_hops,
                edge_types=("calls",),
            )
        elif question.question_type == QuestionType.COMPONENT:
            ctx.edges = await _get_call_edges(
                db,
                question.snapshot_id,
                question.target_symbol,
                direction="both",
                max_hops=question.max_hops,
                edge_types=("calls", "contains", "uses", "inherits", "implements"),
            )
        elif question.question_type == QuestionType.IMPACT:
            ctx.edges = await _get_call_edges(
                db,
                question.snapshot_id,
                question.target_symbol,
                direction="in",
                max_hops=question.max_hops,
                edge_types=("calls", "uses", "inherits", "implements"),
            )
        else:
            ctx.edges = await _get_call_edges(
                db,
                question.snapshot_id,
                question.target_symbol,
                direction="both",
                max_hops=question.max_hops,
                edge_types=("calls", "contains", "uses", "inherits", "implements"),
            )

        # Collect all symbol fq_names from edges for neighborhood
        fq_names = set()
        for e in ctx.edges:
            fq_names.add(e["source_fq_name"])
            fq_names.add(e["target_fq_name"])
        ctx.graph_neighborhood = sorted(fq_names)
        ctx.graph_paths = _build_graph_paths(ctx.edges, question.target_symbol)
        ctx.symbols = _dedupe_symbols(
            ctx.symbols
            + await _get_neighbor_symbols(db, question.snapshot_id, ctx.graph_neighborhood)
        )[:MAX_GRAPH_SYMBOLS]

    elif question.question_type == QuestionType.ARCHITECTURE:
        ctx.edges = await _get_architecture_edges(db, question.snapshot_id)
        ctx.graph_paths = _build_graph_paths(ctx.edges, "")
        fq_names = set()
        for e in ctx.edges:
            fq_names.add(e["source_fq_name"])
            fq_names.add(e["target_fq_name"])
        ctx.graph_neighborhood = sorted(fq_names)

    # Step 4: For architecture questions, also pull module summaries
    if question.question_type == QuestionType.ARCHITECTURE:
        module_summaries = await _get_module_summaries(db, question.snapshot_id)
        ctx.summaries.extend(module_summaries)

    if question.question_type in (QuestionType.ARCHITECTURE, QuestionType.GENERAL):
        if not ctx.symbols:
            ctx.symbols = await _get_overview_symbols(db, question.snapshot_id)
        if not ctx.summaries:
            ctx.summaries = await _get_snapshot_summaries(db, question.snapshot_id)

    if not ctx.symbols and not ctx.edges and not ctx.summaries:
        ctx.symbols = await _get_overview_symbols(db, question.snapshot_id)
        ctx.summaries = await _get_snapshot_summaries(db, question.snapshot_id)

    ctx.code_snippets = _build_code_snippets(ctx.symbols)

    ctx.retrieval_summary = {
        "strategy": question.question_type.value,
        "target_symbol": question.target_symbol,
        "query_terms": _extract_terms(question.text),
        "summary_count": len(ctx.summaries),
        "symbol_count": len(ctx.symbols),
        "edge_count": len(ctx.edges),
        "neighbor_count": len(ctx.graph_neighborhood),
        "path_count": len(ctx.graph_paths),
        "snippet_count": len(ctx.code_snippets),
        "confidence_signals": _confidence_signals(ctx),
    }

    logger.info(
        "Retrieved context: %d summaries, %d symbols, %d edges, %d neighbors",
        len(ctx.summaries),
        len(ctx.symbols),
        len(ctx.edges),
        len(ctx.graph_neighborhood),
    )
    return ctx


# ---------------------------------------------------------------------------
# Internal retrieval helpers
# ---------------------------------------------------------------------------


async def _vector_search(
    question: Question,
    embedder: Embedder | None,
    vector_store: VectorStore | None,
) -> list[dict[str, Any]]:
    """Search vector store for summaries relevant to the question."""
    if embedder is None or vector_store is None:
        return []
    try:
        query_vectors = await embedder.embed([question.text])
        results = await vector_store.search(
            COLLECTION_NAME,
            query_vectors[0],
            limit=MAX_VECTOR_RESULTS,
            filters={"snapshot_id": question.snapshot_id},
        )
        return [
            {
                "text": r.record.text,
                "score": r.score,
                "scope_type": r.record.scope_type,
                "refs": r.record.refs,
                "metadata": r.record.metadata,
            }
            for r in results
        ]
    except Exception as e:
        logger.warning("Vector search failed: %s", e)
        return []


async def _lookup_symbol(db: AsyncSession, snapshot_id: str, target: str) -> list[dict[str, Any]]:
    """Look up symbols matching the target (exact or partial match)."""
    # Try exact match first
    result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id, Symbol.fq_name == target)
    )
    sym = result.scalar_one_or_none()
    if sym:
        return [_symbol_to_dict(sym)]

    # Partial match: name contains target
    result = await db.execute(
        select(Symbol)
        .where(
            Symbol.snapshot_id == snapshot_id,
            or_(
                Symbol.fq_name.contains(target),
                Symbol.name == target,
            ),
        )
        .limit(MAX_GRAPH_SYMBOLS)
    )
    return [_symbol_to_dict(s) for s in result.scalars().all()]


async def _search_symbols_from_question(
    db: AsyncSession,
    snapshot_id: str,
    question_text: str,
) -> list[dict[str, Any]]:
    """Find likely target symbols from natural-language question terms."""
    terms = _extract_terms(question_text)
    if not terms:
        return []

    conditions = []
    for term in terms:
        conditions.append(Symbol.fq_name.contains(term))
        conditions.append(Symbol.name.contains(term))
        conditions.append(Symbol.file_path.contains(term))

    result = await db.execute(
        select(Symbol)
        .where(Symbol.snapshot_id == snapshot_id, or_(*conditions))
        .limit(MAX_GRAPH_SYMBOLS)
    )
    symbols = [_symbol_to_dict(s) for s in result.scalars().all()]
    return sorted(
        symbols,
        key=lambda s: _symbol_question_score(s, terms),
        reverse=True,
    )


def _symbol_question_score(symbol: dict[str, Any], terms: list[str]) -> int:
    text = " ".join(
        str(symbol.get(k, ""))
        for k in ("fq_name", "name", "file_path", "signature", "namespace")
    ).lower()
    score = 0
    symbol_name = str(symbol.get("name", "")).lower()
    for term in terms:
        lower_term = term.lower()
        if lower_term in text:
            score += 3 if lower_term == symbol_name else 1
    return score


async def _get_call_edges(
    db: AsyncSession,
    snapshot_id: str,
    target: str,
    direction: str = "both",
    max_hops: int = 2,
    edge_types: tuple[str, ...] = ("calls",),
) -> list[dict[str, Any]]:
    """
    BFS traversal of call edges from a target symbol.

    direction: "in" (callers), "out" (callees), "both"
    """
    visited_edges: list[dict[str, Any]] = []
    frontier = {target}
    visited_nodes: set[str] = {target}

    for _ in range(max_hops):
        if not frontier:
            break
        next_frontier: set[str] = set()

        for node in frontier:
            conditions = [
                Edge.snapshot_id == snapshot_id,
                Edge.edge_type.in_(edge_types),
            ]
            if direction == "out":
                conditions.append(Edge.source_fq_name.contains(node))
            elif direction == "in":
                conditions.append(Edge.target_fq_name.contains(node))
            else:
                conditions.append(
                    or_(Edge.source_fq_name.contains(node), Edge.target_fq_name.contains(node))
                )

            result = await db.execute(select(Edge).where(*conditions).limit(MAX_EDGES))
            for edge in result.scalars().all():
                edge_dict = _edge_to_dict(edge)
                visited_edges.append(edge_dict)
                for fq in (edge.source_fq_name, edge.target_fq_name):
                    if fq not in visited_nodes:
                        visited_nodes.add(fq)
                        next_frontier.add(fq)

        frontier = next_frontier

    return visited_edges[:MAX_EDGES]


async def _get_architecture_edges(
    db: AsyncSession,
    snapshot_id: str,
) -> list[dict[str, Any]]:
    """Retrieve a representative relationship sample for architecture answers."""
    result = await db.execute(
        select(Edge)
        .where(
            Edge.snapshot_id == snapshot_id,
            Edge.edge_type.in_(("uses", "inherits", "implements", "calls", "contains")),
        )
        .limit(MAX_EDGES)
    )
    return [_edge_to_dict(edge) for edge in result.scalars().all()]


async def _get_overview_symbols(
    db: AsyncSession,
    snapshot_id: str,
) -> list[dict[str, Any]]:
    """Fetch representative symbols for broad codebase questions."""
    result = await db.execute(
        select(Symbol)
        .where(
            Symbol.snapshot_id == snapshot_id,
            Symbol.kind.in_(("class", "interface", "record", "struct", "enum")),
        )
        .limit(MAX_GRAPH_SYMBOLS)
    )
    symbols = [_symbol_to_dict(sym) for sym in result.scalars().all()]
    if symbols:
        return symbols

    result = await db.execute(
        select(Symbol)
        .where(Symbol.snapshot_id == snapshot_id)
        .limit(MAX_GRAPH_SYMBOLS)
    )
    return [_symbol_to_dict(sym) for sym in result.scalars().all()]


async def _get_snapshot_summaries(
    db: AsyncSession,
    snapshot_id: str,
) -> list[dict[str, Any]]:
    """Fetch available summaries as fallback RAG context."""
    result = await db.execute(
        select(Summary)
        .where(Summary.snapshot_id == snapshot_id)
        .limit(MAX_VECTOR_RESULTS)
    )
    summaries = []
    for row in result.scalars().all():
        try:
            data = json.loads(row.summary_json)
        except json.JSONDecodeError:
            data = {"purpose": row.summary_json}
        summaries.append(
            {
                "text": data.get("purpose", "") if isinstance(data, dict) else str(data),
                "scope_type": row.scope_type,
                "refs": data.get("citations", []) if isinstance(data, dict) else [],
                "metadata": {"scope_id": row.scope_id},
            }
        )
    return summaries


async def _get_neighbor_symbols(
    db: AsyncSession,
    snapshot_id: str,
    fq_names: list[str],
) -> list[dict[str, Any]]:
    """Fetch symbol details for graph neighbors."""
    if not fq_names:
        return []
    result = await db.execute(
        select(Symbol)
        .where(Symbol.snapshot_id == snapshot_id, Symbol.fq_name.in_(fq_names[:MAX_GRAPH_SYMBOLS]))
        .limit(MAX_GRAPH_SYMBOLS)
    )
    return [_symbol_to_dict(sym) for sym in result.scalars().all()]


def _edge_to_dict(edge: Edge) -> dict[str, Any]:
    return {
        "source_fq_name": edge.source_fq_name,
        "target_fq_name": edge.target_fq_name,
        "edge_type": edge.edge_type,
        "file_path": edge.file_path,
        "line": edge.line,
    }


def _build_graph_paths(edges: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
    """Create compact first-hop path metadata for the UI and LLM prompt."""
    paths = []
    for edge in edges[:15]:
        src = edge.get("source_fq_name", "")
        dst = edge.get("target_fq_name", "")
        direction = "outbound" if src == target else "inbound" if dst == target else "neighbor"
        paths.append(
            {
                "source": src,
                "target": dst,
                "edge_type": edge.get("edge_type", ""),
                "direction": direction,
                "file_path": edge.get("file_path", ""),
                "line": edge.get("line", 0),
            }
        )
    return paths


def _extract_terms(question_text: str) -> list[str]:
    """Extract useful lexical retrieval terms from a natural-language question."""
    terms = []
    for raw in question_text.replace("_", " ").replace("-", " ").split():
        term = raw.strip("`'\".,:;()[]{}<>!?/")
        if len(term) < 3 or term.lower() in STOPWORDS:
            continue
        terms.append(term)
    return sorted(
        set(terms),
        key=lambda t: (any(ch.isupper() for ch in t), len(t)),
        reverse=True,
    )[:10]


def _dedupe_symbols(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate symbols while preserving ranking order."""
    seen = set()
    unique = []
    for symbol in symbols:
        fq_name = symbol.get("fq_name", "")
        if not fq_name or fq_name in seen:
            continue
        seen.add(fq_name)
        unique.append(symbol)
    return unique


def _build_code_snippets(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a bounded snippet pack for LLM grounding."""
    snippets = []
    budget = MAX_CODE_SNIPPETS * MAX_SNIPPET_CHARS
    for symbol in symbols:
        source = str(symbol.get("source_code", "") or "").strip()
        if not source:
            continue
        clipped = source[:MAX_SNIPPET_CHARS]
        snippets.append(
            {
                "symbol_fq_name": symbol.get("fq_name", ""),
                "file_path": symbol.get("file_path", ""),
                "start_line": symbol.get("start_line", 0),
                "end_line": symbol.get("end_line", 0),
                "code": clipped,
            }
        )
        budget -= len(clipped)
        if len(snippets) >= MAX_CODE_SNIPPETS or budget <= 0:
            break
    return snippets


def _confidence_signals(ctx: RetrievalContext) -> list[str]:
    """Explain why the RAG answer should be trusted or treated carefully."""
    signals = []
    if ctx.symbols:
        signals.append("symbol_match")
    if ctx.edges:
        signals.append("graph_edges")
    if ctx.graph_paths:
        signals.append("graph_paths")
    if ctx.code_snippets:
        signals.append("source_snippets")
    if ctx.summaries:
        signals.append("summaries")
    return signals


async def _get_module_summaries(db: AsyncSession, snapshot_id: str) -> list[dict[str, Any]]:
    """Retrieve all module-level summaries for architecture questions."""
    result = await db.execute(
        select(Summary).where(
            Summary.snapshot_id == snapshot_id,
            Summary.scope_type == "module",
        )
    )
    summaries = []
    for row in result.scalars().all():
        try:
            data = json.loads(row.summary_json)
            summaries.append(
                {
                    "text": data.get("purpose", ""),
                    "scope_type": "module_summary",
                    "refs": data.get("citations", []),
                    "metadata": {"module_name": data.get("name", row.scope_id)},
                }
            )
        except json.JSONDecodeError:
            continue
    return summaries


def _symbol_to_dict(sym: Symbol) -> dict[str, Any]:
    return {
        "fq_name": sym.fq_name,
        "kind": sym.kind,
        "name": sym.name,
        "file_path": sym.file_path,
        "start_line": sym.start_line,
        "end_line": sym.end_line,
        "namespace": sym.namespace,
        "parent_fq_name": sym.parent_fq_name,
        "signature": sym.signature,
        "modifiers": sym.modifiers,
        "return_type": sym.return_type,
        "source_code": sym.source_code,
        "cyclomatic_complexity": sym.cyclomatic_complexity,
        "cognitive_complexity": sym.cognitive_complexity,
        "commit_count": sym.commit_count,
        "author_count": sym.author_count,
    }
