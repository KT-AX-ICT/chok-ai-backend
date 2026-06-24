"""
CHOK AI Backend — FastAPI 게이트웨이
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.middleware import add_process_time

from fastapi.exceptions import RequestValidationError

from app.api.router import router
from app.core.config import get_settings
from app.core.errors import (
    AppError,
    handle_app_error,
    handle_unexpected,
    handle_validation,
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    docs_url="/docs",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
    expose_headers=settings.cors_exposed_headers,
    allow_credentials=settings.cors_allow_credentials,
    max_age=settings.cors_max_age,
)

# X-Process-Time 헤더
app.middleware("http")(add_process_time)

# 전역 예외 핸들러 (core 위임) — 구체 → 일반 순
app.add_exception_handler(RequestValidationError, handle_validation)
app.add_exception_handler(AppError, handle_app_error)
app.add_exception_handler(Exception, handle_unexpected)

# 라우터 등록
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
