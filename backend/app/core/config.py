from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://eidos:eidos@localhost:5432/eidos"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    openai_api_key: str = ""
    repos_data_dir: str = "/data/repos"

    # LLM provider (any OpenAI-compatible endpoint)
    llm_base_url: str = ""  # e.g. "http://localhost:11434/v1" for Ollama
    llm_api_key: str = ""  # empty for local models
    llm_model: str = "gpt-4o-mini"  # provider-specific model name
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048
    llm_timeout: int = 60

    model_config = {"env_prefix": "EIDOS_", "env_file": ".env"}


settings = Settings()
