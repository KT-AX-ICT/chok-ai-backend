# Tests

## Package Owner

- 최종 구조/리뷰 책임: 박가희

## Scope Ownership

| Scope | Primary | Support | Notes |
| --- | --- | --- | --- |
| FastAPI smoke test | 박가희 | 박연지 | 서버 기본 기동과 health check를 검증한다. |
| DTO contract test | 박가희 | 이석진, 이예지 | Spring-FastAPI 요청/응답 DTO 계약을 검증한다. |
| 분석 흐름 test | 박가희 | 고유경, 윤혜림 | 라벨 기준과 reason 포함 여부를 검증한다. |
| 반복 패턴 test | 박가희 | 윤혜림 | 패턴 응답 구조와 필수 필드를 검증한다. |

## Scope

- FastAPI 기본 동작 검증
- Spring-FastAPI DTO 계약 검증
- 라벨 기반 분석 흐름 검증
- 반복 패턴 응답 구조 검증

## 테스트 실행 방법 (How to Run)

> **OpenAI API key 불필요.** LLM·Tool 호출은 monkeypatch로 대체되므로 secret 없이 전부 통과한다.
> (실제 OpenAI 호출이 필요한 테스트는 없다 — 외부 네트워크 의존 테스트는 Out Of Scope.)

### 사전 준비 (최초 1회)

```bash
uv sync          # 의존성 설치 (.venv 생성/동기화)
```

### 전체 테스트 실행

```bash
uv run python -m pytest            # 전체 실행
uv run python -m pytest -q         # 간결 출력
uv run python -m pytest -v         # 테스트별 상세 출력
```

### 일부만 실행

```bash
# 특정 파일
uv run python -m pytest tests/test_analyze.py

# 특정 디렉토리
uv run python -m pytest tests/event_template

# 이름 패턴으로 골라 실행 (-k)
uv run python -m pytest -k "branch"          # 분기 테스트만
uv run python -m pytest -k "concurrency_cap" # 배치 동시성 상한 테스트만

# 특정 테스트 한 건
uv run python -m pytest tests/test_analyze.py::test_analyze_normal_path
```

### 테스트 구성

| 위치 | 검증 대상 |
| --- | --- |
| `test_health.py` | FastAPI 기동 + `/health` smoke test |
| `test_analyze.py` | 엔드포인트 계약(camelCase 직렬화·`eventId`/`errorMessage` 위치)·정상/이상 분기·에러 매핑(422/502/503)·배치 부분 실패·동시성 상한 |
| `event_template/` | Tool① 이벤트 템플릿 분류 (단위·정확도·시나리오) |
| `cluster/` | Tool③ 클러스터 분류 |
| `node_info/` | Tool④ Node 정보 조회 |
| `pipeline_scenarios/` | Tool①→②→③→④ 파이프라인 통합 |

> 참고: `StarletteDeprecationWarning`(httpx/TestClient) 1건은 기능과 무관한 경고이며 통과에 영향 없다.

## Responsibilities

- OpenAI API key 같은 secret 없이 통과 가능한 테스트를 우선 작성한다.
- AI 호출 자체보다 라벨 기준, 응답 필드, 오류 흐름을 검증한다.
- 분석 결과에 reason이 포함되는지 확인한다.
- BGL 라벨 기준을 재현 가능한 방식으로 검증한다.

## Out Of Scope

- 실제 LLM 품질 평가
- Spring Boot 통합 테스트
- DB 저장 검증
- 외부 네트워크 의존 테스트
