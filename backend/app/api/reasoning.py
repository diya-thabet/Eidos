"""
API endpoints for the Explain / Q&A engine.

Provides structured question-answering over indexed codebases
with evidence, confidence, and verification checklists.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.reasoning.answer_builder import build_answer
from app.reasoning.llm_client import LLMConfig, create_llm_client
from app.reasoning.question_router import build_question
from app.reasoning.retriever import retrieve_context
from app.storage.database import get_db
from app.storage.models import RepoSnapshot

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    """User question."""

    question: str
    target_symbol: str | None = None


class EvidenceOut(BaseModel):
    file_path: str
    symbol_fq_name: str = ""
    start_line: int = 0
    end_line: int = 0
    snippet: str = ""
    relevance: str = ""


class VerificationOut(BaseModel):
    description: str
    how_to_verify: str = ""


class AskResponse(BaseModel):
    """Structured answer."""

    question: str
    question_type: str
    answer_text: str
    evidence: list[EvidenceOut]
    confidence: str
    verification: list[VerificationOut]
    related_symbols: list[str]
    error: str = ""


class ClassifyResponse(BaseModel):
    """Question classification result."""

    question: str
    question_type: str
    target_symbol: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/ask",
    response_model=AskResponse,
    summary="Ask a question about the codebase",
)
async def ask_question(
    repo_id: str,
    snapshot_id: str,
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Ask a natural-language question about a snapshot of the codebase.

    The system:
    1. Classifies the question (architecture, flow, component, impact)
    2. Retrieves relevant context (vector search + graph expansion)
    3. Generates a structured answer with evidence and verification

    Works with or without an LLM. Without LLM, returns deterministic
    answers based on code graph analysis.
    """
    await _verify_snapshot(db, repo_id, snapshot_id)

    # Build structured question
    question = build_question(body.question, snapshot_id)
    if body.target_symbol:
        question.target_symbol = body.target_symbol

    # Retrieve context
    context = await retrieve_context(db, question)

    # Create LLM client (or stub)
    llm_config = _get_llm_config()
    llm = create_llm_client(llm_config)

    # Build answer
    answer = await build_answer(question, context, llm)

    return AskResponse(
        question=answer.question,
        question_type=answer.question_type,
        answer_text=answer.answer_text,
        evidence=[
            EvidenceOut(
                file_path=e.file_path,
                symbol_fq_name=e.symbol_fq_name,
                start_line=e.start_line,
                end_line=e.end_line,
                snippet=e.snippet,
                relevance=e.relevance,
            )
            for e in answer.evidence
        ],
        confidence=answer.confidence.value,
        verification=[
            VerificationOut(description=v.description, how_to_verify=v.how_to_verify)
            for v in answer.verification
        ],
        related_symbols=answer.related_symbols,
        error=answer.error,
    )


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/classify",
    response_model=ClassifyResponse,
    summary="Classify a question (debug endpoint)",
)
async def classify_question_endpoint(
    repo_id: str,
    snapshot_id: str,
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Debug endpoint: see how a question is classified without generating an answer."""
    await _verify_snapshot(db, repo_id, snapshot_id)
    question = build_question(body.question, snapshot_id)
    if body.target_symbol:
        question.target_symbol = body.target_symbol
    return ClassifyResponse(
        question=question.text,
        question_type=question.question_type.value,
        target_symbol=question.target_symbol,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _verify_snapshot(db: AsyncSession, repo_id: str, snapshot_id: str) -> Any:
    result = await db.execute(
        select(RepoSnapshot).where(
            RepoSnapshot.id == snapshot_id,
            RepoSnapshot.repo_id == repo_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")


def _get_llm_config() -> LLMConfig | None:
    """Build LLM config from settings."""
    if settings.llm_base_url:
        return LLMConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
        )
    return None
