# Agent Tools

Agent가 사용하는 **결정적(rule/검색 기반) Tool** 구현을 둡니다. 각 Tool은 프레임워크(LangGraph 등)에
종속되지 않는 **순수 함수 + Pydantic 결과 모델**로 작성하고, 오케스트레이션 계층(`app/services`)이 노드로 감쌉니다.

> 입출력 **필드별 상세 설명은 각 결과 모델의 `Field(description=...)`** 가 단일 소스(source of truth)입니다.
> 이 문서는 개요·흐름·호출법만 다루며, 필드 의미는 코드를 참조하세요.

## Tool 요약

| Tool | 파일 | 진입 함수 | 입력 | 출력 모델 | 기능 |
| --- | --- | --- | --- | --- | --- |
| ① 이벤트 템플릿 분류 | `event_template.py` | `extract_event_template(content)` | 로그 `content: str` | `EventTemplateResult` | drain 템플릿 매칭으로 raw 로그 → `event_id` |
| ② 이상·긴급도 분류 | `anomaly_classifier.py` | `classify_anomaly(event_id)` | `event_id: str` | `AnomalyResult` | `event_id` → 이상 여부 + 긴급도 + 영향/조치 |
| ③ 클러스터 분류 | `cluster.py` | `assign_cluster(event_id)` | `event_id: str` | `ClusterResult` | `event_id` → 장애 유형군 `cluster_id` |
| ④ 노드 정보 조회 | `node_info.py` | `get_node_info(node_id)` | `node_id: str` | `NodeInfoResult` | `node_id` → 하드웨어 계층 + 과거 이상 비율 |

## 파이프라인 흐름

실제 운영에서는 **Spring 앞단이 FATAL 레벨 로그만** 에이전트로 전달합니다.

```
log content (FATAL)
   │
   ▼  ① extract_event_template
event_id
   │
   ▼  ② classify_anomaly
is_anomaly ?
   ├─ True  → ③ assign_cluster → ④ get_node_info → 답변 생성 LLM
   └─ False ─────────────────────────────────────→ 정상 근거 산출 LLM
```

- ②의 `is_anomaly` 가 라우팅 분기 기준입니다. **정상(False)은 ③·④ 를 모두 거치지 않고** 바로 답변 생성으로 갑니다.
- ③ cluster 와 ④ node_info 는 **비정상 경로에서만** 실행됩니다 (`③ → ④` 순서).
- ① 매칭 실패(`event_id="unknown"`)는 ②에서 `category="UNKNOWN"`, `is_anomaly=True` 로 처리됩니다.
- ③에서 미커버·unknown·다중배정은 미분류(`cluster_id=99`)로 떨어집니다.
- ④는 `node_id` 파싱 불가(NULL 등)·미등록 노드면 해당 필드가 None 으로 반환됩니다.

## Agent 호출 방법

각 Tool은 메타데이터를 프로세스 기동 시 1회 로드(lru_cache)하는 순수 함수입니다. import 후 바로 호출하면 됩니다.

```python
from app.agents.tools.event_template import extract_event_template
from app.agents.tools.anomaly_classifier import classify_anomaly
from app.agents.tools.cluster import assign_cluster
from app.agents.tools.node_info import get_node_info

# ① 로그 → event_id
ev = extract_event_template("rts: kernel terminated for reason 1001")
#   → EventTemplateResult(event_id="E111", event_template="rts: kernel terminated for reason <*>", matched=True)

# ② event_id → 이상 여부 / 긴급도
an = classify_anomaly(ev.event_id)
#   → AnomalyResult(event_id="E111", is_anomaly=True, urgency=Urgency.CRITICAL, category="KERN", impact = "...", action = "...")

# ③·④ 는 비정상일 때만 진행 (정상은 둘 다 건너뜀)
if an.is_anomaly:
    cl = assign_cluster(ev.event_id)
    #   → ClusterResult(cluster_id=3, matched=True)  # 미커버·unknown 이면 cluster_id=99

    ni = get_node_info("R16-M0-NB-C:J07-U11")
    #   → NodeInfoResult(node_metadata=NodeMetadata(rack="R16", ...), alert_stats=AlertStats(alert_pct=0.7))
```

> 테스트에서 메타데이터를 격리하려면 클래스(`EventTemplateExtractor` / `AnomalyClassifier` / `ClusterAssigner`)에
> `templates` / `events` / `clusters` 를 직접 주입할 수 있습니다.
> (`get_node_info` 는 `node_stats.json` 경로 기반 — `parse_node_id` 만 따로 호출해 파싱만 검증할 수도 있습니다.)

## 구조

- `event_template.py`, `anomaly_classifier.py`, `cluster.py`, `node_info.py` — Tool 순수 함수 + 결과 모델
- `metadata/` — 판정에 사용하는 메타데이터 파일 (별도 README 참고)
- 통합 검증: `tests/integration/test_pipeline_bgl_2k.py` (①→②→③ 전건 채점),
  `tests/pipeline_scenarios/test_total_tool_scenarios.py` (①→②→③→④ 시나리오)
