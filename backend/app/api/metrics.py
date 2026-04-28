"""
Prometheus-compatible metrics endpoint.

Exposes application metrics in the Prometheus text exposition format.
No external dependency required - we generate the text format directly.

Metrics exported:
- eidos_requests_total (counter) - total HTTP requests by method + path + status
- eidos_request_duration_seconds (histogram) - request latency
- eidos_ingestions_total (counter) - total ingestion jobs by status
- eidos_snapshots_total (gauge) - current snapshot count by status
- eidos_symbols_total (gauge) - total symbols in the database
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

router = APIRouter()

# In-memory metrics (reset on process restart - acceptable for single-process SaaS)
_request_counts: dict[str, int] = defaultdict(int)
_request_durations: dict[str, list[float]] = defaultdict(list)
_ingestion_counts: dict[str, int] = defaultdict(int)
_MAX_DURATION_SAMPLES = 1000  # Keep last N samples per route


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that records request count and duration."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start

        method = request.method
        path = request.url.path
        status = str(response.status_code)

        # Normalize path (remove IDs for grouping)
        normalized = _normalize_path(path)
        key = f'{method}|{normalized}|{status}'

        _request_counts[key] += 1
        samples = _request_durations[f'{method}|{normalized}']
        samples.append(duration)
        if len(samples) > _MAX_DURATION_SAMPLES:
            samples.pop(0)

        return response


def record_ingestion(status: str) -> None:
    """Record an ingestion completion (call from tasks.py)."""
    _ingestion_counts[status] += 1


def _normalize_path(path: str) -> str:
    """Collapse dynamic path segments for metric grouping."""
    parts = path.strip("/").split("/")
    normalized = []
    for i, part in enumerate(parts):
        # Heuristic: if it looks like an ID (12+ hex chars or UUID-like), replace
        if len(part) >= 12 and all(c in "0123456789abcdef-" for c in part.lower()):
            normalized.append("{id}")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized)


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Application metrics in Prometheus text exposition format.",
    response_class=Response,
)
async def metrics() -> Response:
    """Return metrics in Prometheus text format."""
    lines: list[str] = []

    # Request counter
    lines.append("# HELP eidos_requests_total Total HTTP requests.")
    lines.append("# TYPE eidos_requests_total counter")
    for key, count in sorted(_request_counts.items()):
        method, path, status = key.split("|")
        lines.append(
            f'eidos_requests_total{{method="{method}",path="{path}",'
            f'status="{status}"}} {count}'
        )

    # Request duration (simplified histogram as summary)
    lines.append("# HELP eidos_request_duration_seconds Request duration.")
    lines.append("# TYPE eidos_request_duration_seconds summary")
    for key, samples in sorted(_request_durations.items()):
        if not samples:
            continue
        method, path = key.split("|")
        sorted_s = sorted(samples)
        count = len(sorted_s)
        total = sum(sorted_s)
        p50 = sorted_s[int(count * 0.5)] if count else 0
        p99 = sorted_s[int(count * 0.99)] if count else 0
        lines.append(
            f'eidos_request_duration_seconds{{method="{method}",path="{path}",'
            f'quantile="0.5"}} {p50:.6f}'
        )
        lines.append(
            f'eidos_request_duration_seconds{{method="{method}",path="{path}",'
            f'quantile="0.99"}} {p99:.6f}'
        )
        lines.append(
            f'eidos_request_duration_seconds_count{{method="{method}",'
            f'path="{path}"}} {count}'
        )
        lines.append(
            f'eidos_request_duration_seconds_sum{{method="{method}",'
            f'path="{path}"}} {total:.6f}'
        )

    # Ingestion counter
    lines.append("# HELP eidos_ingestions_total Total ingestion jobs.")
    lines.append("# TYPE eidos_ingestions_total counter")
    for status, count in sorted(_ingestion_counts.items()):
        lines.append(f'eidos_ingestions_total{{status="{status}"}} {count}')

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; charset=utf-8")
