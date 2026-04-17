"""
Semantic indexing pipeline.

Modules:
    summary_schema    - Data classes for structured summaries
    facts_extractor   - Deterministic facts from code graph (no AI)
    summarizer        - LLM summariser interface + stub implementation
    embedder          - Embedding generation (hash-based + OpenAI placeholder)
    vector_store      - Vector DB abstraction (in-memory + Qdrant)
    indexer           - Pipeline orchestrator
"""
