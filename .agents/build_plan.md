# 구현 계획 (Build Plan) — feat/langgraph LangGraph 전환

> 브랜치: `feat/langgraph`
> 작성일: 2026-06-24
> 설계 기준: [`step4_agent.md`](step4_agent.md), [`step4_graph.md`](step4_graph.md), [`API.md`](API.md), [`ModelDesign.md`](ModelDesign.md)
> 상위 계획: [`implementation_plan.md`](implementation_plan.md)
> 대상: plan-to-code-implementer가 이 문서를 보고 순차 구축

---

## 현재 상태 요약

| 항목 | 상태 | 비고 |
|------|------|------|
| `app/schemas/analysis.py` | 구현됨 | DTO 완성도 높음. 배치 한도 500 (설계는 400) |
| `app/api/router.py` | 구현됨 | 단건·배치 엔드포인트 작동 |
| `app/core/errors.py` | 구현됨 | AppError→502/503 핸들러 정상 |
| `app/agents/diagnosis_agent.py` | 구현됨 | ChatOpenAI + `with_structured_output`, 이상/정상 2경로 |
| `app/services/analysis_service.py` | 스텁 | Tool ①②③④가 하드코딩 스텁 (E00, 항상 이상 등) |
| `app/agents/tools/*.py` | 구현됨 | 4개 Tool 순수함수 실제 구현 완료, **서비스 미연동** |
| `app/main.py` | 결함 | 죽은 `global_exception_handler` (미import `Request`/`JSONResponse`) |
| `pyproject.toml` | 결함 | `tzdata`·`langgraph` 미선언, dev `httpx2` 오타 의심 |
| `app/core/config.py` | 부분 | LLM 기본 설정만. 동시성/타임아웃 설정 미존재 |

---

## Phase 0: 환경 복구 (선행 필수)

> **의존**: 없음 (최우선)
> **목표**: `import app.main` 성공 + 기존 테스트 green

### 작업 항목

- [ ] **0-1.** `pyproject.toml`에 `tzdata>=2024.1` 추가 (dependencies)
- [ ] **0-2.** `pyproject.toml`에 `langgraph>=0.2.0` 추가 (dependencies)
- [ ] **0-3.** dev 그룹의 `httpx2>=0.28.0`을 `httpx>=0.28.0`으로 수정 (TestClient 의존)
- [ ] **0-4.** `uv lock && uv sync` 실행하여 lock 파일 재생성
- [ ] **0-5.** `.venv` 내에서 `python -c "import app.main"` 성공 확인
- [ ] **0-6.** `pytest tests/test_analyze.py -v` 전체 green 확인

### 영향 파일

- `pyproject.toml`
- `uv.lock`

### 완료 기준 (DoD)

- `import app.main` 에러 없음
- `pytest tests/test_analyze.py` 전 항목 PASSED
- `python -c "from langgraph.graph import StateGraph"` 성공

### 리스크

- `uv.lock` 재생성 시 의존성 충돌 가능 — 충돌 발생 시 `docstring-parser` 등 버전 핀 조정 필요
- `httpx2`가 의도적 패키지명인지 오타인지 확인 필요 (FastAPI TestClient는 `httpx`를 요구)

---

## Phase 1: 빠른 정합성 수정

> **의존**: Phase 0 완료
> **목표**: 설계 문서와 코드 간 불일치 제거 (저비용·고확실성 변경)

### 작업 항목

#### 1-A. 배치 한도 500 → 400

- [ ] **1-1.** `app/schemas/analysis.py` — `BatchAnalyzeRequest.logs` 필드의 `max_length=500` → `max_length=400`으로 변경
  ```python
  # Before
  logs: list[AnalyzeRequest] = Field(..., min_length=1, max_length=500)
  # After
  logs: list[AnalyzeRequest] = Field(..., min_length=1, max_length=400)
  ```
- [ ] **1-2.** `app/schemas/analysis.py` — `BatchAnalyzeRequest` docstring의 "최대 500건" → "최대 400건"
- [ ] **1-3.** `app/api/router.py` — `analyze_batch` 엔드포인트의 summary 및 주석에서 "500건" → "400건"
- [ ] **1-4.** `tests/test_analyze.py` — `test_batch_over_limit_is_422`의 파라미터 `[501, 600]` → `[401, 500]`으로 변경
  ```python
  # Before
  @pytest.mark.parametrize("size", [501, 600])
  # After
  @pytest.mark.parametrize("size", [401, 500])
  ```

#### 1-B. main.py 죽은 핸들러 제거

- [ ] **1-5.** `app/main.py` 57~66행의 `global_exception_handler` 전체 삭제 (미import `Request`/`JSONResponse` 참조 + 43행 `handle_unexpected`와 중복 등록)
  - 삭제 대상:
    ```python
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": "처리되지 않은 서버 오류",
                "detail": str(exc),
            },
        )
    ```
  - 43행의 `app.add_exception_handler(Exception, handle_unexpected)`가 이미 동일 역할을 수행하므로 기능 영향 없음

#### 1-C. 설계 문서 정정

- [ ] **1-6.** `.agents/step4_agent.md` 4-5절 — "langchain-anthropic `ChatAnthropic` 권장 — 최신 Claude 모델" → "langchain-openai `ChatOpenAI` 사용 (현재 코드·Tier1 한도 기준 OpenAI)"로 정정
  - 근거: `diagnosis_agent.py`가 이미 `ChatOpenAI` 사용, `config.py`에 `OPENAI_API_KEY`·`gpt-4o-mini` 설정

### 영향 파일

- `app/schemas/analysis.py`
- `app/api/router.py`
- `app/main.py`
- `tests/test_analyze.py`
- `.agents/step4_agent.md`

### 완료 기준 (DoD)

- `max_length=400` 적용, 401건 요청 시 422 응답
- `main.py`에 미import 심볼(`Request`, `JSONResponse`) 참조 없음
- `pytest tests/test_analyze.py` green
- `step4_agent.md`에 ChatAnthropic 언급 제거

### 리스크

- 낮음. 모두 값 변경·삭제 수준

---

## Phase 2: Tool ①②③④ 실연동 (스텁 → 실구현 교체)

> **의존**: Phase 0 완료 (Phase 1과 병행 가능)
> **목표**: `analysis_service.py`의 4개 스텁 함수를 `app/agents/tools/*.py`의 실제 구현으로 교체

### 배경: 현재 스텁 vs 실구현

| Tool | 스텁 위치 (`analysis_service.py`) | 실구현 위치 | 스텁 동작 | 실구현 시그니처 |
|------|-----------------------------------|-------------|-----------|-----------------|
| ① | `classify_event_template()` → `"E00"` | `app/agents/tools/event_template.py` `extract_event_template(content: str) -> EventTemplateResult` | 항상 `"E00"` | `content` → `EventTemplateResult(event_id, event_template, matched)` |
| ② | `classify_status_urgency()` → 항상 `"이상"` | `app/agents/tools/anomaly_classifier.py` `classify_anomaly(event_id: str) -> AnomalyResult` | 항상 이상 + 레벨 문자열 매핑 | `event_id` → `AnomalyResult(is_anomaly, urgency, category, impact, action)` |
| ③ | `classify_cluster()` → `0` | `app/agents/tools/cluster.py` `assign_cluster(event_id: str) -> ClusterResult` | 항상 `0` | `event_id` → `ClusterResult(cluster_id, matched)` |
| ④ | `fetch_node_info()` → `"(노드 정보 없음)"` | `app/agents/tools/node_info.py` `get_node_info(node_id: str) -> NodeInfoResult` | 고정 문자열 | `node_id` → `NodeInfoResult(node_metadata, alert_stats)` |

### 작업 항목

- [ ] **2-1.** `analysis_service.py`에서 Tool 실구현 import 추가:
  ```python
  from app.agents.tools.event_template import extract_event_template
  from app.agents.tools.anomaly_classifier import classify_anomaly, Urgency
  from app.agents.tools.cluster import assign_cluster
  from app.agents.tools.node_info import get_node_info
  ```

- [ ] **2-2.** 스텁 `classify_event_template()` 교체 — Tool ① 연동:
  - `extract_event_template(log.content)` 호출 → `EventTemplateResult`에서 `event_id` 추출
  - 동기 순수함수이므로 `asyncio.to_thread()` 래핑 권장 (이벤트 루프 블로킹 방지, 메타데이터 JSON 로드가 첫 호출에서만 발생하나 안전 마진 확보)
  - **또는**: 이미 `@lru_cache`로 메타데이터 캐싱 중이고 연산이 가벼우므로 직접 호출도 허용. 선택은 구현자 판단.
  ```python
  async def classify_event_template(log: AnalyzeRequest) -> str:
      result = extract_event_template(log.content)  # 또는 await asyncio.to_thread(...)
      return result.event_id
  ```

- [ ] **2-3.** 스텁 `classify_status_urgency()` 교체 — Tool ② 연동:
  - `classify_anomaly(event_id)` 호출 → `AnomalyResult` 수신
  - **변환 로직 (핵심)**:
    - `is_anomaly` (bool) → 내부 `status`: `True` → `"이상"`, `False` → `"정상"`
    - `urgency` (영문 Enum `Critical/High/Mid/Low`) → `risk_level` (한글 `긴급/높음/보통/낮음`)
    - **정상이면 `risk_level=None`** (step4_agent.md 4-3 "정상 urgency 미부여" 규칙)
    - `impact`/`action`은 LLM 프롬프트 컨텍스트용. 현재 서비스 시그니처가 `(status, risk_level)` 튜플만 반환 → **Phase 3에서 State에 저장**. Phase 2에서는 반환 시그니처를 확장하거나 별도 저장 구조를 도입
  - 영문→한글 변환 맵:
    ```python
    _URGENCY_KO: dict[str, RiskLevel] = {
        "Critical": "긴급",
        "High": "높음",
        "Mid": "보통",
        "Low": "낮음",
    }
    ```
  - **주의**: Tool ②는 정상이어도 `urgency`를 반환함 (잠재 심각도 보존). 하지만 API 계약상 정상 시 `riskLevel=null`이므로 **서비스 계층에서 정상일 때 risk_level=None으로 덮어씀**

- [ ] **2-4.** 스텁 `classify_cluster()` 교체 — Tool ③ 연동:
  - `assign_cluster(event_id)` 호출 → `ClusterResult`에서 `cluster_id` 추출
  - 미분류 `99`는 **그대로 반환** (null 변환 없음, step4_agent.md 확정 설계 결정 4번)

- [ ] **2-5.** 스텁 `fetch_node_info()` 교체 — Tool ④ 연동:
  - `get_node_info(log.node)` 호출 → `NodeInfoResult`를 **LLM에 전달할 컨텍스트 문자열로 변환**
  - 현재 `run_diagnosis(..., node_ctx: str)` 시그니처가 문자열을 기대하므로, `NodeInfoResult` → 사람이 읽을 수 있는 텍스트 포매팅 필요:
    ```python
    def _format_node_ctx(info: NodeInfoResult) -> str:
        parts = []
        md = info.node_metadata
        if md.rack: parts.append(f"Rack: {md.rack}")
        if md.midplane: parts.append(f"Midplane: {md.midplane}")
        if md.node_slot: parts.append(f"NodeSlot: {md.node_slot}")
        if md.node_role: parts.append(f"Role: {md.node_role}")
        if info.alert_stats:
            parts.append(f"AlertPct: {info.alert_stats.alert_pct:.1f}%")
        return " | ".join(parts) if parts else "(노드 정보 없음)"
    ```

- [ ] **2-6.** 스텁 함수 4개 본문 삭제 (import + 래퍼로 교체 완료 후)

- [ ] **2-7.** **Tool② `impact`/`action` 전달 경로 확보**: 현재 서비스 시그니처가 `(status, risk_level)` 튜플만 반환하여 `impact`/`action`이 유실됨. Phase 3에서 State로 옮기더라도, Phase 2 단계에서 LLM 프롬프트에 `impact`/`action`을 전달해야 하므로:
  - **방법 A (권장)**: `classify_status_urgency` 반환값을 확장하여 `AnomalyResult` 전체 또는 `(status, risk_level, impact, action)` 튜플 반환 → `run_diagnosis` 프롬프트에 `impact`/`action` 주입
  - **방법 B**: Phase 3 전까지는 `impact`/`action` 없이 동작 유지 (현재와 동일)
  - 구현자가 Phase 3 진입 시기에 따라 판단

### 영향 파일

- `app/services/analysis_service.py` (주요 변경)
- `app/agents/diagnosis_agent.py` (프롬프트에 impact/action 주입 시)
- `app/agents/prompts/diagnosis.py` (프롬프트 템플릿에 impact/action 플레이스홀더 추가 시)

### 완료 기준 (DoD)

- `analysis_service.py`에 하드코딩 스텁(`"E00"`, 항상 `"이상"`, `return 0`, `"(노드 정보 없음)"`) 없음
- 실제 메타데이터 기반으로 `event_id`, `is_anomaly`, `cluster_id`, `node_info` 산출
- `tests/test_analyze.py` green (monkeypatch 대상 경로가 바뀌면 테스트도 수정)

### 리스크

- **monkeypatch 경로 깨짐**: 테스트가 `SVC.run_diagnosis` 등을 monkeypatch하는데, 스텁 함수명이 변경되면 경로 갱신 필요
- **동기함수 이벤트 루프 블로킹**: Tool 함수는 동기 순수함수. JSON 메타데이터가 `@lru_cache`로 캐싱되므로 첫 호출 이후 CPU-bound 연산만 남지만, 안전을 위해 `asyncio.to_thread()` 고려
- **Tool② urgency 정상 처리**: Tool②가 정상이어도 urgency를 반환하므로 서비스에서 반드시 None으로 덮어써야 함

---

## Phase 3: LangGraph StateGraph 전환 (핵심)

> **의존**: Phase 2 완료 (Tool 실연동 필수)
> **목표**: `asyncio.gather` 수기 오케스트레이션을 LangGraph StateGraph로 전환, 조건부 분기를 그래프 구조로 강제

### 아키텍처 참조

```
START → [template] → [anomaly] ─(정상)──→ [llm] → [map] → END
                                └─(이상)──→ [cluster] ──→ [llm] → [map] → END
                                └─(이상)──→ [node_info] ─┘
```

### 작업 항목

#### 3-A. State 정의

- [ ] **3-1.** 새 파일 `app/agents/graph.py` (또는 `app/agents/agent_graph.py`) 생성
- [ ] **3-2.** `TypedDict` 기반 `AgentState` 정의 — step4_agent.md 4-1 필드:
  ```python
  from typing import TypedDict
  
  class AgentState(TypedDict, total=False):
      # 입력 (요청 원본)
      log_id: int
      log_level: str
      content: str
      component: str
      log_type: str
      node: str
      occurred_at: str
      domain: str
      node_repeat: str
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
      # ④ 산출 (이상 경로)
      node_metadata: dict | None   # NodeMetadata를 dict로
      alert_stats: dict | None     # AlertStats를 dict로
      # LLM 산출
      summary: str
      analysis: str
      action: str
      reason: str
      # 매핑 결과
      result: dict | None  # 최종 AnalyzeResult 데이터
  ```
  - **주의**: fan-out/fan-in에서 ③④가 서로 다른 키에 기록하므로 reducer 불필요

#### 3-B. 노드 구현

- [ ] **3-3.** **`template_node`** (① 이벤트 템플릿 분류):
  - `extract_event_template(state["content"])` 호출
  - `state["event_id"]`, `state["event_template"]`, `state["template_matched"]` 갱신
  
- [ ] **3-4.** **`anomaly_node`** (② 이상 여부 + 긴급도):
  - `classify_anomaly(state["event_id"])` 호출
  - `state["is_anomaly"]`, `state["urgency"]`, `state["category"]`, `state["impact"]`, `state["action_ctx"]` 갱신

- [ ] **3-5.** **`cluster_node`** (③ 클러스터 분류, 이상 경로):
  - `assign_cluster(state["event_id"])` 호출
  - `state["cluster_id"]`, `state["cluster_matched"]` 갱신

- [ ] **3-6.** **`node_info_node`** (④ Node 정보 조회, 이상 경로):
  - `get_node_info(state["node"])` 호출
  - `state["node_metadata"]`, `state["alert_stats"]` 갱신 (dict로 변환하여 저장)

- [ ] **3-7.** **`llm_node`** (LLM 분석):
  - `state["is_anomaly"]` 기준으로 프롬프트 분기:
    - **정상**: ① 결과 + ②의 `impact` (정상 근거)만으로 정상 사유 프롬프트 → `run_normal_reason()` 호출
    - **이상**: ①②(impact/action_ctx/urgency/category)③④ + 원본 로그 → `run_diagnosis()` 호출
  - `state["summary"]`, `state["analysis"]`, `state["action"]`, `state["reason"]` 갱신
  - `with_structured_output(LLMAnalysis)`는 기존 `diagnosis_agent.py`를 그대로 활용

- [ ] **3-8.** **`map_node`** (결과 매핑):
  - LLM 출력 + Tool 산출을 `AnalyzeResult`로 변환 — step4_agent.md 4-3 매핑 규칙:
    - `is_anomaly` → `isAbnormal`
    - `event_id` → `result.eventId` (정상이면 `null`)
    - `urgency`(영문) → `result.riskLevel`(한글) (정상이면 `null`)
    - `cluster_id` → `result.clusterId` (정상이면 `null`, 미분류 99 그대로)
    - `summary`/`analysis`/`action` → LLM 생성값
    - `analyzedAt` → 현재 시각(KST)
  - `state["result"]`에 최종 매핑 결과 dict 저장

#### 3-C. 조건부 분기 함수

- [ ] **3-9.** `route_by_anomaly(state: AgentState) -> str | list[str]` 정의:
  ```python
  def route_by_anomaly(state: AgentState):
      if state["is_anomaly"]:
          return ["cluster", "node_info"]  # fan-out
      return "llm"  # 빠른 경로
  ```

#### 3-D. 그래프 구성

- [ ] **3-10.** StateGraph 생성 및 노드 등록:
  ```python
  from langgraph.graph import StateGraph, START, END
  
  graph_builder = StateGraph(AgentState)
  graph_builder.add_node("template", template_node)
  graph_builder.add_node("anomaly", anomaly_node)
  graph_builder.add_node("cluster", cluster_node)
  graph_builder.add_node("node_info", node_info_node)
  graph_builder.add_node("llm", llm_node)
  graph_builder.add_node("map", map_node)
  ```

- [ ] **3-11.** 엣지 연결:
  ```python
  graph_builder.add_edge(START, "template")
  graph_builder.add_edge("template", "anomaly")
  graph_builder.add_conditional_edges("anomaly", route_by_anomaly, {
      "llm": "llm",
      "cluster": "cluster",
      "node_info": "node_info",
  })
  graph_builder.add_edge("cluster", "llm")
  graph_builder.add_edge("node_info", "llm")
  graph_builder.add_edge("llm", "map")
  graph_builder.add_edge("map", END)
  ```

- [ ] **3-12.** `graph = graph_builder.compile()`을 **모듈 레벨에서 1회** 실행, 재사용
  - 주의: LLM 클라이언트 초기화가 모듈 로드 시 발생하지 않도록, `_structured_llm()`의 `@lru_cache` lazy 초기화 유지

#### 3-E. 서비스 진입점 교체

- [ ] **3-13.** `analysis_service.py`의 `analyze_single_log()` 재작성:
  ```python
  async def analyze_single_log(log: AnalyzeRequest) -> tuple[str, LogStatus, AnalyzeResult]:
      initial_state = {
          "log_id": log.log_id,
          "log_level": log.log_level,
          "content": log.content,
          "component": log.component,
          "log_type": log.log_type,
          "node": log.node,
          "occurred_at": log.occurred_at,
          "domain": log.domain,
          "node_repeat": log.node_repeat,
      }
      final_state = await graph.ainvoke(initial_state)
      # final_state["result"]에서 AnalyzeResult 복원
      ...
  ```
  - 반환 시그니처를 기존 `(event_id, status, result)` 유지하여 router 변경 최소화
  - 또는 그래프 결과에서 직접 `AnalyzeResponse` 구성 (라우터 변경 포함)

- [ ] **3-14.** 기존 `analysis_service.py`의 스텁 함수 4개 및 수기 오케스트레이션 코드 삭제

#### 3-F. 테스트 마이그레이션

- [ ] **3-15.** `tests/test_analyze.py`의 monkeypatch 대상 경로 갱신:
  - 기존: `SVC.run_diagnosis`, `SVC.classify_status_urgency`, `SVC.run_normal_reason`
  - 변경 후: 그래프 노드가 직접 Tool/LLM을 호출하므로 monkeypatch 대상이 `app.agents.graph.classify_anomaly` 등으로 변경됨
  - 또는 그래프 전체를 mock하는 전략으로 전환

### 영향 파일

- `app/agents/graph.py` (신규)
- `app/services/analysis_service.py` (대규모 재작성)
- `tests/test_analyze.py` (monkeypatch 경로 변경)
- `app/agents/diagnosis_agent.py` (LLM 노드에서 재사용, 인터페이스 변경 가능)

### 완료 기준 (DoD)

- [ ] ②가 정상으로 판정하면 ③④를 건너뛰는 **빠른 경로**가 **그래프 엣지 구조로 강제**된다
- [ ] 이상으로 판정하면 ③④가 **모두 실행된 뒤** LLM으로 합류함이 보장된다
- [ ] `analyze_single_log` / `analyze_batch_logs`가 기존 DTO 규격(`isAbnormal`/`result`/`processingTimeMs`)에 맞는 응답을 반환한다
- [ ] `graph.compile()` 결과가 모듈 레벨에서 1회 생성, 매 요청마다 재생성하지 않음
- [ ] `pytest tests/test_analyze.py` green

### 리스크

- **monkeypatch 경로 깨짐**: 그래프 구조 전환 시 기존 테스트의 patch 경로가 모두 깨짐 → 테스트 리팩토링 필수 (3-15)
- **fan-out/fan-in 동작 확인**: LangGraph의 `add_conditional_edges`에서 list 반환 시 fan-out이 실제로 병렬 실행되는지, fan-in이 두 노드 완료를 기다리는지 검증 필요
- **async 노드에서 동기 Tool 호출**: 각 노드 함수가 `async def`여야 하는지, 동기 함수도 허용하는지 LangGraph 버전별 확인 필요. 동기 함수를 노드로 등록 시 `asyncio.to_thread()` 래핑 고려

---

## Phase 4: 배치 회복탄력성

> **의존**: Phase 3 완료
> **목표**: 400건 배치가 Tier 1 한도(RPM 500, TPM 500k) 안에서 안전하게 처리

### 작업 항목

#### 4-A. 동시성 제어

- [ ] **4-1.** `config.py`에 배치 동시성·타임아웃·재시도 설정 추가:
  ```python
  # ── 배치 처리 ──────────────────────────────
  batch_concurrency: int = 8                    # asyncio.Semaphore 상한
  batch_timeout_s: int = 300                    # 전체 배치 타임아웃 (5분)
  llm_call_timeout_s: int = 60                  # 개별 LLM 호출 타임아웃
  llm_max_retries: int = 6                      # 지수 백오프 재시도 횟수
  ```
  - 모두 `CHOK_AI_` prefix로 환경변수 override 가능

- [ ] **4-2.** `analysis_service.py`의 `analyze_batch_logs()` 수정:
  ```python
  async def analyze_batch_logs(logs: list[AnalyzeRequest]) -> list[BatchItemResult]:
      settings = get_settings()
      sem = asyncio.Semaphore(settings.batch_concurrency)
      
      async def _limited(log):
          async with sem:
              return await _safe_analyze(log)
      
      results = await asyncio.wait_for(
          asyncio.gather(*[_limited(log) for log in logs]),
          timeout=settings.batch_timeout_s,
      )
      return results
  ```

#### 4-B. LLM 재시도 설정

- [ ] **4-3.** `diagnosis_agent.py`의 `ChatOpenAI` 생성자에 `max_retries` 추가:
  ```python
  llm = ChatOpenAI(
      model=settings.llm_model,
      api_key=settings.openai_api_key,
      temperature=settings.llm_temperature,
      max_completion_tokens=settings.llm_max_tokens,
      max_retries=settings.llm_max_retries,  # 지수 백오프 (429/5xx 대응)
  )
  ```

#### 4-C. 개별 호출 타임아웃

- [ ] **4-4.** `diagnosis_agent.py`의 `_ainvoke()`에 개별 타임아웃 적용:
  ```python
  async def _ainvoke(schema, messages):
      settings = get_settings()
      structured = _structured_llm(schema)
      try:
          return await asyncio.wait_for(
              structured.ainvoke(messages),
              timeout=settings.llm_call_timeout_s,
          )
      except (asyncio.TimeoutError, TimeoutError) as e:
          raise LLMTimeoutError("LLM 응답 지연/타임아웃", str(e)) from e
      except Exception as e:
          raise LLMError("LLM 호출 또는 구조화 출력 실패", str(e)) from e
  ```

### 영향 파일

- `app/core/config.py`
- `app/services/analysis_service.py`
- `app/agents/diagnosis_agent.py`

### 완료 기준 (DoD)

- [ ] `Semaphore(8)`이 동시 LLM 호출을 8건으로 제한
- [ ] `ChatOpenAI(max_retries=6)` 설정으로 429/5xx 시 지수 백오프
- [ ] 전체 배치 5분 타임아웃 + 개별 호출 60s 타임아웃 작동
- [ ] 모든 설정값이 `CHOK_AI_` prefix 환경변수로 override 가능
- [ ] 기존 테스트 green

### 리스크

- **프록시 체인 타임아웃 불일치**: 5분 동기 요청은 nginx `proxy_read_timeout`(기본 60s) 등 모든 홉이 5분을 허용해야 함. 인프라 쪽 설정 확인 필요
- **Semaphore 전역 vs 요청별**: `Semaphore`를 함수 로컬로 생성하면 요청별로 독립 → 동시 배치 요청이 들어오면 전체 동시성이 `8 x 요청수`로 폭증. 전역 Semaphore로 변경하거나, 단일 요청만 허용하는 정책 검토

---

## Phase 5: 테스트 + 검증

> **의존**: Phase 4 완료 (또는 Phase 3 완료 후 병행)
> **목표**: 전체 테스트 스위트 green, 분기 동작 검증

### 작업 항목

- [ ] **5-1.** **분기 테스트 (그래프 구조 검증)**:
  - 정상 입력 → ③④ 미실행, LLM 직행 확인
  - 이상 입력 → ③④ 모두 실행 후 LLM 합류 확인
  - 각 노드 실행 여부를 spy/mock으로 추적

- [ ] **5-2.** **Tool 실연동 통합 테스트**:
  - 알려진 `event_id`(메타데이터에 존재)에 대해 Tool①→②→③→④ 파이프라인 검증
  - `unknown` event_id에 대한 fallback 동작 검증
  - 미등록 노드에 대한 Tool④ 동작 검증

- [ ] **5-3.** **배치 동시성 상한 테스트**:
  - 동시 실행 수가 Semaphore 상한(8)을 초과하지 않음을 검증
  - 타임아웃 시 적절한 에러 반환 확인

- [ ] **5-4.** **기존 회귀 테스트 갱신 확인**:
  - `tests/test_analyze.py` — 모든 기존 테스트 항목 green
  - `tests/event_template/`, `tests/cluster/`, `tests/node_info/` — Tool 단위 테스트 green
  - `tests/pipeline_scenarios/test_total_tool_scenarios.py` — 파이프라인 시나리오 green

- [ ] **5-5.** **전체 스위트 실행**: `pytest --tb=short -v` 전 항목 PASSED

### 영향 파일

- `tests/test_analyze.py` (monkeypatch 경로 갱신)
- `tests/` 하위 신규 테스트 파일 추가 가능

### 완료 기준 (DoD)

- [ ] 정상/이상 분기별 ③④ 실행 여부가 테스트로 보장됨
- [ ] 전체 `pytest` green (tool 단위 + 통합 + 엔드포인트 회귀)
- [ ] 배치 동시성 상한이 테스트로 검증됨

### 리스크

- 낮음. Phase 3~4의 구현이 올바르면 테스트는 이를 확인만 함

---

## 의존 순서 요약

```
Phase 0 (환경복구)
    ├──→ Phase 1 (정합성 수정) ──┐
    └──→ Phase 2 (Tool 실연동) ──┤
                                  └──→ Phase 3 (LangGraph 전환) ──→ Phase 4 (배치 회복탄력성) ──→ Phase 5 (테스트)
```

- **Phase 0**이 막히면 전부 막힘
- **Phase 1과 2**는 서로 독립 → 병행 가능
- **Phase 3**은 Phase 2 위에서 진행 (Tool 실연동 필수)
- **Phase 4**는 Phase 3 이후 (그래프 기반 배치 처리)
- **Phase 5**는 Phase 3 이후부터 점진적 병행 가능, Phase 4 완료 후 전체 검증

---

## 알려진 정합성 차이 (설계 vs 현재 코드)

> Phase 1~3에서 순차 해소

| # | 설계 (API.md / ModelDesign.md) | 현재 코드 | 해소 Phase |
|---|-------------------------------|-----------|------------|
| 1 | 배치 한도 400건 | `max_length=500` | Phase 1 |
| 2 | `result.eventId` (result 내부) | `AnalyzeResponse.event_id` (최상위) | Phase 3 (매핑 노드에서 조정) |
| 3 | `errorMessage` (배치 실패 필드명) | `error` | Phase 3 (DTO 정렬) |
| 4 | `LLMAnalysis.reason` (내부 근거 필드) | `diagnosis_agent.py`에 없음 | Phase 3 (LLM 스키마 확장) |
| 5 | step4_agent.md "ChatAnthropic 권장" | 코드는 ChatOpenAI | Phase 1 (문서 정정) |
| 6 | Tool ②의 `impact`/`action`이 LLM 컨텍스트 | 현재 미전달 | Phase 2~3 |
| 7 | 정상 시 `riskLevel=null` | 스텁이 항상 이상 반환하여 미검증 | Phase 2 |
