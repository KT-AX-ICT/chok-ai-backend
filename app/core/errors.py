"""
  공통 예외 핸들러 — 전역 500 응답
  스키마: app/schemas/analysis.py:ErrorResponse 와 키 일치
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
            """
            잡히지 않은 모든 예외를 처리한다.
            내부 예외 메시지는 로그에만 남기고 응답에는 노출하지 않는다.
            """
            logger.exception(
                "unexpected error on %s %s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error_code": "INTERNAL_ERROR",
                    "message": "처리되지 않은 서버 오류",
                    "detail": None,
                },
            )           