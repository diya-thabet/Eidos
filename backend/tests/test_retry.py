"""
Tests for retry with exponential backoff (P3.15).

Covers:
- Successful execution on first attempt
- Retry on failure then success
- All retries exhausted raises exception
- Exponential delay calculation
- Custom retryable_exceptions
- Non-retryable exception propagates immediately
- Max delay cap
"""

from __future__ import annotations

import time

import pytest

from app.core.retry import retry_with_backoff


class TestRetryWithBackoff:
    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        call_count = 0

        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_with_backoff(succeed, task_name="test")
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        call_count = 0

        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        result = await retry_with_backoff(
            fail_twice, max_retries=3, base_delay=0.01, task_name="test"
        )
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        async def always_fail():
            raise RuntimeError("permanent error")

        with pytest.raises(RuntimeError, match="permanent error"):
            await retry_with_backoff(
                always_fail, max_retries=2, base_delay=0.01, task_name="test"
            )

    @pytest.mark.asyncio
    async def test_total_attempts_is_retries_plus_one(self):
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await retry_with_backoff(
                always_fail, max_retries=3, base_delay=0.01, task_name="test"
            )
        assert call_count == 4  # 1 initial + 3 retries

    @pytest.mark.asyncio
    async def test_respects_backoff_delay(self):
        call_count = 0

        async def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("retry me")
            return "ok"

        start = time.perf_counter()
        await retry_with_backoff(
            fail_once, max_retries=1, base_delay=0.1, task_name="test"
        )
        elapsed = time.perf_counter() - start
        assert elapsed >= 0.08  # At least ~0.1s delay

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_retried(self):
        call_count = 0

        async def fail_with_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            await retry_with_backoff(
                fail_with_type_error,
                max_retries=3,
                base_delay=0.01,
                retryable_exceptions=(ValueError,),
                task_name="test",
            )
        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_custom_retryable_exceptions(self):
        call_count = 0

        async def fail_with_value_error():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("retryable")
            return "ok"

        result = await retry_with_backoff(
            fail_with_value_error,
            max_retries=3,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
            task_name="test",
        )
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("retry")
            return "ok"

        start = time.perf_counter()
        result = await retry_with_backoff(
            fail_then_succeed,
            max_retries=3,
            base_delay=1.0,
            max_delay=0.05,  # Cap at 50ms
            task_name="test",
        )
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0  # Should be much less than 2s of uncapped delays
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_passes_args_and_kwargs(self):
        async def add(a, b, extra=0):
            return a + b + extra

        result = await retry_with_backoff(add, 3, 4, extra=10, task_name="test")
        assert result == 17

    @pytest.mark.asyncio
    async def test_zero_retries_runs_once(self):
        call_count = 0

        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_with_backoff(succeed, max_retries=0, task_name="test")
        assert result == "ok"
        assert call_count == 1
