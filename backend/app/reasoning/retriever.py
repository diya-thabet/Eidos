"""
Hybrid retriever.

Combines vector similarity search with graph-based expansion
to gather rich context for answering questions.
"""

from __future__ import annotations

import json
import logging

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

    # Step 3: Graph expansion (based on question type)
    if question.target_symbol:
        if question.question_type in (QuestionType.FLOW, QuestionType.COMPONENT):
            ctx.edges = await _get_call_edges(
                db,
                question.snapshot_id,
                question.target_symbol,
                direction="out",
                max_hops=question.max_hops,
            )
        elif question.question_type == QuestionType.IMPACT:
            ctx.edges = await _get_call_edges(
                db,
                question.snapshot_id,
                question.target_symbol,
                direction="in",
                max_hops=question.max_hops,
            )
        else:
            ctx.edges = await _get_call_edges(
                db,
                question.snapshot_id,
                question.target_symbol,
                direction="both",
                max_hops=question.max_hops,
            )

        # Collect all symbol fq_names from edges for neighborhood
        fq_names = set()
        for e in ctx.edges:
            fq_names.add(e["source_fq_name"])
            fq_names.add(e["target_fq_name"])
        ctx.graph_neighborhood = sorted(fq_names)

    # Step 4: For architecture questions, also pull module summaries
    if question.question_type == QuestionType.ARCHITECTURE:
        module_summaries = await _get_module_summaries(db, question.snapshot_id)
        ctx.summaries.extend(module_summaries)

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
) -> list[dict]:
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


async def _lookup_symbol(db: AsyncSession, snapshot_id: str, target: str) -> list[dict]:
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


async def _get_call_edges(
    db: AsyncSession,
    snapshot_id: str,
    target: str,
    direction: str = "both",
    max_hops: int = 2,
) -> list[dict]:
    """
    BFS traversal of call edges from a target symbol.

    direction: "in" (callers), "out" (callees), "both"
    """
    visited_edges: list[dict] = []
    frontier = {target}
    visited_nodes: set[str] = {target}

    for _ in range(max_hops):
        if not frontier:
            break
        next_frontier: set[str] = set()

        for node in frontier:
            conditions = [Edge.snapshot_id == snapshot_id, Edge.edge_type == "calls"]
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
                edge_dict = {
                    "source_fq_name": edge.source_fq_name,
                    "target_fq_name": edge.target_fq_name,
                    "edge_type": edge.edge_type,
                    "file_path": edge.file_path,
                    "line": edge.line,
                }
                visited_edges.append(edge_dict)
                for fq in (edge.source_fq_name, edge.target_fq_name):
                    if fq not in visited_nodes:
                        visited_nodes.add(fq)
                        next_frontier.add(fq)

        frontier = next_frontier

    return visited_edges[:MAX_EDGES]


async def _get_module_summaries(db: AsyncSession, snapshot_id: str) -> list[dict]:
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


def _symbol_to_dict(sym: Symbol) -> dict:
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
    }
