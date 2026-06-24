"""
API 라우터 — POST /ai/v1/analyze, POST /ai/v1/analyze/batch
"""

import logging
import time
from typing import Any

from fastapi import APIRouter

from app.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    ErrorResponse,
)
from app.services.analysis_service import analyze_batch_logs, analyze_single_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/v1", tags=["분석"])

# 공통 에러 응답 (API.md §6)
# FastAPI responses 파라미터 타입(dict[int|str, dict[str, Any]])에 맞춰 명시 주석
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "요청 스키마 검증 실패"},
    502: {"model": ErrorResponse, "description": "LLM 호출 실패"},
    503: {"model": ErrorResponse, "description": "LLM 응답 지연/타임아웃"},
    500: {"model": ErrorResponse, "description": "내부 처리 오류"},
}


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="로그 1건 분석 (수동 / 개별 재처리용)",
    responses=_ERROR_RESPONSES,
)
async def analyze_single(request: AnalyzeRequest) -> AnalyzeResponse:
    logger.info("단건 분석 요청 수신 — log_id=%s", request.log_id)
    start = time.perf_counter()
    status, result = await analyze_single_log(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info("단건 분석 완료 — log_id=%s, elapsed_ms=%d", request.log_id, elapsed_ms)

    return AnalyzeResponse(
        log_id=request.log_id,
        is_abnormal=(status == "이상"),   # 응답 경계에서 변환 (내부 status 유지)
        result=result,                    # eventId는 result 내부에 포함
        processing_time_ms=elapsed_ms,
    )


@router.post(
    "/analyze/batch",
    response_model=BatchAnalyzeResponse,
    summary="로그 다건 분석 (스케줄러 기본 경로, 최대 400건)",
    responses=_ERROR_RESPONSES,
)
async def analyze_batch(request: BatchAnalyzeRequest) -> BatchAnalyzeResponse:
    # 배치 건수 초과(>400)는 BatchAnalyzeRequest.max_length 검증으로 422 처리됨
    logger.info("배치 분석 요청 수신 — 건수=%d", len(request.logs))
    start = time.perf_counter()
    results = await analyze_batch_logs(request.logs)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info("배치 분석 완료 — 건수=%d, elapsed_ms=%d", len(request.logs), elapsed_ms)

    return BatchAnalyzeResponse(
        total_count=len(request.logs),
        processing_time_ms=elapsed_ms,
        results=results,
    )
