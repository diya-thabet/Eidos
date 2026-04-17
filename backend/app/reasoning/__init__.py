"""
Reasoning engine -- Explain / Q&A.

Modules:
    models            - Question, Answer, Evidence, RetrievalContext
    llm_client        - Universal LLM client (OpenAI-compatible, local, stub)
    question_router   - Question classification and symbol extraction
    retriever         - Hybrid retrieval (vector + graph)
    answer_builder    - Context assembly + answer generation
"""
