"""
Tests for the LLM client interface and implementations.

Covers: StubLLMClient, OpenAICompatibleClient (mocked), factory function,
config building, and JSON parsing edge cases.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.reasoning.llm_client import (
    LLMConfig,
    OpenAICompatibleClient,
    StubLLMClient,
    create_llm_client,
)


class TestStubLLMClient:
    @pytest.mark.asyncio
    async def test_chat_returns_explanation(self):
        stub = StubLLMClient()
        result = await stub.chat("system", "user question")
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_chat_json_returns_dict(self):
        stub = StubLLMClient()
        result = await stub.chat_json("system", "user question")
        assert isinstance(result, dict)
        assert result["llm_available"] is False

    @pytest.mark.asyncio
    async def test_chat_json_has_answer(self):
        stub = StubLLMClient()
        result = await stub.chat_json("system", "question")
        assert "answer" in result


class TestOpenAICompatibleClient:
    @pytest.mark.asyncio
    async def test_chat_calls_api(self):
        config = LLMConfig(base_url="http://localhost:11434/v1", model="test")
        client = OpenAICompatibleClient(config)

        mock_response = {"choices": [{"message": {"content": "Hello from LLM"}}]}

        with patch("app.reasoning.llm_client.httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_http.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = MagicMock()
            mock_instance.post.return_value = mock_resp

            result = await client.chat("system prompt", "user message")
            assert result == "Hello from LLM"

            # Verify the API was called correctly
            call_args = mock_instance.post.call_args
            assert "/chat/completions" in call_args[0][0]
            payload = call_args[1]["json"]
            assert payload["model"] == "test"
            assert len(payload["messages"]) == 2

    @pytest.mark.asyncio
    async def test_chat_json_parses_response(self):
        config = LLMConfig(base_url="http://localhost:1234/v1", model="local")
        client = OpenAICompatibleClient(config)

        json_content = json.dumps({"answer": "test answer", "confidence": "high"})
        mock_response = {"choices": [{"message": {"content": json_content}}]}

        with patch("app.reasoning.llm_client.httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_http.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = MagicMock()
            mock_instance.post.return_value = mock_resp

            result = await client.chat_json("system", "user")
            assert result["answer"] == "test answer"
            assert result["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_chat_json_handles_markdown_fenced_json(self):
        config = LLMConfig(base_url="http://localhost:1234/v1", model="local")
        client = OpenAICompatibleClient(config)

        # Some models wrap JSON in markdown code fences
        content = '```json\n{"answer": "fenced"}\n```'
        mock_response = {"choices": [{"message": {"content": content}}]}

        with patch("app.reasoning.llm_client.httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_http.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = MagicMock()
            mock_instance.post.return_value = mock_resp

            result = await client.chat_json("system", "user")
            assert result["answer"] == "fenced"

    @pytest.mark.asyncio
    async def test_chat_json_handles_invalid_json(self):
        config = LLMConfig(base_url="http://localhost:1234/v1", model="local")
        client = OpenAICompatibleClient(config)

        mock_response = {"choices": [{"message": {"content": "not json at all"}}]}

        with patch("app.reasoning.llm_client.httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_http.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = MagicMock()
            mock_instance.post.return_value = mock_resp

            result = await client.chat_json("system", "user")
            assert "parse_error" in result or "raw_response" in result

    def test_builds_correct_payload(self):
        config = LLMConfig(
            base_url="http://localhost:8000/v1",
            model="llama3.1",
            temperature=0.5,
            max_tokens=1024,
        )
        client = OpenAICompatibleClient(config)
        payload = client._build_payload("sys", "usr")
        assert payload["model"] == "llama3.1"
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 1024
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"


class TestFactory:
    def test_no_config_returns_stub(self):
        client = create_llm_client(None)
        assert isinstance(client, StubLLMClient)

    def test_empty_url_returns_stub(self):
        client = create_llm_client(LLMConfig(base_url=""))
        assert isinstance(client, StubLLMClient)

    def test_with_url_returns_openai_compatible(self):
        client = create_llm_client(LLMConfig(base_url="http://localhost:11434/v1"))
        assert isinstance(client, OpenAICompatibleClient)

    def test_openai_config(self):
        client = create_llm_client(
            LLMConfig(
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4o-mini",
            )
        )
        assert isinstance(client, OpenAICompatibleClient)

    def test_ollama_config(self):
        client = create_llm_client(
            LLMConfig(
                base_url="http://localhost:11434/v1",
                model="llama3.1",
            )
        )
        assert isinstance(client, OpenAICompatibleClient)


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig()
        assert config.base_url == ""
        assert config.api_key == ""
        assert config.temperature == 0.1
        assert config.max_tokens == 2048
        assert config.timeout == 60
