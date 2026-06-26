"""
LangGraph StateGraph 기반 agentic tool-calling 분석 파이프라인.

LLM이 tool-calling 메커니즘(AIMessage.tool_calls → 툴 실행 → ToolMessage → 다시 LLM)으로
어떤 툴을 호출할지 결정하지만, 어떤 툴이 도느냐는 결정적이다.

핵심 장치 3가지:
(1) 내부 context tag("BGL")를 그래프 초기 state에 주입 → tag가 있으면 툴 호출이 강제됨.
(2) tool_choice 단계별 강제로 LLM이 필수 툴을 못 빠뜨리게 함.
(3) 사후 가드레일로 필수 툴 실행 여부를 검증하고 누락 시 결정적으로 보강 → AnalyzeResult 계약 보장.

LLM 라운드 절감 — classify 병합 + boost 병렬 처리:
  - classify 단계: classify_event 결합 툴로 ①②를 한 LLM 라운드에 수행.
  - boost 단계:   cluster + node_info를 하나의 LLM 라운드에 병렬 tool_calls로 처리.
  - 정상 경로:   classify(1) + reasoning(1) = 2회 LLM 라운드.
  - 이상 경로:   classify(1) + boost(cluster+node_info)(1) + reasoning(1) = 3회 LLM 라운드.

툴 실행 시 LLM이 준 인자 대신 state에서 도출한 정규(canonical) 인자로 실행한다:
  - classify_event → content = log.content
  - cluster        → event_id = state["event_id"]
  - node_info      → node_id  = log.node

tools_done 마커는 기존 이름을 유지한다:
  - classify_event 실행 시 "event_template", "anomaly_classifier" 둘 다 done에 추가.
  - cluster, node_info는 각각 이름 그대로 추가.

graph는 모듈 레벨에서 1회 compile()하여 재사용한다.
"""

import logging
from datetime import datetime
from typing import Annotated, Any, TypedDict
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agents.agent_tools import TOOLS
from app.agents.diagnosis_agent import run_diagnosis, run_normal_reason
from app.agents.prompts.diagnosis import AGENT_SYSTEM_PROMPT
from app.agents.tools.anomaly_classifier import Urgency, classify_anomaly
from app.agents.tools.cluster import assign_cluster
from app.agents.tools.event_template import extract_event_template
from app.agents.tools.node_info import NodeInfoResult, get_node_info
from app.core.config import get_settings
from app.schemas.analysis import AnalyzeRequest, AnalyzeResult, RiskLevel

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

# Tool② 영문 Urgency → 한글 RiskLevel 변환맵
_URGENCY_KO: dict[Urgency, RiskLevel] = {
    Urgency.CRITICAL: "긴급",
    Urgency.HIGH: "높음",
    Urgency.MID: "보통",
    Urgency.LOW: "낮음",
}

# 무한루프 방지: tools_done 최대 허용 길이
_MAX_TOOLS_DONE = 6

# BGL 컨텍스트 태그 (tool 강제 트리거)
_BGL_TAG = "BGL"


# ──────────────────────────────────────────────
# State 정의
# ──────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    # 입력 (요청 원본 — AnalyzeRequest 객체를 그대로 보관)
    log: Any  # AnalyzeRequest (TypedDict은 Pydantic 모델을 직접 타입 힌트 못함)
    # Agentic tool-calling 추가 필드
    messages: Annotated[list, add_messages]  # LangGraph 메시지 누적
    tag: str                                  # "BGL" 등 컨텍스트 태그
    tools_done: list[str]                     # 실행 완료된 툴 이름 목록
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


def _next_phase(state: AgentState) -> str | None:
    """tools_done 기준으로 다음 실행 단계를 반환한다.

    - "classify": classify_event(①②)를 아직 실행하지 않은 경우.
    - "boost":    이상 경로에서 cluster 또는 node_info가 아직 실행되지 않은 경우.
    - None:       모든 필수 단계 완료.

    tools_done 마커는 기존 이름(event_template, anomaly_classifier, cluster, node_info)을 사용한다.
    classify_event 실행 시 "event_template"과 "anomaly_classifier" 둘 다 done에 추가된다.
    """
    done = set(state.get("tools_done") or [])

    # ① 또는 ②가 없으면 classify 단계
    if "anomaly_classifier" not in done:
        return "classify"

    # 이상 경로에서 cluster/node_info 미완료 → boost 단계
    is_anomaly = state.get("is_anomaly", False)
    if is_anomaly and ("cluster" not in done or "node_info" not in done):
        return "boost"

    return None  # 완료


# ──────────────────────────────────────────────
# 입력 정규화 노드
# ──────────────────────────────────────────────

def ingest_node(state: AgentState) -> dict:
    """입력 정규화 노드 — Studio/직접 JSON 입력 호환용.

    - log가 dict(JSON)이면 AnalyzeRequest 객체로 변환해 이후 노드의 속성 접근을 보장한다.
    - FastAPI 경로는 이미 AnalyzeRequest 객체를 넘기므로 그대로 통과(무해).
    - Studio 편의: tag/messages/tools_done가 비어 있으면 기본값을 채워
      태그 없이 Submit해도 툴 호출 경로가 정상 동작하도록 한다.
    """
    updates: dict = {}

    log = state.get("log")
    if isinstance(log, dict):
        updates["log"] = AnalyzeRequest.model_validate(log)

    # Studio에서 tag를 빠뜨리면 agent_node가 '태그 없음'으로 조기 종료하므로 기본값 보강.
    if not state.get("tag"):
        updates["tag"] = _BGL_TAG
    if state.get("tools_done") is None:
        updates["tools_done"] = []

    return updates


# ──────────────────────────────────────────────
# LLM 팩토리 — 테스트가 monkeypatch할 수 있도록 별도 함수로 분리
# ──────────────────────────────────────────────

def _get_agent_llm():
    """Agent용 ChatOpenAI 인스턴스를 반환한다. bind_tools는 호출측에서 적용한다."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.openai_api_key.get_secret_value():
        raise RuntimeError(
            "OPENAI_API_KEY가 비어있습니다. .env에 키를 설정한 뒤 서버를 재시작하세요."
        )
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=settings.llm_temperature,
        max_completion_tokens=settings.llm_max_tokens,
        max_retries=settings.llm_max_retries,
    )


# ──────────────────────────────────────────────
# 노드 구현
# ──────────────────────────────────────────────

def agent_node(state: AgentState) -> dict:
    """Agent 노드 — 현재 단계(phase)에 맞는 tool_choice로 AIMessage를 생성한다.

    - classify 단계: classify_event 결합 툴을 강제해 ①②를 한 라운드에 수행한다.
    - boost 단계:   cluster + node_info를 병렬 tool_calls로 요청한다(tool_choice="required").
    - None(완료):   tool_calls 없는 AIMessage를 반환해 루프를 종료한다.

    tag가 'BGL'일 때만 툴을 강제한다.
    무한루프 방지를 위해 tools_done 길이가 _MAX_TOOLS_DONE 이상이면 강제 완료한다.
    """
    tools_done = state.get("tools_done") or []

    # 무한루프 방지
    if len(tools_done) >= _MAX_TOOLS_DONE:
        logger.warning("tools_done 상한(%d) 도달 — guard로 이동", _MAX_TOOLS_DONE)
        return {"messages": [AIMessage(content="[완료] 툴 상한 도달")]}

    tag = state.get("tag", "")
    if tag != _BGL_TAG:
        # tag가 없으면 강제하지 않음 — 완료 신호 후 guard로
        return {"messages": [AIMessage(content="[완료] BGL 태그 없음")]}

    phase = _next_phase(state)
    if phase is None:
        # 모든 필수 단계 완료 — 완료 신호
        logger.info("agent_node: 모든 필수 단계 완료 — guard로 이동")
        return {"messages": [AIMessage(content="[완료] 모든 필수 툴 실행 완료")]}

    logger.info("agent_node: phase=%s", phase)

    messages = list(state.get("messages") or [])

    # 메시지 시드: 첫 호출이면 SystemMessage + HumanMessage 추가
    if not messages:
        log: AnalyzeRequest = state["log"]
        seed_messages = [
            SystemMessage(content=AGENT_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"[태그] {tag}\n"
                    f"[로그 본문] {log.content}\n"
                    f"[노드] {log.node}\n"
                    "위 로그를 분석하세요. 먼저 classify_event 툴을 호출하세요."
                )
            ),
        ]
        messages = seed_messages

    if phase == "classify":
        # ①② 결합 툴을 한 라운드에 강제 호출
        llm = _get_agent_llm().bind_tools(TOOLS, tool_choice="classify_event")
        logger.info("agent_node: classify 단계 — classify_event 강제")

    else:  # phase == "boost"
        # cluster + node_info를 병렬로 요청 (LLM이 두 tool_call을 한 AIMessage에 실어 보냄)
        # 하나만/하나도 안 내도 guard가 사후 보강하므로 결정성 보장
        boost_hint = HumanMessage(
            content="cluster와 node_info 툴을 모두(병렬로) 호출하세요."
        )
        messages = list(messages) + [boost_hint]
        llm = _get_agent_llm().bind_tools(TOOLS, tool_choice="required")
        logger.info("agent_node: boost 단계 — cluster + node_info 병렬 요청")

    ai_message = llm.invoke(messages)
    return {"messages": [ai_message]}


def tool_exec_node(state: AgentState) -> dict:
    """툴 실행 노드 — 마지막 AIMessage의 tool_calls를 정규 인자로 직접 실행한다.

    LLM이 준 인자 대신 state에서 도출한 정규(canonical) 인자로 underlying 함수를 호출하여
    정확성을 보장한다. 각 결과를 state 구조화 필드에 기록하고 ToolMessage를 추가한다.

    classify_event 처리:
      - extract_event_template → classify_anomaly 순으로 내부 실행.
      - tools_done에 "event_template"과 "anomaly_classifier" 둘 다 추가.

    cluster + node_info는 하나의 AIMessage에 함께 올 수 있으며(병렬 tool_calls),
    루프가 둘 다 처리한 뒤 tools_done에 추가한다.
    """
    messages = state.get("messages") or []
    log: AnalyzeRequest = state["log"]

    # 마지막 AIMessage 찾기
    last_ai: AIMessage | None = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            last_ai = msg
            break

    if last_ai is None or not getattr(last_ai, "tool_calls", None):
        return {}

    updates: dict = {}
    tool_messages: list[ToolMessage] = []
    new_tools_done = list(state.get("tools_done") or [])

    for tc in last_ai.tool_calls:
        tool_name: str = tc["name"]
        tool_call_id: str = tc["id"]

        if tool_name == "classify_event":
            # 정규 인자: content = log.content
            # ① 이벤트 템플릿 분류
            template_result = extract_event_template(log.content)
            updates.update({
                "event_id": template_result.event_id,
                "event_template": template_result.event_template,
                "template_matched": template_result.matched,
            })
            logger.debug(
                "tool_exec[classify_event①]: event_id=%s, matched=%s",
                template_result.event_id, template_result.matched,
            )
            # ② 이상 여부 판정 (event_id는 방금 updates에 기록된 값 우선)
            anomaly_result = classify_anomaly(template_result.event_id)
            updates.update({
                "is_anomaly": anomaly_result.is_anomaly,
                "urgency": anomaly_result.urgency.value,
                "category": anomaly_result.category,
                "impact": anomaly_result.impact,
                "action_ctx": anomaly_result.action,
            })
            summary = (
                f"event_id={template_result.event_id}, matched={template_result.matched}, "
                f"is_anomaly={anomaly_result.is_anomaly}, urgency={anomaly_result.urgency.value}"
            )
            logger.debug("tool_exec[classify_event②]: is_anomaly=%s", anomaly_result.is_anomaly)
            # tools_done 마커: ①② 둘 다 완료 표시 (기존 테스트 단언과 호환)
            if "event_template" not in new_tools_done:
                new_tools_done.append("event_template")
            if "anomaly_classifier" not in new_tools_done:
                new_tools_done.append("anomaly_classifier")

        elif tool_name == "cluster":
            # 정규 인자: event_id = state["event_id"] (또는 방금 classify_event가 갱신한 값)
            event_id = updates.get("event_id") or state.get("event_id", "unknown")
            result = assign_cluster(event_id)
            updates.update({
                "cluster_id": result.cluster_id,
                "cluster_matched": result.matched,
                "cluster_ctx": _format_cluster_ctx(result),
            })
            summary = f"cluster_id={result.cluster_id}, matched={result.matched}"
            logger.debug("tool_exec[cluster]: %s", summary)
            if "cluster" not in new_tools_done:
                new_tools_done.append("cluster")

        elif tool_name == "node_info":
            # 정규 인자: node_id = log.node
            result = get_node_info(log.node)
            updates.update({
                "node_ctx": _format_node_ctx(result),
            })
            summary = f"node_ctx={updates['node_ctx']}"
            logger.debug("tool_exec[node_info]: %s", summary)
            if "node_info" not in new_tools_done:
                new_tools_done.append("node_info")

        else:
            summary = f"알 수 없는 툴: {tool_name}"
            logger.warning("tool_exec: 미등록 툴 '%s' 무시", tool_name)

        tool_messages.append(ToolMessage(content=summary, tool_call_id=tool_call_id))

    updates["tools_done"] = new_tools_done
    updates["messages"] = tool_messages
    return updates


def guard_node(state: AgentState) -> dict:
    """가드레일 노드 — 필수 툴이 실행되지 않았으면 결정적으로 직접 실행해 state를 채운다.

    이 노드 종료 시 event_id / is_anomaly는 반드시 채워진다.

    classify_event 병합 반영:
      - "event_template" 또는 "anomaly_classifier"가 done에 없으면
        extract_event_template + classify_anomaly를 결정적으로 보강하고
        "event_template", "anomaly_classifier" 둘 다 done에 추가한다.
    """
    log: AnalyzeRequest = state["log"]
    done = set(state.get("tools_done") or [])
    updates: dict = {}
    new_done = list(state.get("tools_done") or [])

    # event_template 미실행 → 결정적 보강
    if "event_template" not in done:
        result = extract_event_template(log.content)
        updates.update({
            "event_id": result.event_id,
            "event_template": result.event_template,
            "template_matched": result.matched,
        })
        new_done.append("event_template")
        logger.warning("guard_node: event_template 누락 — 결정적 보강 (event_id=%s)", result.event_id)

    # anomaly_classifier 미실행 → 결정적 보강
    if "anomaly_classifier" not in done:
        event_id = updates.get("event_id") or state.get("event_id", "unknown")
        result = classify_anomaly(event_id)
        updates.update({
            "is_anomaly": result.is_anomaly,
            "urgency": result.urgency.value,
            "category": result.category,
            "impact": result.impact,
            "action_ctx": result.action,
        })
        new_done.append("anomaly_classifier")
        logger.warning(
            "guard_node: anomaly_classifier 누락 — 결정적 보강 (is_anomaly=%s)",
            result.is_anomaly,
        )

    # is_anomaly 확정 후 cluster/node_info 검사
    is_anomaly = updates.get("is_anomaly", state.get("is_anomaly", False))

    if is_anomaly and "cluster" not in done:
        event_id = updates.get("event_id") or state.get("event_id", "unknown")
        result = assign_cluster(event_id)
        updates.update({
            "cluster_id": result.cluster_id,
            "cluster_matched": result.matched,
            "cluster_ctx": _format_cluster_ctx(result),
        })
        new_done.append("cluster")
        logger.warning(
            "guard_node: cluster 누락 — 결정적 보강 (cluster_id=%d)", result.cluster_id
        )

    if is_anomaly and "node_info" not in done:
        result = get_node_info(log.node)
        updates.update({
            "node_ctx": _format_node_ctx(result),
        })
        new_done.append("node_info")
        logger.warning("guard_node: node_info 누락 — 결정적 보강")

    if new_done != list(state.get("tools_done") or []):
        updates["tools_done"] = new_done

    return updates


async def reasoning_node(state: AgentState) -> dict:
    """추론 노드 — is_anomaly로 분기해 run_diagnosis 또는 run_normal_reason을 호출한다.

    기존 llm_node 역할 그대로 이식. category/impact/action_hint를 컨텍스트로 주입한다.
    """
    log: AnalyzeRequest = state["log"]
    event_id = state["event_id"]

    if not state["is_anomaly"]:
        # 정상 경로: 정상 사유만 작성
        category = state.get("category") or "UNKNOWN"
        impact = state.get("impact") or ""
        logger.info("reasoning_node: 정상 경로 (event_id=%s)", event_id)
        llm_out = await run_normal_reason(log, event_id, category=category, impact=impact)
        return {
            "summary": llm_out["summary"],
            "analysis": llm_out["analysis"],
            "action": "",
            "reason": "",
        }

    # 이상 경로: ①②③④ 컨텍스트 + 원본 로그 → 이상 근거·대응 생성
    risk_level = _URGENCY_KO.get(Urgency(state["urgency"]), "보통")
    node_ctx = state.get("node_ctx", "(노드 정보 없음)")
    cluster_ctx = state.get("cluster_ctx", f"클러스터 {state.get('cluster_id', 99)} (설명 없음)")
    category = state.get("category") or "UNKNOWN"
    impact = state.get("impact") or ""
    action_hint = state.get("action_ctx") or ""
    logger.info("reasoning_node: 이상 경로 (event_id=%s, risk_level=%s)", event_id, risk_level)
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
    """결과 매핑 노드 — AnalyzeResult 조립."""
    is_anomaly = state["is_anomaly"]
    now = datetime.now(KST)

    if is_anomaly:
        risk_level: RiskLevel | None = _URGENCY_KO.get(
            Urgency(state["urgency"]), "보통"
        )
        risk_level = risk_level or "보통"
        # 템플릿 미매칭(이상)도 정상과 동일하게 eventId=null로 정규화.
        # API.md 계약(str|null)에 "unknown"은 미정의 → 센티넬 대신 Tool① 플래그 사용.
        event_id: str | None = state["event_id"] if state.get("template_matched") else None
        cluster_id: int | None = state.get("cluster_id", 99)
    else:
        risk_level = None
        # 정상도 매칭된 event_id 반환; 미매칭 sentinel만 null
        event_id = state["event_id"] if state.get("template_matched") else None
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


# 기존 테스트에서 llm_node를 직접 호출하는 경우를 위한 alias
async def llm_node(state: AgentState) -> dict:
    """기존 llm_node alias — reasoning_node로 위임한다. (하위 호환용)"""
    return await reasoning_node(state)


# ──────────────────────────────────────────────
# 라우팅 함수
# ──────────────────────────────────────────────

def route_after_agent(state: AgentState) -> str:
    """agent_node 이후 라우팅.

    가장 마지막 메시지가 AIMessage이고 tool_calls가 있으면 'tools_exec'.
    그 외(ToolMessage가 마지막이거나, tool_calls 없는 AIMessage가 마지막)이면 'guard'.
    """
    messages = state.get("messages") or []

    # 무한루프 방지 — tools_done 상한 도달 시 guard로 강제 이동
    tools_done = state.get("tools_done") or []
    if len(tools_done) >= _MAX_TOOLS_DONE:
        return "guard"

    if not messages:
        return "guard"

    # 가장 마지막 메시지만 확인 (역방향 탐색 대신 끝 메시지 직접 확인)
    last_msg = messages[-1]
    if isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None):
        return "tools_exec"

    return "guard"


# ──────────────────────────────────────────────
# 그래프 구성
# ──────────────────────────────────────────────

_builder = StateGraph(AgentState)
_builder.add_node("ingest", ingest_node)
_builder.add_node("agent", agent_node)
_builder.add_node("tools_exec", tool_exec_node)
_builder.add_node("guard", guard_node)
_builder.add_node("reasoning", reasoning_node)
_builder.add_node("map", map_node)

_builder.add_edge(START, "ingest")
_builder.add_edge("ingest", "agent")
_builder.add_conditional_edges(
    "agent",
    route_after_agent,
    {"tools_exec": "tools_exec", "guard": "guard"},
)
_builder.add_edge("tools_exec", "agent")   # 툴 실행 후 agent로 다시 돌아와 루프
_builder.add_edge("guard", "reasoning")
_builder.add_edge("reasoning", "map")
_builder.add_edge("map", END)

# 모듈 레벨에서 1회 compile — 매 요청마다 재생성하지 않음
graph = _builder.compile()
