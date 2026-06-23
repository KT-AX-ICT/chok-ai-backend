"""
예외 계층 + 전역 예외 핸들러
응답 스키마: app/schemas/analysis.py:ErrorResponse (code / message / detail) 와 키 일치
매핑 표: API.md §6
"""

import logging
from typing import cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 예외 계층
# ──────────────────────────────────────────────

class AppError(Exception):
    """애플리케이션 공통 예외. status_code / code / message 보유."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: str | None = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class LLMTimeoutError(AppError):
    status_code = 503
    code = "LLM_TIMEOUT"


class LLMError(AppError):          # 호출 실패 + 구조화 출력 파싱 실패
    status_code = 502
    code = "LLM_ERROR"


# ──────────────────────────────────────────────
# 핸들러
# ──────────────────────────────────────────────

def _error_body(code: str, message: str, detail: str | None) -> dict:
    return {"code": code, "message": message, "detail": detail}


async def handle_validation(request: Request, exc: Exception) -> JSONResponse:
    """요청 스키마 검증 실패 → 422 VALIDATION_ERROR."""
    err = cast(RequestValidationError, exc)
    return JSONResponse(
        status_code=422,
        content=_error_body("VALIDATION_ERROR", "요청 스키마 검증 실패", str(err.errors())),
    )


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    """도메인 예외(AppError 계열) → 각 예외가 보유한 status_code / code."""
    err = cast(AppError, exc)
    logger.warning("app error on %s %s: %s", request.method, request.url.path, err.message)
    return JSONResponse(
        status_code=err.status_code,
        content=_error_body(err.code, err.message, err.detail),
    )


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """잡히지 않은 모든 예외 → 500. 내부 메시지는 로그에만 남기고 응답 미노출."""
    logger.exception("unexpected error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=_error_body("INTERNAL_ERROR", "처리되지 않은 서버 오류", None),
    )
