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

## API 서버 구동 및 수동 테스트

> pytest는 LLM을 monkeypatch하지만, **실제 서버를 띄워 직접 호출**하려면 `.env`에 `OPENAI_API_KEY`가 있어야 한다(분석 요청이 실제 OpenAI를 호출). 키가 비어 있으면 분석 요청 시 오류가 난다. `/health`는 키 없이도 동작한다.

### 서버 실행

```bash
# 개발용 (코드 변경 시 자동 리로드)
uv run uvicorn app.main:app --reload

# 포트 지정 / 외부 접속 허용
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

기본 주소: `http://127.0.0.1:8000`
Swagger UI 주소: `http://127.0.0.1:8000/docs`

### 로그 출력 위치 및 레벨 설정

서버 실행 시 로그는 **콘솔(stdout)** 과 **`logs/app.log`** 두 곳에 동시 기록된다.

- 로그 파일 위치: 프로젝트 루트 `logs/app.log` (서버 최초 실행 시 자동 생성)
- 로테이션: 10 MB 초과 시 자동 교체, 최대 5개 보관 (`app.log.1` ~ `app.log.5`)

로그 레벨 변경은 환경 변수로 override한다.

```bash
# DEBUG 레벨로 실행 (상세 로그)
CHOK_AI_LOG_LEVEL=DEBUG uv run uvicorn app.main:app --reload

# WARNING 이상만 출력
CHOK_AI_LOG_LEVEL=WARNING uv run uvicorn app.main:app --reload
```

Windows PowerShell:

```powershell
$env:CHOK_AI_LOG_LEVEL = "DEBUG"
uv run uvicorn app.main:app --reload
```

기본 로그 레벨은 `INFO`이며 `.env` 파일에 `CHOK_AI_LOG_LEVEL=DEBUG`를 추가해도 된다.

| 경로 | 메서드 | 용도 |
| --- | --- | --- |
| `/health` | GET | 헬스 체크 (키 불필요) |
| `/docs` | GET | Swagger UI — 브라우저에서 직접 요청·응답 시험 |
| `/redoc` | GET | ReDoc 문서 |
| `/ai/v1/analyze` | POST | 단건 분석 |
| `/ai/v1/analyze/batch` | POST | 다건 분석 (최대 400건) |

### 수동 호출 예시

```bash
# 헬스 체크
curl http://127.0.0.1:8000/health
#   → {"status":"ok"}

# 단건 분석 (이상 이벤트 예시)
curl -X POST http://127.0.0.1:8000/ai/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "logId": 10293,
    "node": "R04-M1-N4-I:J18-U11",
    "nodeRepeat": "R04-M1-N4-I:J18-U11",
    "component": "APP",
    "logType": "RAS",
    "occurredAt": "2005-06-04 00:24:32",
    "logLevel": "FATAL",
    "content": "data storage interrupt",
    "domain": "BGL"
  }'

# 다건 분석 (로그 2건 — 최대 400건까지)
curl -X POST http://127.0.0.1:8000/ai/v1/analyze/batch \
  -H "Content-Type: application/json" \
  -d '{
    "logs": [
      {
        "logId": 10293,
        "node": "R04-M1-N4-I:J18-U11",
        "nodeRepeat": "R04-M1-N4-I:J18-U11",
        "component": "APP",
        "logType": "RAS",
        "occurredAt": "2005-06-04 00:24:32",
        "logLevel": "FATAL",
        "content": "data storage interrupt",
        "domain": "BGL"
      },
      {
        "logId": 10294,
        "node": "R16-M0-NB-C:J07-U11",
        "nodeRepeat": "R16-M0-NB-C:J07-U11",
        "component": "KERNEL",
        "logType": "RAS",
        "occurredAt": "2005-06-04 00:25:11",
        "logLevel": "FATAL",
        "content": "rts: kernel terminated for reason 1001",
        "domain": "BGL"
      }
    ]
  }'
```

PowerShell이면 `Invoke-RestMethod`:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/ai/v1/analyze `
  -ContentType "application/json" `
  -Body '{"logId":10293,"node":"R04-M1-N4-I:J18-U11","nodeRepeat":"R04-M1-N4-I:J18-U11","component":"APP","logType":"RAS","occurredAt":"2005-06-04 00:24:32","logLevel":"FATAL","content":"data storage interrupt","domain":"BGL"}'
```

> 가장 쉬운 수동 테스트는 `GET /docs`(Swagger UI)에서 **Try it out**으로 직접 요청을 보내는 것이다.

### 테스트 케이스 목록

엔드포인트·분기·도구별 시험 항목 전체는 [`TEST_CASES.csv`](TEST_CASES.csv) 참고.

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
