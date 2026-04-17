"""
Universal LLM client.

Supports any OpenAI-compatible API endpoint, which covers:
- OpenAI (api.openai.com)
- Azure OpenAI
- Anthropic Claude (via compatible proxy)
- Local models: Ollama, LM Studio, vLLM, llama.cpp server, LocalAI
- Any provider exposing /v1/chat/completions

Configuration is via environment variables so switching providers
requires zero code changes.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Default timeout for LLM API calls (seconds)
DEFAULT_TIMEOUT = 60


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""

    base_url: str = ""  # e.g. "http://localhost:11434/v1" for Ollama
    api_key: str = ""  # empty for local models
    model: str = "gpt-4o-mini"  # model name (provider-specific)
    temperature: float = 0.1
    max_tokens: int = 2048
    timeout: int = DEFAULT_TIMEOUT


class LLMClient(ABC):
    """Abstract LLM client interface."""

    @abstractmethod
    async def chat(self, system_prompt: str, user_message: str) -> str:
        """Send a chat message and return the assistant response text."""
        ...

    @abstractmethod
    async def chat_json(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        """Send a chat message and parse the response as JSON."""
        ...


class OpenAICompatibleClient(LLMClient):
    """
    Client for any OpenAI-compatible chat completion API.

    Works with: OpenAI, Azure OpenAI, Ollama (/v1), LM Studio,
    vLLM, llama.cpp server, LocalAI, Together AI, Groq, etc.
    """

    def __init__(self, config: LLMConfig):
        self._config = config
        self._base_url = config.base_url.rstrip("/")

    async def chat(self, system_prompt: str, user_message: str) -> str:
        payload = self._build_payload(system_prompt, user_message)
        data = await self._call_api(payload)
        return self._extract_content(data)

    async def chat_json(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        payload = self._build_payload(system_prompt, user_message)
        # Request JSON response format if supported
        payload["response_format"] = {"type": "json_object"}
        data = await self._call_api(payload)
        content = self._extract_content(data)
        try:
            return json.loads(content)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            logger.warning("LLM response was not valid JSON, attempting extraction")
            return self._extract_json_from_text(content)

    def _build_payload(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        return {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }

    async def _call_api(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        url = f"{self._base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]

    def _extract_content(self, data: dict[str, Any]) -> str:
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError) as e:
            logger.error("Unexpected LLM response structure: %s", e)
            return ""

    def _extract_json_from_text(self, text: str) -> dict[str, Any]:
        """Attempt to extract JSON from text that may have markdown fences."""
        # Try to find JSON block in markdown
        for start_marker in ("```json", "```"):
            if start_marker in text:
                start = text.index(start_marker) + len(start_marker)
                end = text.index("```", start) if "```" in text[start:] else len(text)
                try:
                    return json.loads(text[start:end].strip())  # type: ignore[no-any-return]
                except json.JSONDecodeError:
                    continue
        # Try the whole text
        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return {"raw_response": text, "parse_error": True}


class StubLLMClient(LLMClient):
    """
    Stub client for testing and when no LLM is configured.

    Returns a structured response explaining that no LLM is available,
    preserving the pipeline contract.
    """

    async def chat(self, system_prompt: str, user_message: str) -> str:
        return (
            "LLM is not configured. The answer below is based on deterministic "
            "analysis only (code graph, symbol metadata, and structural facts). "
            "Configure an LLM provider for richer natural-language explanations."
        )

    async def chat_json(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        return {
            "answer": await self.chat(system_prompt, user_message),
            "llm_available": False,
        }


def create_llm_client(config: LLMConfig | None = None) -> LLMClient:
    """
    Factory: creates the appropriate LLM client.

    If a base_url is provided, uses the OpenAI-compatible client.
    Otherwise returns a stub.

    Examples:
        # OpenAI
        create_llm_client(LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="sk-...",
            model="gpt-4o-mini"
        ))

        # Ollama (local)
        create_llm_client(LLMConfig(
            base_url="http://localhost:11434/v1",
            model="llama3.1"
        ))

        # LM Studio (local)
        create_llm_client(LLMConfig(
            base_url="http://localhost:1234/v1",
            model="local-model"
        ))

        # vLLM (local)
        create_llm_client(LLMConfig(
            base_url="http://localhost:8000/v1",
            model="meta-llama/Llama-3.1-8B"
        ))

        # No LLM
        create_llm_client(None)
    """
    if config and config.base_url:
        logger.info("LLM client: OpenAI-compatible at %s (model=%s)", config.base_url, config.model)
        return OpenAICompatibleClient(config)
    logger.info("LLM client: Stub (no LLM configured)")
    return StubLLMClient()
