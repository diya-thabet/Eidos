import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.api import admin as admin_api
from app.api import analysis as analysis_api
from app.api import auth as auth_api
from app.api import docgen as docgen_api
from app.api import evaluations as eval_api
from app.api import indexing as indexing_api
from app.api import reasoning as reasoning_api
from app.api import repos
from app.api import reviews as reviews_api
from app.api import search as search_api
from app.api import webhooks as webhook_api
from app.core.config import settings
from app.core.middleware import install_middleware
from app.storage.database import engine
from app.storage.models import Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    # Create tables on startup (replaced by Alembic migrations in production)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not connect to DB on startup; skipping table creation"
        )
    yield
    try:
        await engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title="Eidos - Legacy Code Intelligence",
    version=settings.version,
    description="Explains legacy codebases, generates docs, and reviews PRs.",
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
