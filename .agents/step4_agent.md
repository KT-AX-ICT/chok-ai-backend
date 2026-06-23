# 4단계 구현 상세: LangGraph 기반 AI Agent 구축

> 상위 계획: [implementation_plan.md](implementation_plan.md) 4단계
> 목표: 3단계 Tool 4개를 `StateGraph` 노드로 **명시적으로 연결**하여 분석 흐름을 고정한다.
> 핵심 결정
> - Tool 호출 순서·여부를 LLM 자율 판단(`create_react_agent`)에 맡기지 않고 **그래프 엣지로 고정**한다.
> - **②(이상 여부 + 긴급도)에서 분기**한다. 정상이면 ③④를 건너뛰고 곧장 LLM으로, 이상이면 ③④로 컨텍스트를 보강한 뒤 LLM으로 합류한다.
> - **ChromaDB(RAG) 미사용.** Tool은 내부 정의 JSON만 참조한다([step3_tools.md](step3_tools.md)).
> 노드 구성도: [step4_graph.md](step4_graph.md)

```
START ──▶ [① 이벤트 템플릿 분류] ──▶ [② 이상 여부 + 긴급도 분류]
                                              │ (조건부 분기)
                ┌────────────(정상)───────────┘
                │                              └──(이상)──┬──▶ [③ 클러스터 분류]
                ▼                                         └──▶ [④ Node 정보 조회]
          [LLM 분석] ◀───────────(이상 경로 합류)────────────┘
                │
                ▼
          [결과 매핑] ──▶ END
```

---

## 4-1. State 정의 (`TypedDict`)

그래프 전체에서 공유할 상태. Tool 산출과 LLM 출력, 최종 응답 매핑에 필요한 키를 모두 보유한다.

- [ ] 입력 필드(요청 원본): `log_id`, `log_level`, `content`, `component`, `log_type`, `node`, `occurred_at` 등 DTO 필드
- [ ] ① 산출: `event_id`, `event_template`, `template_matched`
- [ ] ② 산출(분기 기준): `is_anomaly`(bool), `urgency`, `category`, `impact`, `action`
  - ※ `impact`·`action`은 **LLM 프롬프트에 넣을 컨텍스트**일 뿐 응답에 직접 매핑하지 않는다 (최종 `analysis`/`action`은 LLM이 생성)
- [ ] ③ 산출(이상 경로): `cluster_id`(int), `cluster_matched`
- [ ] ④ 산출(이상 경로): `node_metadata`, `alert_stats`
- [ ] LLM 산출: `summary`, `analysis`, `action`, `reason`
- [ ] 분기 키: `is_anomaly`를 조건부 엣지의 판정 기준으로 사용
- [ ] 이상 경로의 ③④는 **서로 다른 키**에 기록하므로 fan-out/fan-in 시 충돌 없음 (필요 시 reducer는 불필요)

---

## 4-2. 노드 구현 (`services/agent_service.py`)

각 Tool 노드는 3단계 순수 함수를 호출해 State를 갱신만 한다(라우팅 판단 없음).

- [ ] **① 이벤트 템플릿 분류 노드**: `extract_event_template(content)` → `state["event_id"]`, `event_template`, `template_matched` 기록 (**선행 노드**)
- [ ] **② 이상 여부 + 긴급도 분류 노드**: `classify_anomaly(event_id)` → `state["is_anomaly"]`, `urgency`, `category`, `impact`, `action` 기록 (**분기 기준 노드**)
- [ ] **③ 클러스터 분류 노드**(이상): `assign_cluster(event_id)` → `state["cluster_id"]`, `cluster_matched` 기록
- [ ] **④ Node 정보 조회 노드**(이상): `get_node_info(node)` → `state["node_metadata"]`, `alert_stats` 기록
- [ ] **LLM 분석 노드**:
  - [ ] 정상 경로: ① 결과 + ②의 `impact`(정상 근거)만으로 **정상 사유** 프롬프트 구성
  - [ ] 이상 경로: ①②(`impact`/`action`/`urgency`/`category`)③④ 컨텍스트 + 원본 로그로 **이상 근거·대응** 프롬프트 구성
  - [ ] `with_structured_output(LLMAnalysis)`로 `summary / analysis / action / reason` 수신 (※ `domain`·`eventId`는 LLM이 생성하지 않음)
  - [ ] ②의 `impact`/`action`은 **입력 컨텍스트**이며, 최종 `analysis`/`action`은 LLM이 다시 작성한 값을 사용한다
- [ ] **결과 매핑 노드**: LLM 출력 + ②③④ 산출을 `AnalysisResult`로 매핑 (4-3 매핑 규칙 참조)

---

## 4-3. 결과 매핑 규칙 (Tool/LLM 산출 → API 계약)

> Tool 산출 명칭과 API 계약([API.md](API.md))이 다르므로 **매핑 노드에서 변환을 흡수**한다.

**Tool 산출 → 응답(명칭 변환):**
- [ ] `is_anomaly`(bool) → 응답 최상위 `isAbnormal`
- [ ] `event_id` → `result.eventId` — **이상이면 값, 정상이면 `null`**
- [ ] `urgency`(영문 `Critical/High/Mid/Low`) → `result.riskLevel`(한글 `긴급/높음/보통/낮음`) — **정상이면 `null`** (정상에는 긴급도를 부여하지 않음)
- [ ] `cluster_id`(int) → `result.clusterId` — **이상이면 값, 정상이면 `null`**. 미분류는 `99`를 **그대로** 응답에 노출한다(별도 null 변환 없음)

**LLM 산출 → 응답:**
- [ ] LLM `summary` → `result.summary`, `analysis` → `result.analysis`, `action` → `result.action` (최종 `analysis`/`action`은 LLM이 생성한 값)
- [ ] `reason`은 내부 근거용으로 응답에 노출하지 않음

**매핑 노드 생성:**
- [ ] `analyzedAt`(개별 로그 분석 시각, `yyyy-MM-dd HH:mm:ss`)은 매핑 노드에서 생성

> ②의 `impact`/`action`은 응답에 직접 매핑하지 않는다 — LLM 프롬프트 컨텍스트로만 사용한다.

---

## 4-4. 그래프 구성

- [ ] `StateGraph(State)` 생성
- [ ] 노드 `add_node` 등록: `template`(①), `anomaly`(②), `cluster`(③), `node_info`(④), `llm`, `map`
- [ ] 엣지 연결:
  - [ ] `add_edge(START, "template")`
  - [ ] `add_edge("template", "anomaly")`
  - [ ] `add_conditional_edges("anomaly", route_by_anomaly, {...})` — `is_anomaly`가 False면 `"llm"`, True면 `["cluster", "node_info"]`로 fan-out
  - [ ] `add_edge("cluster", "llm")`, `add_edge("node_info", "llm")` — 이상 경로 fan-in (두 노드 완료 후 LLM 합류)
  - [ ] `add_edge("llm", "map")`, `add_edge("map", END)`
- [ ] `graph.compile()` 결과를 **모듈 레벨에서 1회 생성**해 재사용

---

## 4-5. LLM 설정

- [ ] 모델 선택 및 클라이언트 구성 (`langchain-anthropic` `ChatAnthropic` 권장 — 최신 Claude 모델)
- [ ] API 키를 `core/config.py` 환경 변수에서 로드 (`CHOK_AI_` prefix)
- [ ] **구조화 출력**: `with_structured_output(LLMAnalysis)` (JSON 파싱 오류 최소화)
- [ ] 분석 일관성을 위해 낮은 temperature 권장, 최대 토큰 설정

---

## 4-6. 시스템 프롬프트 설계

> 기준: `app/agents/README.md` 책임 범위 준수 (AI는 정상/이상을 **재판단하지 않음**)

- [ ] 역할 정의: "①②에서 이미 판정된 결과를 바탕으로 **근거 설명**을 생성한다"
- [ ] **정상/이상 재판단 금지** 명시 (판정은 규칙 기반 Tool ②가 수행)
- [ ] `reason` 필드 **필수**: 사람이 읽을 수 있는 근거 포함
- [ ] 출력 형식 고정: `summary`, `analysis`, `action`, `reason` (구조화 출력 스키마와 일치)
- [ ] 이상 경로: `urgency`/`category`/`impact`/`cluster`/`node` 컨텍스트 주입 위치 지정
- [ ] 정상 경로: ②의 정상 근거(`impact`)만으로 간결한 정상 사유 작성하도록 지시
- [ ] 반복 패턴 표현 기준: 원인 후보 / 대표 메시지 / 발생 빈도 중심 요약

---

## 4-7. 서비스 진입점

라우터(5단계)가 호출할 함수. 컴파일된 그래프를 감싼다.

- [ ] `analyze_single_log(request) -> LogAnalyzeResponse`: 그래프 `invoke` → `AnalysisResult` 매핑 → `processingTimeMs` 측정
- [ ] `analyze_batch_logs(request) -> LogBatchAnalyzeResponse`: `asyncio.gather(..., return_exceptions=True)`로 병렬 처리
- [ ] 배치 개별 실패가 전체를 막지 않도록 `processStatus`(`success`/`fail`) + `errorMessage` 매핑
- [ ] **LLM/메타데이터 로드 실패 시 명확한 예외**(`AppError` 계열) 반환 (5단계 라우터 에러 핸들링에서 잡음)

---

## 4-8. 테스트

- [ ] 각 노드 단위 테스트 (Mock Tool/LLM 주입)
- [ ] 분기 테스트: **정상** 입력 → ③④ 미실행, LLM 직행 / **이상** 입력 → ③④ 모두 실행 후 합류
- [ ] 그래프 통합 테스트: 입력 로그 → 최종 `AnalysisResult` 산출 검증
- [ ] LLM 응답 파싱 실패 시 예외 경로 테스트

---

## 4단계 완료 기준 (DoD)

- [ ] **②가 정상으로 판정하면 ③④를 건너뛰는 빠른 경로**가 그래프 구조로 강제된다
- [ ] **이상으로 판정하면 ③④가 모두 실행**된 뒤 LLM으로 합류함이 보장된다
- [ ] `analyze_single_log` / `analyze_batch_logs`가 DTO 규격(`isAbnormal`/`result`/`processingTimeMs`)에 맞는 응답을 반환한다
- [ ] LLM·메타데이터 실패가 명확한 오류로 표면화되어 5단계 에러 핸들링에서 처리 가능하다

---

## 확정된 설계 결정 (정합성)

> 2026-06-23 확정. [step3_tools.md](step3_tools.md) "남은 작업 / 리스크"와 연동.

1. **계약 명칭 변환**: Tool은 `is_anomaly`·`cluster_id`로 산출하고, 응답에서 `isAbnormal`·`clusterId`로 변환한다. 긴급도는 `urgency`(영문) → `riskLevel`(한글)로 변환. → 4-3 매핑 노드에서 흡수.
2. **정상 urgency 미부여**: 정상 로그에는 긴급도를 부여하지 않는다 → `result.riskLevel=null`.
3. **③④ 실행 위치**: ③ 클러스터·④ Node 정보 **모두 이상 경로에서만** 수행한다. (3단계 파이프라인 테스트의 ④ 전건 호출은 이 설계에 맞춰 이상-only로 정렬한다.)
4. **클러스터 미분류 표현**: `cluster_id=99`(미분류)는 **그대로 `99`** 로 응답에 노출한다(null 변환 없음).

> `analysis`·`action`은 **최종 응답 필드명**이며 **LLM이 생성**한다. Tool ②의 `impact`/`action`은 응답에 직접 들어가지 않고 LLM 프롬프트 컨텍스트로만 쓰인다.
