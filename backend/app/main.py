from fastapi import FastAPI
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import repos
from app.api import analysis as analysis_api
from app.storage.database import engine
from app.storage.models import Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (replaced by Alembic migrations in production)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        logging.getLogger(__name__).warning("Could not connect to DB on startup; skipping table creation")
    yield
    try:
        await engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title="Eidos - Legacy Code Intelligence",
    version="0.1.0",
    description="Explains legacy codebases, generates documentation, and reviews PRs with evidence.",
    lifespan=lifespan,
)

app.include_router(repos.router, prefix="/repos", tags=["repos"])
app.include_router(analysis_api.router, prefix="/repos", tags=["analysis"])


@app.get("/health")
async def health():
    return {"status": "ok"}
