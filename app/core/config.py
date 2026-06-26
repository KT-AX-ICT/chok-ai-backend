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
    llm_model: str = "gpt-5-2025-08-07"
    # GPT-5 계열은 temperature 기본값(1)만 허용 — 다른 값 전달 시 API 에러.
    llm_temperature: float = 1.0
    llm_max_tokens: int = 2048  # 상세 analysis + 단계별 action 출력을 담기 위해 1024 → 2048 상향

    # ── 배치 처리 · 회복탄력성 ──────────────────
    batch_concurrency: int = 8          # 전역 asyncio.Semaphore 상한 (동시 LLM 호출 캡)
    batch_timeout_s: int = 300          # 전체 배치 타임아웃 (5분)
    llm_call_timeout_s: int = 60        # 개별 LLM 호출 타임아웃
    llm_max_retries: int = 6            # 지수 백오프 재시도 횟수 (429/5xx 대응)

    # ── 로깅 ─────────────────────────────────────
    # CHOK_AI_LOG_LEVEL 로 override 가능 (INFO/DEBUG/WARNING/ERROR)
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_file: str = "app.log"
    log_max_bytes: int = 10_485_760     # 10 MB
    log_backup_count: int = 5

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



