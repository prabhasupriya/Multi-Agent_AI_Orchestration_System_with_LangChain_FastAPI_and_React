"""
Centralized application configuration.

All configuration is sourced from environment variables (see .env.example
at the repository root). Using pydantic-settings gives us validation and
type coercion for free, and a single source of truth that every module
(FastAPI app, Celery worker, agent graph) imports from.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Core service URLs -------------------------------------------------
    DATABASE_URL: str = "postgresql+asyncpg://agent_user:agent_pass@db:5432/agent_db"
    REDIS_URL: str = "redis://redis:6379/0"

    # --- LLM provider --------------------------------------------------
    # "openai" or "anthropic". The rest of the app only ever calls
    # `get_llm()` from app.agents.llm, so switching providers here is
    # sufficient to change the reasoning engine used by every agent.
    LLM_PROVIDER: str = "openai"
    LLM_API_KEY: str = ""
    # Left empty by default on purpose: app.agents.llm.get_llm() picks a
    # sensible default MODEL per provider. If this were hardcoded to e.g.
    # "gpt-4o-mini", switching LLM_PROVIDER to "groq" without also setting
    # LLM_MODEL would silently try to call Groq with an OpenAI model name.
    LLM_MODEL: str = ""

    # --- Tool provider keys --------------------------------------------
    OPENWEATHER_API_KEY: str = ""
    BRAVE_SEARCH_API_KEY: str = ""

    # --- CORS --------------------------------------------------------------
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # --- Misc ----------------------------------------------------------
    TOOL_RESULT_TIMEOUT_SECONDS: int = 30
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
