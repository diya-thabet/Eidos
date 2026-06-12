from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings

# Resolve the .env path relative to the backend/ directory so it works
# regardless of which directory uvicorn is launched from.
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://eidos:eidos@localhost:5432/eidos"
    in_memory_db: bool = False  # set True to use SQLite in-memory (demo/testing)
    demo_mode: bool = False  # set True to run without DB/auth/external services
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    openai_api_key: str = ""
    repos_data_dir: str = "/data/repos"

    # Edition: "internal" (no limits, debug) or "client" (quotas enforced)
    edition: str = "internal"
    version: str = "0.2.0"

    # Database pool tuning
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # LLM provider (any OpenAI-compatible endpoint)
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048
    llm_timeout: int = 60

    # Authentication
    auth_enabled: bool = False  # set True to enforce auth
    secret_key: str = "change-me-in-production-32-chars!"
    jwt_expire_seconds: int = 86400  # 24h
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/auth/callback"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # Default superadmin (seeded on first startup)
    superadmin_email: str = ""

    # Data retention
    delete_clones_after_indexing: bool = True

    # CORS
    cors_origins: list[str] = ["*"]

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_per_second: float = 10.0
    rate_limit_burst: int = 500

    # Webhooks
    webhook_secret: str = ""

    model_config = {"env_prefix": "EIDOS_", "env_file": str(_ENV_FILE)}

    @property
    def db_driver(self) -> str:
        """Extract the dialect+driver from the database URL (e.g. 'postgresql+asyncpg')."""
        return self.database_url.split("://")[0] if "://" in self.database_url else ""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.demo_mode:
            self.in_memory_db = True
            self.auth_enabled = False
            self.rate_limit_enabled = False


settings = Settings()
