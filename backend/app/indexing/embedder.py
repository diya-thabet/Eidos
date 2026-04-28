"""
Embedding interface.

Abstracts the embedding generation so the system can use OpenAI, a local
model, or a deterministic hash-based embedder for testing.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Default vector size used across the system
DEFAULT_VECTOR_SIZE = 256


class Embedder(ABC):
    """Protocol for generating text embeddings."""

    @property
    @abstractmethod
    def vector_size(self) -> int:
        """Dimensionality of the output vectors."""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts."""
        ...


class HashEmbedder(Embedder):
    """
    Deterministic hash-based embedder for testing.

    Produces consistent vectors from text using SHA-256 so that
    identical inputs always produce identical embeddings.
    Not semantically meaningful, but preserves the pipeline contract.
    """

    def __init__(self, size: int = DEFAULT_VECTOR_SIZE):
        self._size = size

    @property
    def vector_size(self) -> int:
        return self._size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            # Expand hash to fill vector_size floats in [-1, 1] range
            floats: list[float] = []
            i = 0
            while len(floats) < self._size:
                chunk = hashlib.sha256(h + i.to_bytes(4, "big")).digest()
                for byte in chunk:
                    if len(floats) >= self._size:
                        break
                    # Map byte [0,255] to [-1.0, 1.0]
                    floats.append((byte / 127.5) - 1.0)
                i += 1
            # Normalise to unit length
            norm = sum(f * f for f in floats) ** 0.5
            if norm > 0:
                floats = [f / norm for f in floats]
            results.append(floats)
        return results


class OpenAIEmbedder(Embedder):
    """
    OpenAI embedding client (placeholder).

    When LLM/API access is approved, replace the stub with real calls.
    """

    def __init__(self, api_key: str = "", model: str = "text-embedding-3-small"):
        self._api_key = api_key
        self._model = model
        self._size = 1536  # text-embedding-3-small default

    @property
    def vector_size(self) -> int:
        return self._size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # OpenAI embedding not yet wired; uses hash fallback (works without API key)
        logger.warning("OpenAIEmbedder called but not configured; falling back to hash embedder.")
        fallback = HashEmbedder(self._size)
        return await fallback.embed(texts)


def create_embedder(api_key: str = "") -> Embedder:
    """Factory: returns OpenAI embedder if key provided, else hash embedder."""
    if api_key:
        return OpenAIEmbedder(api_key=api_key)
    return HashEmbedder()
