from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://eidos:eidos@localhost:5432/eidos"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    openai_api_key: str = ""
    repos_data_dir: str = "/data/repos"

    model_config = {"env_prefix": "EIDOS_", "env_file": ".env"}


settings = Settings()
