"""
분석 endpoint 흐름 회귀 테스트 — POST /ai/v1/analyze, /analyze/batch

LLM/Tool은 monkeypatch로 대체해 외부(OpenAI) 호출 없이 계약을 검증한다.
검증 대상: camelCase 직렬화·status(정상/이상) 분기·KST 포맷·에러 매핑(422/502/503)·배치 부분 실패.

[agentic 경로 mock 전략]
_get_agent_llm을 monkeypatch해서 FakeLLM을 주입한다.
FakeLLM.bind_tools(tools, tool_choice=...) 분기:
  - tool_choice == "classify_event" → classify_event tool_call 1개 담은 AIMessage 반환.
  - tool_choice in ("required","any","auto") → cluster + node_info tool_call 2개 담은 AIMessage 반환(boost 단계).
  - 그 외 특정 툴 이름 → 해당 tool_call 1개.
실제 OpenAI를 호출하지 않고 tool_exec_node가 정규 인자로 실행하도록 한다.
"""

import re
import uuid

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.core.errors import LLMError, LLMTimeoutError
from app.main import app

client = TestClient(app, raise_server_exceptions=False)

# KST "yyyy-MM-dd HH:mm:ss"
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

# 그래프 모듈 경로 (monkeypatch 대상 — Tool/LLM 호출은 graph.py에서 발생)
GRAPH = "app.agents.graph"


# ──────────────────────────────────────────────
# Fake LLM — _get_agent_llm monkeypatch용
# ──────────────────────────────────────────────

class FakeBoundLLM:
    """bind_tools(tool_choice=...) 결과.

    tool_choice 분기:
      - "classify_event" → classify_event tool_call 1개 (classify 단계)
      - "required"/"any"/"auto" → cluster + node_info tool_call 2개 (boost 단계)
      - 그 외 → 해당 이름 1개
    tool_exec_node는 정규 인자를 사용하므로 args는 무시된다.
    """

    def __init__(self, tool_choice: str) -> None:
        self._tool_choice = tool_choice

    def invoke(self, messages) -> AIMessage:
        choice = self._tool_choice

        if choice in ("required", "any", "auto"):
            # boost 단계: cluster + node_info를 한 AIMessage에 담아 병렬 tool_calls 시뮬레이션
            tool_calls = [
                {
                    "name": "cluster",
                    "args": {},
                    "id": f"call_cluster",
                    "type": "tool_call",
                },
                {
                    "name": "node_info",
                    "args": {},
                    "id": f"call_node_info",
                    "type": "tool_call",
                },
            ]
        else:
            # classify_event 또는 특정 툴 이름 1개
            tool_calls = [
                {
                    "name": choice,
                    "args": {},
                    "id": f"call_{choice}",
                    "type": "tool_call",
                }
            ]

        return AIMessage(content="", tool_calls=tool_calls)


class FakeLLM:
    """_get_agent_llm() 반환값. bind_tools(tools, tool_choice=...) 호출을 가로챈다."""

    def bind_tools(self, tools, *, tool_choice: str | None = None, **kwargs) -> FakeBoundLLM:
        if tool_choice is None:
            tool_choice = "classify_event"
        return FakeBoundLLM(tool_choice)


# ──────────────────────────────────────────────
# 공통 헬퍼
# ──────────────────────────────────────────────

def make_log(log_id: int = 10293, log_level: str = "FATAL") -> dict:
    return {
        "logId": log_id,
        "node": "R04-M1-N4",
        "nodeRepeat": "R04-M1-N4",
        "component": "APP",
        "logType": "RAS",
        "occurredAt": "2005-06-04 00:24:32",
        "domain": "BGL",
        "logLevel": log_level,
        # Tool① 템플릿 E33(ciod 제어 스트림 실패) → Tool③ cluster 2 에 매칭되는 본문
        "content": (
            "ciod: failed to read message prefix on control stream "
            "(CioStream socket to 172.16.96.116:33425"
        ),
    }


async def _fake_diagnosis(*args, **kwargs) -> dict:
    return {
        "summary": "요약",
        "analysis": "분석",
        "action": "대응",
        "reason": "근거",
    }


async def _fake_normal_reason(*args, **kwargs) -> dict:
    return {
        "summary": "정상 사유 요약",
        "analysis": "정상 사유 근거",
    }


# ──────────────────────────────────────────────
# 단건 — 이상 경로
# ──────────────────────────────────────────────

def test_analyze_abnormal_success(monkeypatch) -> None:
    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", _fake_diagnosis)

    r = client.post("/ai/v1/analyze", json=make_log_with_content("data storage interrupt", log_id=10293))
    assert r.status_code == 200
    body = r.json()

    # 최상위 camelCase 계약
    assert body["logId"] == 10293
    assert body["isAbnormal"] is True
    assert isinstance(body["processingTimeMs"], int)

    result = body["result"]
    assert result["eventId"] == "E52"              # known 이상 event → eventId 채워짐
    assert result["riskLevel"] == "긴급"           # E52 → Critical → 긴급
    assert result["summary"] == "요약"
    assert result["action"] == "대응"
    assert result["clusterId"] == 0                # E52 → Tool③ cluster 0
    assert TS_RE.match(result["analyzedAt"])       # KST 포맷


# ──────────────────────────────────────────────
# 단건 — 템플릿 미매칭 (eventId=null, cluster=미분류)
# ──────────────────────────────────────────────

def test_analyze_unmatched_template_event_id_null(monkeypatch) -> None:
    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", _fake_diagnosis)

    log = make_log()
    log["content"] = "totally novel fatal message never seen before"
    r = client.post("/ai/v1/analyze", json=log)
    assert r.status_code == 200
    body = r.json()

    assert body["result"]["eventId"] is None       # 미매칭 → null (bgl_log.event_id NULL 허용)
    assert body["result"]["clusterId"] == 99        # 미분류 버킷


# ──────────────────────────────────────────────
# 단건 — 정상 경로 (FATAL→정상)
# ──────────────────────────────────────────────

def test_analyze_normal_path(monkeypatch) -> None:
    from app.agents.tools.anomaly_classifier import AnomalyResult, Urgency

    def fake_classify_anomaly(event_id):
        return AnomalyResult(
            event_id=event_id,
            is_anomaly=False,
            urgency=Urgency.LOW,
            category="APP",
            impact="정상 동작",
            action=None,
        )

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.classify_anomaly", fake_classify_anomaly)
    monkeypatch.setattr(f"{GRAPH}.run_normal_reason", _fake_normal_reason)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 200
    body = r.json()

    assert body["isAbnormal"] is False
    result = body["result"]
    assert result["eventId"] is None               # 정상 → null
    assert result["riskLevel"] is None             # 정상 → null
    assert result["clusterId"] is None             # 정상 → null
    assert result["action"] == ""                  # 정상 → ""
    assert result["summary"] == "정상 사유 요약"
    assert TS_RE.match(result["analyzedAt"])


# ──────────────────────────────────────────────
# 단건 — 에러 매핑
# ──────────────────────────────────────────────

def test_analyze_validation_error() -> None:
    r = client.post("/ai/v1/analyze", json={"logId": 1})   # 필수 필드 누락
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_analyze_llm_error_maps_502(monkeypatch) -> None:
    async def boom(*a, **k):
        raise LLMError("호출 실패")

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", boom)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 502
    assert r.json()["code"] == "LLM_ERROR"


def test_analyze_llm_timeout_maps_503(monkeypatch) -> None:
    async def slow(*a, **k):
        raise LLMTimeoutError("타임아웃")

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", slow)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 503
    assert r.json()["code"] == "LLM_TIMEOUT"


# ──────────────────────────────────────────────
# 배치 — 부분 실패 격리
# ──────────────────────────────────────────────

def test_batch_partial_failure(monkeypatch) -> None:
    async def diagnosis_by_id(log, *a, **k):
        if log.log_id == 2:
            raise LLMError("이 건만 실패")
        return {"summary": "요약", "analysis": "분석", "action": "대응", "reason": "근거"}

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", diagnosis_by_id)

    payload = {"logs": [make_log(1), make_log(2), make_log(3)]}
    r = client.post("/ai/v1/analyze/batch", json=payload)
    assert r.status_code == 200
    body = r.json()

    assert body["totalCount"] == 3
    by_id = {item["logId"]: item for item in body["results"]}

    assert by_id[1]["processStatus"] == "success"
    assert by_id[1]["isAbnormal"] is True
    assert by_id[1]["result"] is not None

    assert by_id[2]["processStatus"] == "fail"
    assert by_id[2]["errorMessage"] == "LLMError"
    assert by_id[2]["result"] is None


def test_batch_empty_is_422() -> None:
    r = client.post("/ai/v1/analyze/batch", json={"logs": []})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("size", [401, 500])
def test_batch_over_limit_is_422(size: int) -> None:
    payload = {"logs": [make_log(i) for i in range(size)]}
    r = client.post("/ai/v1/analyze/batch", json=payload)
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


# ──────────────────────────────────────────────
# 분기 테스트 — agentic 경로에서 cluster/node_info 실행 여부
# ──────────────────────────────────────────────

def test_branch_normal_skips_cluster_and_node_info(monkeypatch) -> None:
    """정상(is_anomaly=False) 경로: cluster·node_info 가 실행되지 않는다.

    classify_anomaly를 is_anomaly=False 반환으로, assign_cluster·get_node_info를 spy로,
    _get_agent_llm을 FakeLLM으로 monkeypatch한 뒤 cluster/node_info 호출 횟수 0을 assert한다.
    """
    from app.agents.tools.anomaly_classifier import AnomalyResult, Urgency

    # 정상 판정으로 고정
    def fake_classify_anomaly(event_id):
        return AnomalyResult(
            event_id=event_id,
            is_anomaly=False,
            urgency=Urgency.LOW,
            category="APP",
            impact="정상 동작",
            action=None,
        )

    cluster_calls: list[str] = []
    node_info_calls: list[str] = []

    def spy_assign_cluster(event_id):
        cluster_calls.append(event_id)
        from app.agents.tools.cluster import ClusterResult
        return ClusterResult(cluster_id=99, matched=False)

    def spy_get_node_info(node_id):
        node_info_calls.append(node_id)
        from app.agents.tools.node_info import NodeInfoResult, NodeMetadata
        return NodeInfoResult(
            node_metadata=NodeMetadata(),
            alert_stats=None,
        )

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.classify_anomaly", fake_classify_anomaly)
    monkeypatch.setattr(f"{GRAPH}.assign_cluster", spy_assign_cluster)
    monkeypatch.setattr(f"{GRAPH}.get_node_info", spy_get_node_info)
    monkeypatch.setattr(f"{GRAPH}.run_normal_reason", _fake_normal_reason)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 200
    assert r.json()["isAbnormal"] is False

    assert cluster_calls == [], f"정상 경로에서 assign_cluster가 {len(cluster_calls)}회 호출됨"
    assert node_info_calls == [], f"정상 경로에서 get_node_info가 {len(node_info_calls)}회 호출됨"


def test_branch_anomaly_runs_cluster_and_node_info(monkeypatch) -> None:
    """이상(is_anomaly=True) 경로: cluster·node_info 가 각 1회 실행된다.

    classify_anomaly를 is_anomaly=True 반환으로, assign_cluster·get_node_info를 spy로,
    _get_agent_llm을 FakeLLM으로 monkeypatch한 뒤 각 1회 호출됨을 assert한다.
    """
    from app.agents.tools.anomaly_classifier import AnomalyResult, Urgency

    # 이상 판정으로 고정
    def fake_classify_anomaly(event_id):
        return AnomalyResult(
            event_id=event_id,
            is_anomaly=True,
            urgency=Urgency.CRITICAL,
            category="HARDWARE",
            impact="하드웨어 장애",
            action="서버 점검",
        )

    cluster_calls: list[str] = []
    node_info_calls: list[str] = []

    def spy_assign_cluster(event_id):
        cluster_calls.append(event_id)
        from app.agents.tools.cluster import ClusterResult
        return ClusterResult(cluster_id=0, matched=True)

    def spy_get_node_info(node_id):
        node_info_calls.append(node_id)
        from app.agents.tools.node_info import NodeInfoResult, NodeMetadata
        return NodeInfoResult(
            node_metadata=NodeMetadata(rack="R04"),
            alert_stats=None,
        )

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.classify_anomaly", fake_classify_anomaly)
    monkeypatch.setattr(f"{GRAPH}.assign_cluster", spy_assign_cluster)
    monkeypatch.setattr(f"{GRAPH}.get_node_info", spy_get_node_info)
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", _fake_diagnosis)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 200
    assert r.json()["isAbnormal"] is True

    assert len(cluster_calls) == 1, f"이상 경로에서 assign_cluster 호출 횟수: {len(cluster_calls)} (기대: 1)"
    assert len(node_info_calls) == 1, f"이상 경로에서 get_node_info 호출 횟수: {len(node_info_calls)} (기대: 1)"


# ──────────────────────────────────────────────
# Agentic 경로 — tools_done 검증
# ──────────────────────────────────────────────

def test_agentic_normal_tools_done(monkeypatch) -> None:
    """정상 경로: tools_done에 event_template, anomaly_classifier만 포함되고
    cluster/node_info는 포함되지 않는다. 응답은 is_abnormal=False.
    """
    from app.agents.tools.anomaly_classifier import AnomalyResult, Urgency

    def fake_classify_anomaly(event_id):
        return AnomalyResult(
            event_id=event_id,
            is_anomaly=False,
            urgency=Urgency.LOW,
            category="APP",
            impact="정상 동작",
            action=None,
        )

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.classify_anomaly", fake_classify_anomaly)
    monkeypatch.setattr(f"{GRAPH}.run_normal_reason", _fake_normal_reason)

    # 최종 state를 꺼내기 위해 graph를 직접 호출
    import asyncio

    import app.agents.graph as _graph
    from app.schemas.analysis import AnalyzeRequest

    log = AnalyzeRequest(
        log_id=1,
        node="R04-M1-N4",
        node_repeat="R04-M1-N4",
        component="APP",
        log_type="RAS",
        occurred_at="2005-06-04 00:24:32",
        log_level="FATAL",
        content="ciod: failed to read message prefix on control stream",
        domain="BGL",
    )

    state = asyncio.run(
        _graph.graph.ainvoke({
            "log": log,
            "tag": "BGL 로그 데이터",
            "messages": [],
            "tools_done": [],
        })
    )

    done = set(state["tools_done"])
    assert "event_template" in done, "event_template 미실행"
    assert "anomaly_classifier" in done, "anomaly_classifier 미실행"
    assert "cluster" not in done, f"정상 경로에서 cluster가 실행됨: {done}"
    assert "node_info" not in done, f"정상 경로에서 node_info가 실행됨: {done}"
    # state["is_anomaly"]로 직접 확인 (result는 model_dump() snake_case)
    assert state["is_anomaly"] is False


def test_agentic_anomaly_tools_done(monkeypatch) -> None:
    """이상 경로: tools_done에 event_template, anomaly_classifier, cluster, node_info
    4개 전부 포함된다. 응답 is_abnormal=True, eventId/riskLevel/clusterId가 채워진다.
    """
    from app.agents.tools.anomaly_classifier import AnomalyResult, Urgency

    def fake_classify_anomaly(event_id):
        return AnomalyResult(
            event_id=event_id,
            is_anomaly=True,
            urgency=Urgency.CRITICAL,
            category="HARDWARE",
            impact="하드웨어 장애",
            action="서버 점검",
        )

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.classify_anomaly", fake_classify_anomaly)
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", _fake_diagnosis)

    import asyncio

    import app.agents.graph as _graph
    from app.schemas.analysis import AnalyzeRequest

    log = AnalyzeRequest(
        log_id=1,
        node="R04-M1-N4",
        node_repeat="R04-M1-N4",
        component="APP",
        log_type="RAS",
        occurred_at="2005-06-04 00:24:32",
        log_level="FATAL",
        content="data storage interrupt",   # known 이상 event(E52) → eventId 채워짐
        domain="BGL",
    )

    state = asyncio.run(
        _graph.graph.ainvoke({
            "log": log,
            "tag": "BGL 로그 데이터",
            "messages": [],
            "tools_done": [],
        })
    )

    done = set(state["tools_done"])
    assert "event_template" in done, "event_template 미실행"
    assert "anomaly_classifier" in done, "anomaly_classifier 미실행"
    assert "cluster" in done, "이상 경로에서 cluster 미실행"
    assert "node_info" in done, "이상 경로에서 node_info 미실행"

    # 결과 계약 확인
    result_data = state["result"]
    from app.schemas.analysis import AnalyzeResult
    result = AnalyzeResult.model_validate(result_data)
    assert result.event_id is not None
    assert result.risk_level is not None
    assert result.cluster_id is not None


def test_agentic_cluster99_passthrough(monkeypatch) -> None:
    """이상 경로에서 cluster_id=99(미분류) passthrough 동작 확인.

    assign_cluster가 cluster_id=99를 반환할 때 result.clusterId=99가 그대로 전달된다.
    """
    from app.agents.tools.anomaly_classifier import AnomalyResult, Urgency

    def fake_classify_anomaly(event_id):
        return AnomalyResult(
            event_id=event_id,
            is_anomaly=True,
            urgency=Urgency.MID,
            category="UNKNOWN",
            impact="알 수 없는 이벤트",
            action="직접 확인",
        )

    def fake_assign_cluster(event_id):
        from app.agents.tools.cluster import ClusterResult
        return ClusterResult(cluster_id=99, matched=True)

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.classify_anomaly", fake_classify_anomaly)
    monkeypatch.setattr(f"{GRAPH}.assign_cluster", fake_assign_cluster)
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", _fake_diagnosis)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 200
    body = r.json()
    assert body["isAbnormal"] is True
    assert body["result"]["clusterId"] == 99


# ──────────────────────────────────────────────
# 가드레일 테스트
# ──────────────────────────────────────────────

def test_guard_node_fills_all_missing_tools(monkeypatch) -> None:
    """가드레일 테스트: agent LLM이 tool_calls 없는 빈 AIMessage만 반환해도
    guard_node가 결정적으로 모든 필수 툴을 보강해 계약(eventId 등)이 채워진다.
    """

    class EmptyFakeLLM:
        """tool_calls 없는 빈 AIMessage만 반환 — 툴을 전혀 호출하지 않음."""

        def bind_tools(self, tools, *, tool_choice=None, **kwargs):
            return self

        def invoke(self, messages) -> AIMessage:
            return AIMessage(content="직접 판단: 이상")

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: EmptyFakeLLM())
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", _fake_diagnosis)

    r = client.post("/ai/v1/analyze", json=make_log_with_content("data storage interrupt"))
    assert r.status_code == 200
    body = r.json()

    # guard_node가 모든 툴을 보강했으므로 계약이 채워져야 함
    assert body["isAbnormal"] is True   # known 이상 event(E52) → anomaly=True
    result = body["result"]
    assert result["eventId"] is not None    # guard가 event_template 보강
    assert result["riskLevel"] is not None  # guard가 anomaly_classifier 보강
    assert result["clusterId"] is not None  # guard가 cluster 보강
    assert result["summary"] == "요약"
    assert TS_RE.match(result["analyzedAt"])


def test_guard_node_normal_path_fills_required(monkeypatch) -> None:
    """가드레일 정상 경로 테스트: LLM이 툴을 호출하지 않아도
    guard_node가 event_template + anomaly_classifier를 보강하고,
    is_anomaly=False이면 cluster/node_info는 보강하지 않는다.
    """
    from app.agents.tools.anomaly_classifier import AnomalyResult, Urgency

    def fake_classify_anomaly(event_id):
        return AnomalyResult(
            event_id=event_id,
            is_anomaly=False,
            urgency=Urgency.LOW,
            category="APP",
            impact="정상 동작",
            action=None,
        )

    class EmptyFakeLLM:
        def bind_tools(self, tools, *, tool_choice=None, **kwargs):
            return self

        def invoke(self, messages) -> AIMessage:
            return AIMessage(content="")

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: EmptyFakeLLM())
    monkeypatch.setattr(f"{GRAPH}.classify_anomaly", fake_classify_anomaly)
    monkeypatch.setattr(f"{GRAPH}.run_normal_reason", _fake_normal_reason)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 200
    body = r.json()
    assert body["isAbnormal"] is False
    result = body["result"]
    assert result["eventId"] is None
    assert result["riskLevel"] is None
    assert result["clusterId"] is None


# ──────────────────────────────────────────────
# Phase 5-2: Tool 실연동 통합 테스트 (LLM만 fake)
# ──────────────────────────────────────────────

def make_log_with_content(content: str, node: str = "R04-M1-N4", log_id: int = 1) -> dict:
    """content·node를 지정할 수 있는 로그 생성 헬퍼."""
    return {
        "logId": log_id,
        "node": node,
        "nodeRepeat": node,
        "component": "APP",
        "logType": "RAS",
        "occurredAt": "2005-06-04 00:24:32",
        "domain": "BGL",
        "logLevel": "FATAL",
        "content": content,
    }


def test_tool_integration_known_event_anomaly(monkeypatch) -> None:
    """알려진 이상 event_id(E52 = 'data storage interrupt'): 실제 Tool①②③④ 연동 확인.

    LLM(run_diagnosis)만 fake로 교체. event_id, cluster_id, is_anomaly가 메타데이터
    기반으로 올바르게 채워짐을 검증한다.
    """
    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", _fake_diagnosis)

    r = client.post(
        "/ai/v1/analyze",
        json=make_log_with_content("data storage interrupt", node="R30-M0-N9-C:J16-U01"),
    )
    assert r.status_code == 200
    body = r.json()

    assert body["isAbnormal"] is True
    result = body["result"]
    assert result["eventId"] == "E52"          # Tool① 실연동 확인
    assert result["riskLevel"] == "긴급"       # E52 → Critical → 긴급
    assert isinstance(result["clusterId"], int) # Tool③ 실연동 확인 (cluster 0)
    assert result["clusterId"] == 0


def test_tool_integration_unknown_content_fallback(monkeypatch) -> None:
    """미등록 content → event_id=unknown → is_anomaly=True(Mid) fallback 동작 확인.

    LLM(run_diagnosis)만 fake. unknown event_id가 anomaly=True/Mid로 처리되고
    cluster_id=99(미분류)가 반환됨을 검증한다.
    """
    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", _fake_diagnosis)

    r = client.post(
        "/ai/v1/analyze",
        json=make_log_with_content("this is not a real bgl log at all"),
    )
    assert r.status_code == 200
    body = r.json()

    assert body["isAbnormal"] is True
    result = body["result"]
    assert result["eventId"] is None           # 미매칭(unknown) → 응답 null (명세 str|null)
    assert result["riskLevel"] == "보통"       # unknown → Mid → 보통 (유지)
    assert result["clusterId"] == 99           # Tool③ 미분류 (유지)


def test_tool_integration_known_event_normal(monkeypatch) -> None:
    """알려진 정상 event_id(E77 = 'instruction cache parity error corrected'): 정상 경로 확인.

    LLM(run_normal_reason)만 fake. is_anomaly=False, cluster/node_info 관련 필드가
    None임을 검증한다.
    """
    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.run_normal_reason", _fake_normal_reason)

    r = client.post(
        "/ai/v1/analyze",
        json=make_log_with_content(
            "instruction cache parity error corrected",
            node="R30-M0-N9-C:J16-U01",
        ),
    )
    assert r.status_code == 200
    body = r.json()

    assert body["isAbnormal"] is False
    result = body["result"]
    assert result["eventId"] is None
    assert result["riskLevel"] is None
    assert result["clusterId"] is None


# ──────────────────────────────────────────────
# Phase 5-3: 배치 동시성 상한 테스트 (Semaphore ≤ 8)
# ──────────────────────────────────────────────

def test_batch_concurrency_cap(monkeypatch) -> None:
    """20건 배치 처리 시 동시 실행 peak가 batch_concurrency(8) 이하임을 검증한다.

    run_diagnosis를 async spy로 교체해 진입/종료 시점에 카운터를 기록한다.
    전역 _llm_semaphore를 리셋해 테스트 간 상태 오염을 방지한다.
    """
    import asyncio as _asyncio

    import app.services.analysis_service as _svc

    # 전역 세마포어를 리셋 — 이전 테스트에서 생성된 세마포어가 남아 있으면
    # 카운트가 이미 소모된 상태일 수 있으므로 새로 생성하도록 초기화
    _svc._llm_semaphore = None

    concurrent = 0
    peak = 0

    async def spy_diagnosis(*args, **kwargs):
        nonlocal concurrent, peak
        concurrent += 1
        if concurrent > peak:
            peak = concurrent
        await _asyncio.sleep(0)   # 다른 코루틴에게 실행 기회를 양보
        concurrent -= 1
        return {"summary": "요약", "analysis": "분석", "action": "대응", "reason": "근거"}

    monkeypatch.setattr(f"{GRAPH}._get_agent_llm", lambda: FakeLLM())
    monkeypatch.setattr(f"{GRAPH}.run_diagnosis", spy_diagnosis)

    # 20건 배치 (전부 FATAL 기본 로그 → 이상 경로 → run_diagnosis 호출)
    payload = {"logs": [make_log(i) for i in range(1, 21)]}
    r = client.post("/ai/v1/analyze/batch", json=payload)
    assert r.status_code == 200

    body = r.json()
    assert body["totalCount"] == 20

    # 핵심 검증: 동시 실행 peak가 세마포어 상한(8) 이하
    assert peak <= 8, f"동시성 상한 초과: peak={peak} (상한: 8)"
    # 모든 건이 정상 처리됐는지 확인
    success_count = sum(1 for item in body["results"] if item["processStatus"] == "success")
    assert success_count == 20, f"성공 건수: {success_count}/20"


# ──────────────────────────────────────────────
# Phase D: Tool② impact/action/category → reasoning_node 주입 검증
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_node_passes_impact_to_run_diagnosis(monkeypatch) -> None:
    """이상 경로: reasoning_node(=llm_node alias)가 State의 impact/action_ctx/category를
    run_diagnosis 인자로 전달한다.

    run_diagnosis를 mock으로 교체한 뒤 call_args.kwargs에
    category/impact/action_hint 값이 올바르게 전달되는지 검증한다.
    """
    from unittest.mock import AsyncMock

    import app.agents.graph as _graph
    from app.schemas.analysis import AnalyzeRequest

    expected_return = {
        "summary": "요약",
        "analysis": "분석",
        "action": "대응",
        "reason": "근거",
    }
    mock_run = AsyncMock(return_value=expected_return)
    monkeypatch.setattr(_graph, "run_diagnosis", mock_run)

    log = AnalyzeRequest(
        log_id=1,
        node="R04-M1-N4",
        node_repeat="R04-M1-N4",
        component="APP",
        log_type="RAS",
        occurred_at="2005-06-04 00:24:32",
        log_level="FATAL",
        content="ciod: failed to read message prefix",
        domain="BGL",
    )

    state = {
        "log": log,
        "event_id": "E52",
        "is_anomaly": True,
        "urgency": "Critical",
        "category": "HARDWARE",
        "impact": "DDR 메모리 오류로 인한 노드 다운.",
        "action_ctx": "해당 노드 메모리 점검 및 교체",
        "cluster_id": 0,
        "cluster_ctx": "클러스터 0 — 커널 종료/패닉군",
        "node_ctx": "Rack: R04 | Role: compute",
    }

    # llm_node alias를 통해 호출 (하위 호환 검증)
    await _graph.llm_node(state)

    assert mock_run.called, "run_diagnosis가 호출되지 않았습니다."
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["impact"] == "DDR 메모리 오류로 인한 노드 다운."
    assert call_kwargs["action_hint"] == "해당 노드 메모리 점검 및 교체"
    assert call_kwargs["category"] == "HARDWARE"


@pytest.mark.asyncio
async def test_llm_node_passes_impact_to_run_normal_reason(monkeypatch) -> None:
    """정상 경로: reasoning_node(=llm_node alias)가 State의 impact/category를
    run_normal_reason 인자로 전달한다.

    run_normal_reason을 mock으로 교체한 뒤 call_args.kwargs에
    category/impact 값이 올바르게 전달되는지 검증한다.
    """
    from unittest.mock import AsyncMock

    import app.agents.graph as _graph
    from app.schemas.analysis import AnalyzeRequest

    expected_return = {
        "summary": "정상 사유 요약",
        "analysis": "정상 사유 근거",
    }
    mock_run = AsyncMock(return_value=expected_return)
    monkeypatch.setattr(_graph, "run_normal_reason", mock_run)

    log = AnalyzeRequest(
        log_id=2,
        node="R30-M0-N9-C:J16-U01",
        node_repeat="R30-M0-N9-C:J16-U01",
        component="APP",
        log_type="RAS",
        occurred_at="2005-06-04 01:00:00",
        log_level="FATAL",
        content="instruction cache parity error corrected",
        domain="BGL",
    )

    state = {
        "log": log,
        "event_id": "E77",
        "is_anomaly": False,
        "urgency": "Low",
        "category": "HARDWARE",
        "impact": "ECC 자동 정정됨. 단발성으로 정상 동작.",
        "action_ctx": None,
    }

    # llm_node alias를 통해 호출 (하위 호환 검증)
    await _graph.llm_node(state)

    assert mock_run.called, "run_normal_reason이 호출되지 않았습니다."
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["impact"] == "ECC 자동 정정됨. 단발성으로 정상 동작."
    assert call_kwargs["category"] == "HARDWARE"
