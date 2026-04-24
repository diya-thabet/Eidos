"""
Production middleware stack for Eidos.

Provides:
- Request ID injection (X-Request-ID header)
- Structured JSON logging with request context
- Global exception handling (no stack trace leaks)
- Simple in-memory rate limiting per IP
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from typing import Any, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("eidos.middleware")

# Context variable holding the current request ID (accessible from anywhere)
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


# ------------------------------------------------------------------
# Request ID middleware
# ------------------------------------------------------------------


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Injects an ``X-Request-ID`` header into every request and response.

    If the client sends an ``X-Request-ID``, it is reused; otherwise a
    new UUID4 is generated.  The value is stored in a :class:`ContextVar`
    so that loggers and downstream code can access it.
    """

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request_id_ctx.set(rid)
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


# ------------------------------------------------------------------
# Access log middleware (structured)
# ------------------------------------------------------------------


class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    Logs every request with method, path, status, duration and request ID.
    """

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        rid = getattr(request.state, "request_id", "")
        logger.info(
            "request",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client": request.client.host if request.client else "",
            },
        )
        return response


# ------------------------------------------------------------------
# Global exception handler
# ------------------------------------------------------------------


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """
    Catches unhandled exceptions and returns a safe 500 JSON response.

    Never leaks internal stack traces to clients.
    """

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        try:
            return await call_next(request)
        except Exception:
            rid = getattr(request.state, "request_id", "")
            logger.exception(
                "Unhandled exception",
                extra={"request_id": rid, "path": request.url.path},
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": rid,
                },
                headers={"X-Request-ID": rid},
            )


# ------------------------------------------------------------------
# In-memory rate limiter
# ------------------------------------------------------------------


class _TokenBucket:
    """Simple per-key token bucket."""

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate  # tokens per second
        self._burst = burst
        self._buckets: dict[str, tuple[float, float]] = defaultdict(
            lambda: (float(burst), time.monotonic())
        )

    def allow(self, key: str) -> bool:
        tokens, last = self._buckets[key]
        now = time.monotonic()
        elapsed = now - last
        tokens = min(self._burst, tokens + elapsed * self._rate)
        if tokens >= 1.0:
            self._buckets[key] = (tokens - 1.0, now)
            return True
        self._buckets[key] = (tokens, now)
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP rate limiting using a token-bucket algorithm.

    Defaults: 60 requests/minute burst, 1 request/second sustained.
    Skipped for health/version endpoints and when ``rate_limit_enabled``
    is False.
    """

    _SKIP_PATHS = {"/health", "/version", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app: FastAPI, rate: float = 1.0, burst: int = 60, enabled: bool = True) -> None:  # noqa: E501
        super().__init__(app)
        self._bucket = _TokenBucket(rate, burst)
        self._enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        if not self._enabled:
            return await call_next(request)
        if request.url.path in self._SKIP_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        if not self._bucket.allow(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )
        return await call_next(request)


# ------------------------------------------------------------------
# Helper: attach all middleware to app
# ------------------------------------------------------------------


def install_middleware(app: FastAPI) -> None:
    """
    Install the full production middleware stack on the FastAPI app.

    Order matters -- middleware is applied in reverse order of addition
    (last added = outermost).
    """
    from app.core.config import settings

    # CORS -- always added so frontend can talk to the API
    from starlette.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=getattr(settings, "cors_origins", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Rate limiting (outermost after CORS)
    rate_enabled = getattr(settings, "rate_limit_enabled", True)
    rate = getattr(settings, "rate_limit_per_second", 2.0)
    burst = getattr(settings, "rate_limit_burst", 120)
    app.add_middleware(RateLimitMiddleware, rate=rate, burst=burst, enabled=rate_enabled)

    # Access logging
    app.add_middleware(AccessLogMiddleware)

    # Global exception handler
    app.add_middleware(ExceptionHandlerMiddleware)

    # Request ID (innermost -- runs first)
    app.add_middleware(RequestIDMiddleware)

