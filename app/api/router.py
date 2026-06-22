"""
API 라우터 — POST /ai/v1/analyze, POST /ai/v1/analyze/batch
"""

import time

from fastapi import APIRouter, HTTPException

from app.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    ErrorResponse,
)
from app.services.analysis_service import analyze_single_log, analyze_batch_logs

router = APIRouter(prefix="/ai/v1", tags=["분석"])

BATCH_MAX_SIZE = 500


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="로그 1건 분석",
    responses={400: {"model": ErrorResponse}},
)
async def analyze_single(request: AnalyzeRequest) -> AnalyzeResponse:
    start = time.perf_counter()
    result = await analyze_single_log(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return AnalyzeResponse(
        log_id=request.log_id,
        result=result,
        processing_time_ms=elapsed_ms,
    )


@router.post(
    "/analyze/batch",
    response_model=BatchAnalyzeResponse,
    summary="로그 다건 분석",
    responses={413: {"model": ErrorResponse}},
)
async def analyze_batch(request: BatchAnalyzeRequest) -> BatchAnalyzeResponse:
    if len(request.logs) > BATCH_MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail={
                "error_code": "BATCH_TOO_LARGE",
                "message": f"배치 건수 초과: {len(request.logs)}건 (최대 {BATCH_MAX_SIZE}건)",
            },
        )

    start = time.perf_counter()
    results = await analyze_batch_logs(request.logs)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return BatchAnalyzeResponse(
        total_count=len(request.logs),
        processing_time_ms=elapsed_ms,
        results=results,
    )