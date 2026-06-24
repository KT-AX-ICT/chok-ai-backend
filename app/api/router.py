"""
API 라우터 — POST /ai/v1/analyze, POST /ai/v1/analyze/batch
"""

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
    start = time.perf_counter()
    event_id, status, result = await analyze_single_log(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return AnalyzeResponse(
        log_id=request.log_id,
        event_id=event_id,
        is_abnormal=(status == "이상"),   # 응답 경계에서 변환 (내부 status 유지)
        result=result,
        processing_time_ms=elapsed_ms,
    )


@router.post(
    "/analyze/batch",
    response_model=BatchAnalyzeResponse,
    summary="로그 다건 분석 (스케줄러 기본 경로, 최대 500건)",
    responses=_ERROR_RESPONSES,
)
async def analyze_batch(request: BatchAnalyzeRequest) -> BatchAnalyzeResponse:
    # 배치 건수 초과(>500)는 BatchAnalyzeRequest.max_length 검증으로 422 처리됨
    start = time.perf_counter()
    results = await analyze_batch_logs(request.logs)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return BatchAnalyzeResponse(
        total_count=len(request.logs),
        processing_time_ms=elapsed_ms,
        results=results,
    )
