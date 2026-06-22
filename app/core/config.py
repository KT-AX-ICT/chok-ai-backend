from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CHOK AI Backend"
    app_description: str = "FastAPI service shell for AI log analysis workflows."
    app_version: str = "0.1.0"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    cors_methods: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    cors_headers: list[str] = [
        "Authorization",
        "Content-Type",
        "Accept",
        "X-Requested-With",
    ]
    cors_exposed_headers: list[str] = ["Authorization", "X-Process-Time"]
    cors_allow_credentials: bool = True
    cors_max_age: int = 3600

    # ── LLM ─────────────────────────────────────
    # ANTHROPIC_API_KEY는 prefix 없이 표준 이름 그대로 읽음
    # (validation_alias가 env_prefix를 무시함)
    anthropic_api_key: str = Field(
        default="",
        validation_alias="ANTHROPIC_API_KEY",
    )
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_temprature: float = 0.2
    llm_max_tokens: int = 1024

    model_config = SettingsConfigDict(
    )
    

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CHOK_AI_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()



