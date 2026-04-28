"""
Retry logic for background tasks with exponential backoff.

Used by webhooks and ingestion to retry failed operations.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 2.0  # seconds
DEFAULT_MAX_DELAY = 60.0  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0


async def retry_with_backoff(
    func: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    task_name: str = "task",
    **kwargs: Any,
) -> Any:
    """
    Execute an async function with exponential backoff retry.

    Args:
        func: The async function to execute.
        *args: Positional arguments for the function.
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        backoff_factor: Multiplier for each successive retry delay.
        retryable_exceptions: Tuple of exception types that trigger a retry.
        task_name: Human-readable name for logging.
        **kwargs: Keyword arguments for the function.

    Returns:
        The result of the function call.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            if attempt > 0:
                logger.info(
                    "%s succeeded on attempt %d/%d",
                    task_name, attempt + 1, max_retries + 1,
                )
            return result
        except retryable_exceptions as exc:
            last_exception = exc
            if attempt >= max_retries:
                logger.error(
                    "%s failed after %d attempts: %s",
                    task_name, max_retries + 1, str(exc)[:200],
                )
                raise

            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            logger.warning(
                "%s failed (attempt %d/%d), retrying in %.1fs: %s",
                task_name, attempt + 1, max_retries + 1, delay, str(exc)[:100],
            )
            await asyncio.sleep(delay)

    # Should never reach here, but satisfy type checker
    if last_exception:
        raise last_exception
    raise RuntimeError(f"{task_name} failed unexpectedly")
