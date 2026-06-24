"""
LangGraph StateGraph 기반 분석 파이프라인.

step4_agent.md 4-1~4-7 설계를 구현한다.
START → [template] → [anomaly] ─(정상)──→ [llm] → [map] → END
                                └─(이상)──→ [cluster]  ──→ [llm] → [map] → END
                                └─(이상)──→ [node_info] ─┘

Tool 함수(동기 순수함수)는 asyncio.to_thread()로 래핑하여 이벤트 루프 블로킹을 방지한다.
graph는 모듈 레벨에서 1회 compile()하여 재사용한다.
"""

import asyncio
from datetime import datetime
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph

from app.agents.diagnosis_agent import run_diagnosis, run_normal_reason
from app.agents.tools.anomaly_classifier import Urgency, classify_anomaly
from app.agents.tools.cluster import assign_cluster
from app.agents.tools.event_template import extract_event_template
from app.agents.tools.node_info import NodeInfoResult, get_node_info
from app.schemas.analysis import AnalyzeRequest, AnalyzeResult, RiskLevel

KST = ZoneInfo("Asia/Seoul")

# Tool② 영문 Urgency → 한글 RiskLevel 변환맵
_URGENCY_KO: dict[Urgency, RiskLevel] = {
    Urgency.CRITICAL: "긴급",
    Urgency.HIGH: "높음",
    Urgency.MID: "보통",
    Urgency.LOW: "낮음",
}


# ──────────────────────────────────────────────
# State 정의 (step4_agent.md 4-1)
# ──────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    # 입력 (요청 원본 — AnalyzeRequest 객체를 그대로 보관)
    log: Any  # AnalyzeRequest (TypedDict은 Pydantic 모델을 직접 타입 힌트 못함)
    # ① 산출
    event_id: str
    event_template: str | None
    template_matched: bool
    # ② 산출 (분기 기준)
    is_anomaly: bool
    urgency: str          # 영문 Critical/High/Mid/Low
    category: str | None
    impact: str | None    # LLM 프롬프트 컨텍스트용
    action_ctx: str | None  # ②의 action (LLM 컨텍스트용, 최종 action과 구분)
    # ③ 산출 (이상 경로)
    cluster_id: int
    cluster_matched: bool
    cluster_ctx: str       # _format_cluster_ctx 결과 문자열 (LLM 프롬프트용)
    # ④ 산출 (이상 경로)
    node_ctx: str         # _format_node_ctx 결과 문자열
    # LLM 산출
    summary: str
    analysis: str
    action: str
    reason: str
    # 매핑 결과
    status: str           # "정상" / "이상"
    risk_level: str | None  # 한글 RiskLevel or None
    result: dict | None   # 최종 AnalyzeResult 데이터 (dict로 직렬화)


# ──────────────────────────────────────────────
# 노드 헬퍼
# ──────────────────────────────────────────────

def _format_node_ctx(info: NodeInfoResult) -> str:
    """NodeInfoResult → LLM 컨텍스트 문자열 변환."""
    parts: list[str] = []
    md = info.node_metadata
    if md.rack:
        parts.append(f"Rack: {md.rack}")
    if md.midplane:
        parts.append(f"Midplane: {md.midplane}")
    if md.node_slot:
        parts.append(f"NodeSlot: {md.node_slot}")
    if md.node_role:
        parts.append(f"Role: {md.node_role}")
    if info.alert_stats:
        parts.append(f"AlertPct: {info.alert_stats.alert_pct:.1f}%")
    return " | ".join(parts) if parts else "(노드 정보 없음)"


def _format_cluster_ctx(result) -> str:
    """ClusterResult → LLM 프롬프트용 클러스터 컨텍스트 문자열.

    예: '클러스터 3 — 커널 종료/패닉군 — 커널 종료: 커널이 종료(terminated)되거나...'
    제목·설명이 없으면 '클러스터 {id} (설명 없음)' 반환.
    """
    cid = result.cluster_id
    title = result.cluster_title
    desc = result.description
    if title and desc:
        return f"클러스터 {cid} — {title}: {desc}"
    if title:
        return f"클러스터 {cid} — {title}"
    return f"클러스터 {cid} (설명 없음)"


# ──────────────────────────────────────────────
# 노드 구현 (step4_agent.md 4-2)
# ──────────────────────────────────────────────

async def template_node(state: AgentState) -> dict:
    """① 이벤트 템플릿 분류."""
    log: AnalyzeRequest = state["log"]
    result = await asyncio.to_thread(extract_event_template, log.content)
    return {
        "event_id": result.event_id,
        "event_template": result.event_template,
        "template_matched": result.matched,
    }


async def anomaly_node(state: AgentState) -> dict:
    """② 이상 여부 + 긴급도 분류. 분기 기준 노드."""
    ar = await asyncio.to_thread(classify_anomaly, state["event_id"])
    return {
        "is_anomaly": ar.is_anomaly,
        "urgency": ar.urgency.value,
        "category": ar.category,
        "impact": ar.impact,
        "action_ctx": ar.action,
    }


async def cluster_node(state: AgentState) -> dict:
    """③ 클러스터 분류 (이상 경로)."""
    result = await asyncio.to_thread(assign_cluster, state["event_id"])
    return {
        "cluster_id": result.cluster_id,
        "cluster_matched": result.matched,
        "cluster_ctx": _format_cluster_ctx(result),
    }


async def node_info_node(state: AgentState) -> dict:
    """④ Node 정보 조회 (이상 경로)."""
    log: AnalyzeRequest = state["log"]
    result = await asyncio.to_thread(get_node_info, log.node)
    return {
        "node_ctx": _format_node_ctx(result),
    }


async def llm_node(state: AgentState) -> dict:
    """LLM 분석 노드 — is_anomaly로 정상/이상 프롬프트 분기."""
    log: AnalyzeRequest = state["log"]
    event_id = state["event_id"]

    if not state["is_anomaly"]:
        # 정상 경로: 정상 사유만 작성
        # Tool② 산출값(category/impact)을 프롬프트 컨텍스트로 전달
        category = state.get("category") or "UNKNOWN"
        impact = state.get("impact") or ""
        llm_out = await run_normal_reason(log, event_id, category=category, impact=impact)
        return {
            "summary": llm_out["summary"],
            "analysis": llm_out["analysis"],
            "action": "",
            "reason": "",
        }

    # 이상 경로: ①②③④ 컨텍스트 + 원본 로그 → 이상 근거·대응 생성
    # Tool② 산출값(category/impact/action_ctx)을 프롬프트 컨텍스트로 전달
    risk_level = _URGENCY_KO.get(Urgency(state["urgency"]), "보통")
    node_ctx = state.get("node_ctx", "(노드 정보 없음)")
    cluster_ctx = state.get("cluster_ctx", f"클러스터 {state.get('cluster_id', 99)} (설명 없음)")
    category = state.get("category") or "UNKNOWN"
    impact = state.get("impact") or ""
    action_hint = state.get("action_ctx") or ""
    llm_out = await run_diagnosis(
        log, risk_level, cluster_ctx, event_id, node_ctx,
        category=category, impact=impact, action_hint=action_hint,
    )
    return {
        "summary": llm_out["summary"],
        "analysis": llm_out["analysis"],
        "action": llm_out["action"],
        "reason": llm_out.get("reason", ""),
    }


async def map_node(state: AgentState) -> dict:
    """결과 매핑 노드 — step4_agent.md 4-3 규칙대로 AnalyzeResult 조립."""
    is_anomaly = state["is_anomaly"]
    now = datetime.now(KST)

    if is_anomaly:
        risk_level: RiskLevel | None = _URGENCY_KO.get(
            Urgency(state["urgency"]), "보통"
        )
        # 이상인데 긴급도 비어있으면 안전 기본값
        risk_level = risk_level or "보통"
        event_id: str | None = state["event_id"]
        cluster_id: int | None = state.get("cluster_id", 99)
    else:
        risk_level = None
        event_id = None
        cluster_id = None

    status = "이상" if is_anomaly else "정상"

    analyze_result = AnalyzeResult(
        event_id=event_id,
        risk_level=risk_level,
        summary=state["summary"],
        analysis=state["analysis"],
        action=state["action"],
        cluster_id=cluster_id,
        analyzed_at=now,
    )
    return {
        "status": status,
        "risk_level": risk_level,
        "result": analyze_result.model_dump(),
    }


# ──────────────────────────────────────────────
# 조건부 분기 함수 (step4_agent.md 3-9)
# ──────────────────────────────────────────────

def route_by_anomaly(state: AgentState) -> str | list[str]:
    """②가 정상이면 llm 직행, 이상이면 cluster+node_info fan-out."""
    if state["is_anomaly"]:
        return ["cluster", "node_info"]
    return "llm"


# ──────────────────────────────────────────────
# 그래프 구성 (step4_agent.md 3-10~3-12)
# ──────────────────────────────────────────────

_builder = StateGraph(AgentState)
_builder.add_node("template", template_node)
_builder.add_node("anomaly", anomaly_node)
_builder.add_node("cluster", cluster_node)
_builder.add_node("node_info", node_info_node)
_builder.add_node("llm", llm_node)
_builder.add_node("map", map_node)

_builder.add_edge(START, "template")
_builder.add_edge("template", "anomaly")
_builder.add_conditional_edges("anomaly", route_by_anomaly, {
    "llm": "llm",
    "cluster": "cluster",
    "node_info": "node_info",
})
_builder.add_edge("cluster", "llm")
_builder.add_edge("node_info", "llm")
_builder.add_edge("llm", "map")
_builder.add_edge("map", END)

# 모듈 레벨에서 1회 compile — 매 요청마다 재생성하지 않음
graph = _builder.compile()
