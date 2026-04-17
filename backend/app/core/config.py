from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://eidos:eidos@localhost:5432/eidos"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    openai_api_key: str = ""
    repos_data_dir: str = "/data/repos"

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

    # Data retention
    delete_clones_after_indexing: bool = True

    model_config = {"env_prefix": "EIDOS_", "env_file": ".env"}

    @property
    def db_driver(self) -> str:
        """Extract the dialect+driver from the database URL (e.g. 'postgresql+asyncpg')."""
        return self.database_url.split("://")[0] if "://" in self.database_url else ""


settings = Settings()
