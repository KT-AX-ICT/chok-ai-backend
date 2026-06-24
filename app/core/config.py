from functools import lru_cache

from pydantic import Field, SecretStr
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
    # OPENAI_API_KEY는 prefix 없이 표준 이름 그대로 읽음
    # (validation_alias가 env_prefix를 무시함)
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="OPENAI_API_KEY",
    )
    # 모델은 CHOK_AI_LLM_MODEL 로 override 가능
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

    # ── 배치 처리 · 회복탄력성 ──────────────────
    batch_concurrency: int = 8          # 전역 asyncio.Semaphore 상한 (동시 LLM 호출 캡)
    batch_timeout_s: int = 300          # 전체 배치 타임아웃 (5분)
    llm_call_timeout_s: int = 60        # 개별 LLM 호출 타임아웃
    llm_max_retries: int = 6            # 지수 백오프 재시도 횟수 (429/5xx 대응)

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



