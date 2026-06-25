# Chok AI Backend

로그 분석 자동화 시스템의 FastAPI/Python AI 분석 백엔드 프로젝트입니다.

FastAPI는 Spring Boot에서 전달받은 로그를 기준으로 정상/이상 판정과 이상 로그 근거 설명(정상 사유 포함)을 담당합니다. 반복 패턴(클러스터)은 분류 Tool이 처리하며, 라벨 기반 정확도 검증 산출, BGL seed data 적재, 분석 결과 저장·조회, Scheduler 실행, 대시보드/어드민 API는 Spring Boot 영역입니다.

## 기술 스택

- Python 3.12
- FastAPI
- Uvicorn
- Pydantic v2
- pydantic-settings
- LangGraph (분석 파이프라인 그래프)
- LangChain OpenAI (`langchain-openai`, LLM 구조화 출력)
- uv

## 빠른 시작

### 의존성 설치

```bash
uv sync
```

### 서버 실행

```bash
uv run uvicorn app.main:app --reload
```

서버 실행 후 아래 경로를 확인합니다.

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health Check: `http://localhost:8000/health`

## 프로젝트 범위

P0 범위는 다음 흐름을 우선합니다.

- Spring Boot에서 FATAL 레벨로 1차 필터링된 로그 분석 요청 처리
- 분석 파이프라인(Tool②)에서 정상/이상 직접 판정 및 긴급도 분류
- 이상 판정 로그의 근거 설명 / 정상 판정 로그의 정상 사유 생성
- Spring-FastAPI 요청/응답 DTO 계약 유지

정상/이상 판정은 FastAPI 분석 파이프라인(Tool②)이 직접 수행합니다. 분석 요청에는 정답 라벨(label)을 포함하지 않습니다(판정 누수 방지). 라벨 기반 정확도(Precision/Recall/F1) 산출은 **Spring이 담당**하며, 결과는 어드민(내부) 지표로만 사용합니다(유저 비노출). 반복 패턴(클러스터)은 분류 Tool이 처리하므로 별도 FastAPI endpoint를 두지 않습니다.

## 패키지 책임

| Package | 책임 |
| --- | --- |
| `app` | FastAPI 애플리케이션 진입점과 전체 서버 골격 |
| `app.api` | Spring Boot에서 호출할 HTTP endpoint 경계 |
| `app.schemas` | Spring-FastAPI 요청/응답 DTO 계약 |
| `app.services` | 라우터와 Agent 사이의 분석 흐름 조합 |
| `app.agents` | 이상 로그 근거 설명 / 정상 사유 생성 로직 |
| `app.data` | BGL 구조 확인, 분석 입력 구조, 검증용 데이터 처리 |
| `app.core` | 설정, CORS, 공통 예외 처리 등 서버 공통 정책 |
| `tests` | FastAPI 기본 동작, DTO 계약, 분석 흐름 검증 기준 |

주요 패키지에는 `README.md`가 있으며, 패키지 책임자, scope별 담당자, 책임 범위, 제외 범위를 적어두었습니다.

## 책임 경계

- FastAPI는 Spring Boot DB에 직접 접근하지 않습니다.
- FastAPI는 분석 결과를 직접 저장하지 않습니다.
- 분석 결과 저장은 Spring Boot `domain.analysis` 책임입니다.
- 반복 패턴 결과 저장은 Spring Boot `domain.pattern` 책임입니다.
- 로그 조회와 분석 대상 선정은 Spring Boot `domain.log` 또는 application/service 계층 책임입니다.
- FastAPI는 FATAL 1차 필터를 통과한 로그의 정상/이상 여부를 직접 판정합니다(Tool②).
- 정확도 검증(Precision/Recall/F1)은 **Spring이 담당**합니다. Spring이 저장한 BGL 라벨(정답)과 FastAPI가 반환한 status를 비교해 산출하고, 어드민(내부) 지표로만 사용합니다. FastAPI 분석 요청 DTO에는 label을 포함하지 않습니다.
- 반복 패턴(클러스터)은 분류 Tool이 처리하며, 별도 FastAPI endpoint를 두지 않습니다.
- `app.api`는 HTTP 경계만 담당하고, 분석 흐름은 `app.services`와 `app.agents`로 분리합니다.

## 로컬 지침 파일

공유 지침 파일:

- `AGENTS.md`
- `CLAUDE.md`

개인 로컬 지침 파일은 Git에서 제외됩니다.

- `AGENTS.local.md`
- `CLAUDE.local.md`

로컬 지침 파일, `.env`, secret, credential, key, private config 파일은 커밋하거나 업로드하지 않습니다.

## 현재 초기 구성

구현됨:

- FastAPI 애플리케이션 shell
- Health check endpoint
- Spring Boot CORS 설정과 맞춘 로컬 CORS 설정
- `X-Process-Time` 응답 헤더 미들웨어
- 전역 예외 처리 (VALIDATION_ERROR / LLM_TIMEOUT / LLM_ERROR / INTERNAL_ERROR)
- pydantic-settings 기반 공통 설정
- 패키지별 담당/책임 README
- 분석 endpoint (`POST /ai/v1/analyze`, `POST /ai/v1/analyze/batch`)
- Spring-FastAPI 요청/응답 DTO (camelCase 계약, 응답 is_abnormal(bool) 포함)
- 이상 로그 근거 설명 / 정상 사유 Agent
- OpenAI(LLM) 연동 및 구조화 출력
- LangGraph 분석 파이프라인 (`app/agents/graph.py`)
- 분석 Tool 구현: 이상 판정(`anomaly_classifier`) · 반복 패턴 클러스터(`cluster`) · 이벤트 템플릿(`event_template`) · 노드 정보 조회(`node_info`) + 메타데이터(`clusters`/`event_analysis_v2`/`event_template`/`node_stats`)
- 분석 흐름 테스트 (analyze·batch·에러 매핑)

진행 중 / 남은 작업:

- 실 데이터 기반 Tool 파라미터·프롬프트 튜닝 및 시나리오 검증 보강
- Spring batch 연동(동시 5) end-to-end 안정화

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