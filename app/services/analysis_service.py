"""
분석 파이프라인 오케스트레이션 — 서비스 계층
API.md §3 처리 흐름 기준

처리 흐름:
  AnalyzeRequest
    → ① classify_event_template()  → event_id
    → ② classify_status_urgency()  → status(정상/이상) · risk_level   [분기]
        · 정상 → run_normal_reason()  (③④·이상분석 LLM 생략, 정상 사유만)
        · 이상 → ③ classify_cluster() · ④ fetch_node_info() → run_diagnosis()
    → AnalyzeResult 조립 (analyzed_at = KST)

Tool ①~④는 데이터 분석팀이 구현. 여기서는 연결 stub만 두고 TODO로 표시한다.
"""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents.diagnosis_agent import run_diagnosis, run_normal_reason
from app.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResult,
    BatchItemResult,
    LogStatus,
    ProcessStatus,
    RiskLevel,
)

KST = ZoneInfo("Asia/Seoul")
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 단건 분석
# ──────────────────────────────────────────────

async def analyze_single_log(
    log: AnalyzeRequest,
) -> tuple[str, LogStatus, AnalyzeResult]:
    """
    단건 로그 분석 파이프라인. (event_id, status, result) 반환.
    event_id·status·risk_level·cluster_id는 결정적 Tool 산출 → LLM 재판단 금지.
    """
    event_id = await classify_event_template(log)              # Tool ①
    status, risk_level = await classify_status_urgency(log, event_id)  # Tool ② (분기)
    now = datetime.now(KST)

    # ── 정상 분기: ③④ 생략, 정상 사유만 작성 ──
    if status == "정상":
        normal = await run_normal_reason(log, event_id)
        result = AnalyzeResult(
            domain="",
            risk_level=None,
            summary=normal["summary"],
            analysis=normal["analysis"],
            action="",
            cluster_id=None,
            analyzed_at=now,
        )
        return event_id, status, result

    # ── 이상 분기: ③ 클러스터 · ④ 노드정보 동시 조회 후 LLM ──
    # 이상인데 Tool②가 긴급도를 비워 보낸 경우 안전 기본값으로 보정 (None 방지)
    risk_level = risk_level or "보통"
    cluster_id, node_ctx = await asyncio.gather(
        classify_cluster(log, event_id),                       # Tool ③
        fetch_node_info(log),                                  # Tool ④
    )
    llm = await run_diagnosis(log, risk_level, cluster_id, event_id, node_ctx)
    result = AnalyzeResult(
        domain="BGL",
        risk_level=risk_level,
        summary=llm["summary"],
        analysis=llm["analysis"],
        action=llm["action"],
        cluster_id=cluster_id,
        analyzed_at=now,
    )
    return event_id, status, result


# ──────────────────────────────────────────────
# 배치 분석 — 로그별 동시 처리, 개별 실패 격리
# ──────────────────────────────────────────────

async def analyze_batch_logs(logs: list[AnalyzeRequest]) -> list[BatchItemResult]:
    """각 로그를 동시에 처리. 개별 실패는 해당 항목만 fail 처리."""
    return await asyncio.gather(*[_safe_analyze(log) for log in logs])


async def _safe_analyze(log: AnalyzeRequest) -> BatchItemResult:
    """개별 로그 분석을 try/except로 감싸 실패를 격리한다."""
    try:
        event_id, status, result = await analyze_single_log(log)
        return BatchItemResult(
            log_id=log.log_id,
            event_id=event_id,
            process_status=ProcessStatus.SUCCESS,
            is_abnormal=(status == "이상"),   # 응답 경계에서 변환
            result=result,
        )
    except Exception as e:
        logger.error("log_id=%s 분석 실패: %s", log.log_id, e)
        return BatchItemResult(
            log_id=log.log_id,
            process_status=ProcessStatus.FAIL,
            error=type(e).__name__,
        )


# ──────────────────────────────────────────────
# Tool 연결부 — 데이터 분석팀 구현 예정 (현재 stub)
# ──────────────────────────────────────────────

async def classify_event_template(log: AnalyzeRequest) -> str:
    """Tool ① 이벤트 템플릿 분류 → event_id (규칙 기반).

    TODO: 데이터팀 템플릿 매칭 Tool 연동.
    """
    return "E00"


async def classify_status_urgency(
    log: AnalyzeRequest,
    event_id: str,
) -> tuple[LogStatus, RiskLevel | None]:
    """Tool ② 이상 여부 + 긴급도 분류 (이벤트 템플릿 기반). 분기 기준.

    정상이면 risk_level은 None. TODO: 데이터팀 Tool 연동.
    """
    urgency: dict[str, RiskLevel] = {
        "FATAL": "긴급",
        "FAILURE": "긴급",
        "SEVERE": "높음",
        "ERROR": "높음",
        "WARNING": "보통",
        "INFO": "낮음",
    }
    # stub: 현재는 모두 이상으로 간주 (실제 정상/이상 판정은 Tool② 연동 후)
    return "이상", urgency.get(log.log_level.upper(), "보통")


async def classify_cluster(log: AnalyzeRequest, event_id: str) -> int:
    """Tool ③ 클러스터(패턴) 분류 → cluster_id (이벤트 템플릿 기반).

    TODO: 데이터팀 패턴 군집화 Tool 연동.
    """
    return 0


async def fetch_node_info(log: AnalyzeRequest) -> str:
    """Tool ④ 노드별 정보 조회 → LLM 분석 컨텍스트.

    TODO: 데이터팀 노드 정보 조회 Tool 연동.
    """
    return "(노드 정보 없음 — Tool④ 연동 전)"
