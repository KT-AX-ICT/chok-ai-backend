"""
분석 파이프라인 오케스트레이션 — 서비스 계층
API.md §3 처리 흐름 기준

LangGraph StateGraph로 분석 흐름을 고정한다.
graph.ainvoke()로 단건 분석을 실행하고, 배치는 asyncio.gather로 병렬 처리한다.
동시성 캡(전역 Semaphore)과 배치 타임아웃으로 Tier 1 한도 내 안전 처리를 보장한다.
"""

import asyncio
import logging

from app.agents.graph import graph
from app.core.config import get_settings
from app.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResult,
    BatchItemResult,
    LogStatus,
    ProcessStatus,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 전역 LLM 동시성 캡
# ──────────────────────────────────────────────
# 모듈 레벨 전역 Semaphore — 동시 배치 요청이 들어와도 전체 LLM 동시 호출이
# batch_concurrency(기본 8)를 초과하지 않도록 제한한다.
# asyncio.Semaphore는 3.10+ 에서 특정 루프에 바인딩되지 않으므로 모듈 레벨 생성 OK.
_llm_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Lazy 생성 — TestClient가 새 루프를 만들어도 안전."""
    global _llm_semaphore
    if _llm_semaphore is None:
        settings = get_settings()
        _llm_semaphore = asyncio.Semaphore(settings.batch_concurrency)
    return _llm_semaphore


# ──────────────────────────────────────────────
# 단건 분석
# ──────────────────────────────────────────────

async def analyze_single_log(
    log: AnalyzeRequest,
) -> tuple[LogStatus, AnalyzeResult]:
    """
    단건 로그 분석 파이프라인. (status, result) 반환.
    LangGraph StateGraph를 ainvoke하여 Tool①②③④ + LLM + 결과매핑을 실행한다.
    """
    logger.info("단건 분석 시작 — log_id=%s", log.log_id)
    initial_state = {"log": log, "tag": "BGL", "messages": [], "tools_done": []}
    final_state = await graph.ainvoke(initial_state)

    status: LogStatus = final_state["status"]
    result_data = final_state["result"]
    result = AnalyzeResult.model_validate(result_data)
    logger.info(
        "단건 분석 완료 — log_id=%s, status=%s, isAbnormal=%s, eventId=%s, riskLevel=%s, clusterId=%s",
        log.log_id,
        status,
        status == "이상",
        result.event_id,
        result.risk_level,
        result.cluster_id,
    )
    return status, result


# ──────────────────────────────────────────────
# 배치 분석 — 동시성 캡 + 전체 타임아웃 + 개별 실패 격리
# ──────────────────────────────────────────────

async def analyze_batch_logs(logs: list[AnalyzeRequest]) -> list[BatchItemResult]:
    """각 로그를 동시에 처리. 전역 Semaphore로 LLM 동시 호출을 캡하고,
    전체 배치에 batch_timeout_s 타임아웃을 적용한다.
    개별 실패는 해당 항목만 fail 처리(_safe_analyze).
    전체 타임아웃 초과 시 asyncio.TimeoutError가 라우터로 전파되어 503 처리된다.
    """
    settings = get_settings()
    sem = _get_semaphore()
    logger.info(
        "배치 분석 시작 — 건수=%d, 동시성 상한=%d",
        len(logs),
        settings.batch_concurrency,
    )

    async def _limited(log: AnalyzeRequest) -> BatchItemResult:
        async with sem:
            return await _safe_analyze(log)

    results: list[BatchItemResult] = await asyncio.wait_for(
        asyncio.gather(*[_limited(log) for log in logs]),
        timeout=settings.batch_timeout_s,
    )

    success_count = sum(1 for r in results if r.process_status == ProcessStatus.SUCCESS)
    fail_count = len(results) - success_count
    logger.info(
        "배치 분석 완료 — 전체=%d, 성공=%d, 실패=%d",
        len(results),
        success_count,
        fail_count,
    )
    return results


async def _safe_analyze(log: AnalyzeRequest) -> BatchItemResult:
    """개별 로그 분석을 try/except로 감싸 실패를 격리한다."""
    try:
        status, result = await analyze_single_log(log)
        return BatchItemResult(
            log_id=log.log_id,
            process_status=ProcessStatus.SUCCESS,
            is_abnormal=(status == "이상"),   # 응답 경계에서 변환
            result=result,
        )
    except Exception as e:
        logger.error("log_id=%s 분석 실패: %s", log.log_id, e)
        return BatchItemResult(
            log_id=log.log_id,
            process_status=ProcessStatus.FAIL,
            error_message=type(e).__name__,
        )
