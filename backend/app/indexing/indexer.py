"""
Indexing orchestrator.

Coordinates the full summarisation & indexing pipeline:
  1. Extract deterministic facts from the code graph
  2. (Optionally) enrich with LLM-generated prose
  3. Persist summaries to PostgreSQL
  4. Generate embeddings and store in vector DB
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.graph_builder import CodeGraph
from app.indexing.embedder import Embedder, create_embedder
from app.indexing.facts_extractor import (
    extract_file_facts,
    extract_module_facts,
    extract_symbol_facts,
)
from app.indexing.summarizer import Summariser, create_summariser
from app.indexing.vector_store import InMemoryVectorStore, VectorRecord, VectorStore
from app.storage.models import Summary

logger = logging.getLogger(__name__)

# Qdrant / vector DB collection name
COLLECTION_NAME = "eidos_summaries"

# Batch size for embedding calls (limits API cost)
EMBED_BATCH_SIZE = 64


async def run_indexing(
    db: AsyncSession,
    snapshot_id: str,
    graph: CodeGraph,
    *,
    summariser: Summariser | None = None,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
) -> dict:
    """
    Run the full indexing pipeline for a snapshot.

    Args:
        db: Database session for persisting summaries.
        snapshot_id: Snapshot to index.
        graph: The code graph produced by static analysis.
        summariser: Summary enrichment strategy (defaults to StubSummariser).
        embedder: Embedding generator (defaults to HashEmbedder).
        vector_store: Vector storage backend (defaults to InMemoryVectorStore).

    Returns:
        dict with counts: symbols, modules, files, vectors.
    """
    if summariser is None:
        summariser = create_summariser()
    if embedder is None:
        embedder = create_embedder()
    if vector_store is None:
        vector_store = InMemoryVectorStore()

    # Step 1: Extract deterministic facts
    symbol_facts = extract_symbol_facts(graph)
    module_facts = extract_module_facts(graph)
    file_facts = extract_file_facts(graph)

    # Step 2: Enrich with summariser (no-op if StubSummariser)
    symbol_summaries = [await summariser.summarise_symbol(f) for f in symbol_facts]
    module_summaries = [await summariser.summarise_module(f) for f in module_facts]
    file_summaries = [await summariser.summarise_file(f) for f in file_facts]

    # Step 3: Persist to PostgreSQL
    all_db_summaries: list[Summary] = []

    for s in symbol_summaries:
        all_db_summaries.append(_to_db_summary(snapshot_id, "symbol", s.fq_name, s))
    for m in module_summaries:
        all_db_summaries.append(_to_db_summary(snapshot_id, "module", m.name, m))
    for f in file_summaries:
        all_db_summaries.append(_to_db_summary(snapshot_id, "file", f.path, f))

    for summary in all_db_summaries:
        db.add(summary)
    await db.flush()

    # Step 4: Generate embeddings and store in vector DB
    await vector_store.ensure_collection(COLLECTION_NAME, embedder.vector_size)

    records: list[VectorRecord] = []
    texts: list[str] = []

    for s in symbol_summaries:
        text = _summary_to_text(s)
        records.append(
            VectorRecord(
                id=uuid.uuid4().hex,
                snapshot_id=snapshot_id,
                scope_type="symbol_summary",
                text=text,
                refs=[asdict(c) for c in s.citations],
                metadata={"fq_name": s.fq_name, "kind": s.kind},
            )
        )
        texts.append(text)

    for m in module_summaries:
        text = _summary_to_text(m)
        records.append(
            VectorRecord(
                id=uuid.uuid4().hex,
                snapshot_id=snapshot_id,
                scope_type="module_summary",
                text=text,
                refs=[asdict(c) for c in m.citations],
                metadata={"module_name": m.name},
            )
        )
        texts.append(text)

    for f in file_summaries:
        text = _summary_to_text(f)
        records.append(
            VectorRecord(
                id=uuid.uuid4().hex,
                snapshot_id=snapshot_id,
                scope_type="file_summary",
                text=text,
                refs=[asdict(c) for c in f.citations],
                metadata={"file_path": f.path},
            )
        )
        texts.append(text)

    # Embed and upsert in batches
    vector_count = 0
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch_texts = texts[i : i + EMBED_BATCH_SIZE]
        batch_records = records[i : i + EMBED_BATCH_SIZE]
        vectors = await embedder.embed(batch_texts)
        count = await vector_store.upsert(COLLECTION_NAME, batch_records, vectors)
        vector_count += count

    stats = {
        "symbol_summaries": len(symbol_summaries),
        "module_summaries": len(module_summaries),
        "file_summaries": len(file_summaries),
        "vectors_stored": vector_count,
    }
    logger.info("Indexing complete for snapshot %s: %s", snapshot_id, stats)
    return stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_db_summary(snapshot_id: str, scope_type: str, scope_id: str, summary) -> Summary:
    """Convert a summary dataclass to a DB model."""
    return Summary(
        snapshot_id=snapshot_id,
        scope_type=scope_type,
        scope_id=scope_id,
        summary_json=json.dumps(asdict(summary), default=str),
    )


def _summary_to_text(summary) -> str:
    """Convert a summary to a single text string for embedding."""
    parts: list[str] = []

    if hasattr(summary, "fq_name"):
        parts.append(f"Symbol: {summary.fq_name}")
    elif hasattr(summary, "name"):
        parts.append(f"Module: {summary.name}")
    elif hasattr(summary, "path"):
        parts.append(f"File: {summary.path}")

    if hasattr(summary, "purpose"):
        parts.append(summary.purpose)

    if hasattr(summary, "side_effects") and summary.side_effects:
        parts.append("Side effects: " + "; ".join(summary.side_effects))

    if hasattr(summary, "risks") and summary.risks:
        parts.append("Risks: " + "; ".join(summary.risks))

    if hasattr(summary, "responsibilities") and summary.responsibilities:
        parts.append("Responsibilities: " + "; ".join(summary.responsibilities))

    return " | ".join(parts)
