import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.api import admin as admin_api
from app.api import analysis as analysis_api
from app.api import auth as auth_api
from app.api import diagrams as diagrams_api
from app.api import docgen as docgen_api
from app.api import evaluations as eval_api
from app.api import indexing as indexing_api
from app.api import portable as portable_api
from app.api import reasoning as reasoning_api
from app.api import repos
from app.api import reviews as reviews_api
from app.api import search as search_api
from app.api import trends as trends_api
from app.api import webhooks as webhook_api
from app.core.config import settings
from app.core.middleware import install_middleware
from app.storage.database import engine
from app.storage.models import Base


def _configure_logging() -> None:
    """Set up logging: JSON in client mode, text in internal mode."""
    import logging

    if settings.edition == "client":
        try:
            from pythonjsonlogger.json import JsonFormatter

            handler = logging.StreamHandler()
            handler.setFormatter(JsonFormatter(
                fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
                rename_fields={"asctime": "timestamp", "levelname": "level"},
            ))
            logging.root.handlers = [handler]
            logging.root.setLevel(logging.INFO)
        except ImportError:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s %(name)s %(levelname)s %(message)s",
            )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )


_configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    logger = logging.getLogger(__name__)
    try:
        if settings.database_url.startswith("sqlite"):
            # SQLite (tests/dev): use create_all since Alembic doesn't support async SQLite well
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        else:
            # PostgreSQL (production): run Alembic migrations
            from alembic.config import Config

            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
            await _run_alembic_upgrade(alembic_cfg)
            logger.info("Alembic migrations applied successfully")
    except Exception:
        logger.warning(
            "Could not run migrations on startup; falling back to create_all"
        )
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception:
            logger.warning("create_all also failed; DB may be unavailable")
    yield
    try:
        await engine.dispose()
    except Exception:
        pass


async def _run_alembic_upgrade(alembic_cfg: Any) -> None:
    """Run Alembic upgrade in a thread (Alembic is sync)."""
    import asyncio

    from alembic import command

    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")


tags_metadata = [
    {"name": "repos", "description": "Register, update, delete, status, ingest"},
    {"name": "analysis", "description": "Symbols, edges, call graphs, overviews, health"},
    {"name": "search", "description": "Full-text search, snapshot comparison, JSON export"},
    {"name": "reasoning", "description": "Ask questions about the codebase in natural language"},
    {"name": "reviews", "description": "PR review: submit a diff, get behavioral risk analysis"},
    {"name": "docs", "description": "Auto-generate documentation with file/line citations"},
    {"name": "evaluations", "description": "Guardrails: evaluate output quality and safety"},
    {"name": "diagrams", "description": "Mermaid class and module diagrams"},
    {"name": "trends", "description": "Track code health scores across snapshots"},
    {"name": "portable", "description": "Export/import snapshots as compact .eidos files"},
    {"name": "indexing", "description": "Summarization and vector indexing pipeline"},
    {"name": "webhooks", "description": "GitHub, GitLab, and generic push webhooks"},
    {"name": "auth", "description": "OAuth login (GitHub, Google), JWT tokens, API keys"},
    {"name": "admin", "description": "User management, roles, plans, usage metering"},
]

app = FastAPI(
    title="Eidos - Code Intelligence Platform",
    version=settings.version,
    description=(
        "Analyzes codebases across 8 languages, auto-generates documentation, "
        "reviews PRs for behavioral risks, and answers questions about your code."
    ),
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# Install production middleware stack (CORS, rate limiting, logging, error handling, request IDs)
install_middleware(app)

app.include_router(auth_api.router, prefix="/auth", tags=["auth"])
app.include_router(repos.router, prefix="/repos", tags=["repos"])
app.include_router(analysis_api.router, prefix="/repos", tags=["analysis"])
app.include_router(indexing_api.router, prefix="/repos", tags=["indexing"])
app.include_router(reasoning_api.router, prefix="/repos", tags=["reasoning"])
app.include_router(reviews_api.router, prefix="/repos", tags=["reviews"])
app.include_router(docgen_api.router, prefix="/repos", tags=["docs"])
app.include_router(eval_api.router, prefix="/repos", tags=["evaluations"])
app.include_router(search_api.router, prefix="/repos", tags=["search"])
app.include_router(diagrams_api.router, prefix="/repos", tags=["diagrams"])
app.include_router(trends_api.router, prefix="/repos", tags=["trends"])
app.include_router(portable_api.router, prefix="/repos", tags=["portable"])
app.include_router(webhook_api.router, tags=["webhooks"])
app.include_router(admin_api.router, prefix="/admin", tags=["admin"])


@app.get("/health")
async def health() -> Any:
    """Shallow health check -- always returns ok if the process is alive."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> Any:
    """
    Deep readiness check.

    Verifies connectivity to PostgreSQL (or whichever DB is configured).
    Returns 503 if the database is unreachable.
    """
    from sqlalchemy import text

    from app.storage.database import async_session

    checks: dict[str, str] = {}

    # Database
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"

    all_ok = all(v == "ok" for v in checks.values())
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )


@app.get("/version")
async def version() -> Any:
    return {
        "version": settings.version,
        "edition": settings.edition,
    }
