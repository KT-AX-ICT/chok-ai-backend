# 변경 기록 — 컨텍스트 태그 단순화 · 프롬프트 정비 · GPT-5 전환 (2026-06-26)

## 배경

LangGraph agent 파이프라인의 컨텍스트 태그와 시스템 프롬프트 사이에 표기가 어긋나 있었고,
분석 품질을 끌어올리기 위해 추론 모델을 상위 모델로 교체했다. 관련 변경을 한 번에 정리한다.

- 시스템 프롬프트 규칙 #1은 "tag가 'BGL'이면 툴을 사용"이라고 기술하는데, 실제 state·주입 컨텍스트에는
  `"BGL 로그 데이터"`라는 긴 토큰이 흘러 다녔다. 동작은 했으나 프롬프트가 기대하는 토큰과 실제 토큰이 불일치했다.
- 운영 로그상 툴 미호출 시 `guard_node`(결정적 보강)가 약 4%(62/1508) 발생했는데, 이는 태그 누락이 아니라
  LLM이 드물게 강제 tool_call을 빠뜨린 경우의 안전망 동작이었다(`BGL 태그 없음` 조기종료는 0회).
  보강 빈도를 줄이기 위한 레버는 프롬프트가 아니라 모델 품질 쪽이라 판단해 모델을 상향했다.

## 변경 사항

### 1. 컨텍스트 태그를 `BGL`로 단순화
시스템 프롬프트가 검사하는 토큰(`'BGL'`)과 실제 주입 토큰을 일치시킨다.

- `app/agents/graph.py`
  - `_BGL_TAG = "BGL"` (기존 `"BGL 로그 데이터"`)
  - 모듈 docstring·`AgentState.tag` 주석·`agent_node` docstring의 텍스트 참조를 `"BGL"`로 정리
  - seed HumanMessage는 `[태그] {tag}` 그대로 — 이제 `[태그] BGL`이 주입됨
- `app/services/analysis_service.py`
  - 단건 진입 `initial_state`의 `"tag": "BGL"`
- `tests/test_analyze.py`
  - 입력 state의 `"tag"` 4곳, `test_ingest_node_defaults_tag`의 docstring·단언을 `"BGL"`로 갱신

> `ingest_node`는 tag 미지정 시 `_BGL_TAG`로 기본값을 보강하므로 Studio/JSON 입력도 자동으로 `BGL`을 사용한다.

### 2. 시스템 프롬프트 정비
- `app/agents/prompts/diagnosis.py`
  - **규칙 #1 복원**: `컨텍스트 tag가 'BGL'이면 반드시 제공된 툴을 사용해야 합니다.`
  - 이상 로그 프롬프트(`SYSTEM_PROMPT`): analysis 개조식 작성 지시, summary는 핵심 한 문장(공백 포함 50자 내외),
    action은 한 줄 안내 후 단계별 개조식, impact/action_hint 표현 정제
  - 노드 언급 규칙: 노드 컨텍스트에 특이사항(예: 과거 이상 로그 다수 발생 노드)이 있을 때만 analysis에서 노드를 언급,
    특이사항이 없으면 생략 가능. **summary에는 노드를 언급하지 않도록** 명시
  - 정상 로그 프롬프트(`NORMAL_SYSTEM_PROMPT`/`NORMAL_USER_PROMPT_TEMPLATE`): analysis/summary를 개조식·50자 내외로 구조화,
    summary에 노드 미언급

### 3. 추론 모델 GPT-5 전환
- `app/core/config.py`
  - `llm_model = "gpt-5-2025-08-07"` (기존 `gpt-4o-mini`)
  - `llm_temperature = 1.0` — **GPT-5 계열은 temperature 기본값(1)만 허용**(다른 값 전달 시 API 에러)하므로 주석과 함께 고정
  - 이 설정은 agent 호출(`graph.py`)과 reasoning 호출(`diagnosis_agent.py`) 양쪽에 공통 적용된다

## 동작/계약 영향

| 항목 | 변경 |
|------|------|
| 응답 스키마(`/analyze`, `/analyze/batch`) | **불변** (필드·타입 동일) |
| 내부 컨텍스트 태그 | `"BGL 로그 데이터"` → `"BGL"` |
| 추론 모델 | `gpt-4o-mini` → `gpt-5-2025-08-07` |
| `llm_temperature` | `0.2` → `1.0` (GPT-5 제약) |
| 툴 강제 메커니즘 | 불변 — `tool_choice` 강제 + `guard_node` 결정적 보강 |

## 검증

```
uv run pytest -q
48 passed
```

## 후속 참고

- GPT-5는 추론(reasoning) 토큰을 `max_completion_tokens` 예산에서 먼저 소비한다. 2048에서는 구조화 출력이 잘려
  `finish_reason=length` → 구조화 파싱 실패(`LLMError "LLM 호출 또는 구조화 출력 실패"`)가 발생했다.
  이를 해소하기 위해 **`llm_max_tokens` 2048 → 8192로 상향**했다. (상한일 뿐이라 실제 비용은 생성 토큰만큼만 발생)
- 추가 최적화 여지: 이 LLM은 결정적 툴 산출값을 글로 옮기는 작업이라 무거운 추론이 불필요하므로,
  `reasoning_effort="low"` 적용 시 추론 토큰·지연·비용을 더 줄일 수 있다(미적용, 후속 검토).
- `CHOK_AI_LLM_MODEL` 환경변수로 모델을 override할 수 있다.
