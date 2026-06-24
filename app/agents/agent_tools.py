"""
LangChain Tool 래퍼 — bind_tools 스키마 제공용으로 노출한다.

그래프의 tool_exec_node는 이 툴의 본문 대신 정규(canonical) 인자로 underlying 함수를
직접 호출한다. 이 모듈은 bind_tools 스키마 제공 + 폴백 용도로만 사용된다.

LLM 라운드 절감을 위해 ①②를 classify_event로 병합했다:
  - classify_event: event_template(①) + anomaly_classifier(②)를 한 번에 수행.
  - cluster, node_info는 이상 경로 병렬 호출용으로 그대로 유지.

TOOLS = [classify_event, cluster, node_info]
"""

from langchain_core.tools import tool

from app.agents.tools.anomaly_classifier import classify_anomaly
from app.agents.tools.cluster import assign_cluster
from app.agents.tools.event_template import extract_event_template
from app.agents.tools.node_info import get_node_info


@tool
def classify_event(content: str) -> dict:
    """로그 본문(content)으로 이벤트 템플릿을 분류하고(①) 이어서 이상 여부·긴급도를 판정한다(②).
    event_id, event_template, template_matched, is_anomaly, urgency, category, impact, action을 반환한다."""
    # ① 이벤트 템플릿 분류
    template_result = extract_event_template(content)
    # ② 이상 여부 판정
    anomaly_result = classify_anomaly(template_result.event_id)
    return {
        "event_id": template_result.event_id,
        "event_template": template_result.event_template,
        "template_matched": template_result.matched,
        "is_anomaly": anomaly_result.is_anomaly,
        "urgency": anomaly_result.urgency.value,
        "category": anomaly_result.category,
        "impact": anomaly_result.impact,
        "action": anomaly_result.action,
    }


@tool
def cluster(event_id: str) -> dict:
    """event_id를 사전 정의된 장애 유형 클러스터에 배정한다.
    cluster_id, matched, cluster_title, description을 반환한다. 이상 경로에서만 호출한다."""
    result = assign_cluster(event_id)
    return result.model_dump()


@tool
def node_info(node_id: str) -> dict:
    """node_id로 노드의 하드웨어 위치(rack/midplane/slot/role)와 이상 발생 비율(alert_pct)을 조회한다.
    node_metadata와 alert_stats를 반환한다. 이상 경로에서만 호출한다."""
    result = get_node_info(node_id)
    return result.model_dump()


# ── 외부 공개 목록 ──────────────────────────────────────────────────────────
# classify_event: ①②를 한 라운드로 병합한 결합 툴
# cluster, node_info: 이상 경로 병렬 호출용
TOOLS = [classify_event, cluster, node_info]
TOOL_BY_NAME: dict[str, object] = {t.name: t for t in TOOLS}
