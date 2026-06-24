# 계획 문서 — LLM 프롬프트에 Tool② 산출(impact·action·category) 주입

> 브랜치: `feat/langgraph`
> 작성일: 2026-06-24
> 설계 기준: [`step4_agent.md`](step4_agent.md), [`build_plan.md`](build_plan.md) Phase 2~3
> 대상 파일: `app/agents/graph.py`, `app/agents/diagnosis_agent.py`, `app/agents/prompts/diagnosis.py`, `tests/test_analyze.py`

---

## 배경 및 목표

`anomaly_node`는 `classify_anomaly(event_id)`를 호출해 `category`·`impact`·`action_ctx`를 LangGraph
`AgentState`에 보관한다. 그러나 **`llm_node`는 이 값들을 `run_diagnosis` / `run_normal_reason`에 전달하지
않는다** — State에 저장된 결정적 힌트가 LLM 프롬프트 직전에 소실된다.

`impact`(장애 영향)와 `action`(권장 대응)은 `step4_agent.md` 4-2/4-6에서 "LLM 프롬프트 컨텍스트로
의도된 값"으로 명시되어 있으며, `category`(도메인 분류)는 LLM이 분석 방향을 잡는 데 직접 활용된다.
세 값 모두 주입하면 LLM이 일관된 틀 안에서 분석을 정제할 수 있고, echo 방지 지시로 앵무새 리스크를
완화한다.

### 현재 상태 (실측)

| 항목 | 현재 상태 |
|------|-----------|
| `anomaly_node` → State 저장 | `category` / `impact` / `action_ctx` 모두 저장됨 |
| `llm_node` → `run_diagnosis` 호출 | `(log, risk_level, cluster_ctx, event_id, node_ctx)` — impact/action/category **미전달** |
| `llm_node` → `run_normal_reason` 호출 | `(log, event_id)` — impact/category **미전달** |
| `USER_PROMPT_TEMPLATE` 결정적 산출값 블록 | `risk_level`, `cluster_ctx` 만 포함 |
| `NORMAL_USER_PROMPT_TEMPLATE` | 로그 정보만 (Tool② 산출 전혀 없음) |
| `SYSTEM_PROMPT` | impact/action 참고·정제 지시 없음 |

---

## 제외 항목 (확정, 이유 포함)

| 산출 | 제외 이유 |
|------|-----------|
| ① `event_template` | `event_id`와 내용 유사, LLM에 불필요한 중복 |
| ④ `socket_position` / `processor_unit` | 원본 `node` 문자열에 이미 포함 → 중복; `alert_pct`는 노드 단위 집계라 소켓·프로세서 단위 상관 데이터 없음 |
| ③ `importance` | 설계상 의도적 제외 (`build_plan.md` Phase 6 및 README 주석) |
| ①③ `matched` / `cluster_matched` / `is_anomaly` 외 메타 플래그 | LLM 근거 작성에 불필요 |

---

## Phase 구성

```
Phase A: llm_node — State에서 impact/action/category 꺼내 호출 인자 추가
    └──→ Phase B: diagnosis_agent.py — run_diagnosis / run_normal_reason 시그니처 확장
            └──→ Phase C: prompts/diagnosis.py — 프롬프트 템플릿에 블록 추가 + 시스템 지시 보강
                    └──→ Phase D: 테스트 — 기존 green 유지 + 주입 검증 추가
```

---

## Phase A: `graph.py` — `llm_node` 호출 인자 확장

> **의존**: 없음 (최우선)
> **목표**: State에 보관된 `category`/`impact`/`action_ctx`를 LLM 호출 시 전달

### 작업 항목

- [ ] **A-1.** `llm_node`의 이상 경로에서 `run_diagnosis` 호출 시 `category`/`impact`/`action` 인자 추가:
  ```python
  # Before
  llm_out = await run_diagnosis(log, risk_level, cluster_ctx, event_id, node_ctx)

  # After
  category = state.get("category") or "UNKNOWN"
  impact = state.get("impact") or ""
  action_hint = state.get("action_ctx") or ""
  llm_out = await run_diagnosis(
      log, risk_level, cluster_ctx, event_id, node_ctx,
      category=category, impact=impact, action_hint=action_hint,
  )
  ```

- [ ] **A-2.** `llm_node`의 정상 경로에서 `run_normal_reason` 호출 시 `category`/`impact` 인자 추가:
  ```python
  # Before
  llm_out = await run_normal_reason(log, event_id)

  # After
  category = state.get("category") or "UNKNOWN"
  impact = state.get("impact") or ""
  llm_out = await run_normal_reason(log, event_id, category=category, impact=impact)
  ```
  - **State 안전 접근**: `state.get(key)` 사용 필수. 정상 경로에서 `anomaly_node`가 실행되므로
    `impact`/`category`는 항상 존재하나, `None` 반환 시 폴백 문자열로 방어.

### 영향 파일

- `app/agents/graph.py` (`llm_node` 함수)

### 완료 기준

- `run_diagnosis` 호출 시 `category`/`impact`/`action_hint` 인자 포함
- `run_normal_reason` 호출 시 `category`/`impact` 인자 포함
- `state.get()` 안전 접근 패턴 사용

---

## Phase B: `diagnosis_agent.py` — 시그니처 확장

> **의존**: Phase A 완료
> **목표**: `run_diagnosis` / `run_normal_reason`이 추가 인자를 받아 프롬프트에 전달

### 작업 항목

- [ ] **B-1.** `run_diagnosis` 시그니처에 `category`/`impact`/`action_hint` 파라미터 추가:
  ```python
  # Before
  async def run_diagnosis(
      log: AnalyzeRequest,
      risk_level: RiskLevel,
      cluster_ctx: str,
      event_id: str,
      node_ctx: str,
  ) -> dict[str, str]:

  # After
  async def run_diagnosis(
      log: AnalyzeRequest,
      risk_level: RiskLevel,
      cluster_ctx: str,
      event_id: str,
      node_ctx: str,
      *,
      category: str = "UNKNOWN",
      impact: str = "",
      action_hint: str = "",
  ) -> dict[str, str]:
  ```
  - 기본값을 설정해 기존 호출 지점이 인자를 생략해도 호환되게 함

- [ ] **B-2.** `run_diagnosis` 내 `USER_PROMPT_TEMPLATE.format(...)` 호출에 신규 인자 추가:
  ```python
  user_prompt = USER_PROMPT_TEMPLATE.format(
      ...,
      category=category,
      impact=impact,
      action_hint=action_hint,
  )
  ```

- [ ] **B-3.** `run_normal_reason` 시그니처에 `category`/`impact` 파라미터 추가:
  ```python
  # Before
  async def run_normal_reason(
      log: AnalyzeRequest,
      event_id: str,
  ) -> dict[str, str]:

  # After
  async def run_normal_reason(
      log: AnalyzeRequest,
      event_id: str,
      *,
      category: str = "UNKNOWN",
      impact: str = "",
  ) -> dict[str, str]:
  ```

- [ ] **B-4.** `run_normal_reason` 내 `NORMAL_USER_PROMPT_TEMPLATE.format(...)` 호출에 신규 인자 추가:
  ```python
  user_prompt = NORMAL_USER_PROMPT_TEMPLATE.format(
      ...,
      category=category,
      impact=impact,
  )
  ```

### 영향 파일

- `app/agents/diagnosis_agent.py`

### 완료 기준

- 기본값(`category="UNKNOWN"`, `impact=""`, `action_hint=""`)이 있어 기존 호출 지점 호환 유지
- `run_diagnosis` / `run_normal_reason` 모두 새 인자를 `format()` 호출에 전달

---

## Phase C: `prompts/diagnosis.py` — 템플릿 및 시스템 지시 보강

> **의존**: Phase B 완료
> **목표**: 프롬프트에 도메인 분류·장애 영향·권장 대응 블록 추가 + echo 방지 지시 삽입

### Before / After — 이상 경로 결정적 산출값 블록

```
# Before (USER_PROMPT_TEMPLATE)
[결정적 Tool 산출값 — 재판단 금지]
- 긴급도(risk_level): {risk_level}
- 패턴 클러스터: {cluster_ctx}

# After
[결정적 Tool 산출값 — 재판단 금지]
- 긴급도(risk_level): {risk_level}
- 도메인 분류(category): {category}
- 장애 영향(impact): {impact}
- 권장 대응(action_hint): {action_hint}
- 패턴 클러스터: {cluster_ctx}
```

### Before / After — 정상 경로 컨텍스트 블록

```
# Before (NORMAL_USER_PROMPT_TEMPLATE)
[로그 정보]
...
이 로그를 정상으로 판단한 사유(summary, analysis)를 작성하세요.

# After — [정상 컨텍스트] 블록 추가
[로그 정보]
...

[정상 컨텍스트 — 참고용]
- 도메인 분류(category): {category}
- 이벤트 영향 설명(impact): {impact}

이 로그를 정상으로 판단한 사유(summary, analysis)를 작성하세요.
  (impact는 참고용 출발점입니다. 로그 본문을 근거로 정제하여 작성하세요.)
```

### 작업 항목

- [ ] **C-1.** `USER_PROMPT_TEMPLATE`의 `[결정적 Tool 산출값]` 블록에 3줄 추가:
  - `도메인 분류(category): {category}`
  - `장애 영향(impact): {impact}`
  - `권장 대응(action_hint): {action_hint}`
  - 기존 `{risk_level}`·`{cluster_ctx}` 줄은 위치 유지

- [ ] **C-2.** `NORMAL_USER_PROMPT_TEMPLATE`에 `[정상 컨텍스트]` 블록 추가:
  - `{category}`, `{impact}` 플레이스홀더 포함
  - impact가 정상 경로에서 갖는 의미(ECC 자동 정정, 임계값 미달 등) 참고용임을 명시

- [ ] **C-3.** `SYSTEM_PROMPT`에 impact/action_hint 취급 원칙 추가:
  ```
  # 추가할 원칙 (기존 원칙 5개 이후)
  6. impact와 action_hint는 결정적 규칙 기반 힌트입니다. 로그 본문·컨텍스트를 근거로 정제하여
     자신의 언어로 작성하세요. 그대로 복붙하지 마세요.
  ```
  - LLM이 `impact` 문자열을 `analysis` 필드에 그대로 복붙하는 echo(앵무새) 방지

- [ ] **C-4.** `NORMAL_SYSTEM_PROMPT`에 impact 취급 원칙 추가:
  ```
  # 추가할 원칙
  4. impact는 참고용 출발점입니다. 반드시 로그 본문·컴포넌트 근거를 중심으로 정제하여
     자신의 표현으로 작성하세요.
  ```

### 영향 파일

- `app/agents/prompts/diagnosis.py`

### 완료 기준

- `USER_PROMPT_TEMPLATE`에 `{category}`, `{impact}`, `{action_hint}` 플레이스홀더 존재
- `NORMAL_USER_PROMPT_TEMPLATE`에 `{category}`, `{impact}` 플레이스홀더 존재
- `SYSTEM_PROMPT` / `NORMAL_SYSTEM_PROMPT`에 echo 방지 원칙 포함
- `USER_PROMPT_TEMPLATE.format(...)` 호출 시 미전달 플레이스홀더로 인한 `KeyError` 없음

---

## Phase D: 테스트

> **의존**: Phase A~C 완료
> **목표**: 기존 pytest green 유지 + impact/action/category 주입 검증 추가

### 작업 항목

- [ ] **D-1.** 기존 테스트 전체 green 확인: `pytest tests/test_analyze.py -v`
  - Phase A~C의 변경이 `run_diagnosis` / `run_normal_reason` 기본값 덕분에 기존 monkeypatch 호출과
    호환되는지 확인. 기존 테스트가 인자를 직접 체크하지 않으므로 큰 수정 불필요하나, 템플릿 `format()`
    호출 시 플레이스홀더 누락 여부는 반드시 확인.

- [ ] **D-2.** 이상 경로 — `run_diagnosis` 호출 시 인자 주입 검증 테스트 1건 추가:
  ```python
  # 예시 (tests/test_analyze.py 또는 신규 파일)
  async def test_llm_node_passes_impact_to_run_diagnosis(mocker):
      mock_run = mocker.patch("app.agents.graph.run_diagnosis", return_value={...})
      # anomaly_node State 세팅 후 llm_node 직접 호출
      state = { ..., "is_anomaly": True, "impact": "DDR 메모리 오류.", "action_ctx": "메모리 점검", "category": "HARDWARE" }
      await llm_node(state)
      call_kwargs = mock_run.call_args.kwargs
      assert call_kwargs["impact"] == "DDR 메모리 오류."
      assert call_kwargs["action_hint"] == "메모리 점검"
      assert call_kwargs["category"] == "HARDWARE"
  ```

- [ ] **D-3.** 정상 경로 — `run_normal_reason` 호출 시 인자 주입 검증 테스트 1건 추가:
  ```python
  async def test_llm_node_passes_impact_to_run_normal_reason(mocker):
      mock_run = mocker.patch("app.agents.graph.run_normal_reason", return_value={...})
      state = { ..., "is_anomaly": False, "impact": "ECC 자동 정정됨.", "category": "HARDWARE" }
      await llm_node(state)
      call_kwargs = mock_run.call_args.kwargs
      assert call_kwargs["impact"] == "ECC 자동 정정됨."
      assert call_kwargs["category"] == "HARDWARE"
  ```

### 영향 파일

- `tests/test_analyze.py` (또는 `tests/test_llm_node.py` 신규)

### 완료 기준

- 기존 `pytest tests/test_analyze.py` 전 항목 PASSED (기존 35건 이상)
- 이상 경로 주입 검증 1건 PASSED
- 정상 경로 주입 검증 1건 PASSED

---

## DoD (완료 기준 요약)

| # | 항목 | 검증 방법 |
|---|------|-----------|
| 1 | `category`/`impact`/`action_hint`가 이상 경로 프롬프트에 포함됨 | spy 또는 `USER_PROMPT_TEMPLATE.format(...)` 결과 문자열 확인 |
| 2 | `category`/`impact`가 정상 경로 프롬프트에 포함됨 | spy 또는 `NORMAL_USER_PROMPT_TEMPLATE.format(...)` 결과 확인 |
| 3 | LLM이 impact/action을 echo(복붙)하지 않도록 시스템 프롬프트에 지시 삽입됨 | `SYSTEM_PROMPT` / `NORMAL_SYSTEM_PROMPT` 텍스트 확인 |
| 4 | 응답 계약 불변 (`isAbnormal` / `clusterId` / `riskLevel` / `analyzedAt` 필드 변경 없음) | `map_node` 로직 무변경 확인 + 기존 엔드포인트 테스트 green |
| 5 | 전체 `pytest` green (기존 회귀 + 주입 검증 2건 신규) | `pytest --tb=short -v` |

---

## 리스크

| 리스크 | 가능성 | 완화 방법 |
|--------|--------|-----------|
| **LLM echo (앵무새)**: impact 문자열이 analysis에 그대로 복붙 | 중 | `SYSTEM_PROMPT` 원칙 6 "정제하여 자신의 언어로" 지시 + 실사용 로그 모니터링 |
| **`format()` KeyError**: 템플릿 플레이스홀더 추가 후 호출 인자 누락 | 중 | Phase B의 기본값 선언 + Phase D-1 에서 format 호출 smoke test 필수 |
| **정상 경로 시그니처 변경**: `run_normal_reason` 기존 monkeypatch 경로가 인자 수를 검증하면 깨짐 | 낮음 | 기본값 제공으로 positional 호환 유지, Phase D-1 확인 |
| **`action_hint` 인자명 혼동**: State 키는 `action_ctx`, 함수 인자는 `action_hint` — 최종 응답의 `action`과 3개 이름이 공존 | 낮음 | docstring에 "action_ctx = Tool②의 권장 대응 (LLM 컨텍스트 힌트), action = LLM 생성 최종 대응" 명시 |
| **impact 빈 문자열 시 프롬프트 노이즈**: unknown event_id이면 impact가 "알 수 없는 이벤트 — 직접 판단 필요." → LLM 혼동 가능 | 낮음 | unknown impact 문구 자체가 LLM에 상황을 알리므로 허용; 필요 시 빈 문자열 폴백 고려 |

---

## 명시적 미주입 항목 (변경 없음)

아래 항목은 이 계획에서 **의도적으로 제외**한다. 미래에 재논의하려면 `build_plan.md` Phase 주석을 참고.

- ① `event_template` — `event_id`와 내용 유사, 불필요
- ④ `socket_position` / `processor_unit` — 원본 `node` 문자열 중복
- ③ `importance` — 설계상 의도적 제외
- ①③ `matched` / `cluster_matched` / 기타 메타 플래그

---

## 영향 파일 요약

| 파일 | 변경 유형 | 주요 내용 |
|------|-----------|-----------|
| `app/agents/graph.py` | 수정 | `llm_node`: `category`/`impact`/`action_ctx` 추출 후 함수 호출 인자에 추가 |
| `app/agents/diagnosis_agent.py` | 시그니처 확장 | `run_diagnosis(*, category, impact, action_hint)`, `run_normal_reason(*, category, impact)` |
| `app/agents/prompts/diagnosis.py` | 템플릿 + 시스템 지시 수정 | 결정적 산출값 블록 3줄 추가, 정상 컨텍스트 블록 신설, echo 방지 원칙 2건 |
| `tests/test_analyze.py` | 테스트 추가 | 이상/정상 경로 주입 검증 각 1건 |
