# Chok AI Backend

로그 분석 자동화 시스템의 **FastAPI/Python AI 분석 백엔드**입니다.
Spring Boot에서 전달받은 (FATAL 1차 필터를 통과한) 로그를 받아 **정상/이상 판정과 근거 설명(정상 사유 포함)** 을 생성합니다.

분석은 **LangGraph** 기반 파이프라인으로 수행되며, 두 가지 방법으로 실행·확인할 수 있습니다.

- **FastAPI 서버** (Swagger) — 실제 API 호출 방식
- **LangGraph Studio** — 그래프 흐름을 시각적으로 보며 실행하는 방식

> 기술 스택: FastAPI · LangGraph · LangChain-OpenAI · Pydantic v2 · uv

---

## 1. 준비사항

- **Python 3.12** (`>=3.12,<3.13`)
- **[uv](https://docs.astral.sh/uv/)** — 패키지/실행 관리
- **OpenAI API Key** — 실제 분석은 LLM을 호출하므로 필요 (`/health`는 키 없이 동작)

### 1) 의존성 설치

```bash
uv sync
```

### 2) 환경 변수 설정 (`.env`)

프로젝트 루트에 `.env` 파일을 만들고 값을 채웁니다.

```dotenv
OPENAI_API_KEY=sk-...          # 필수
LANGSMITH_TRACING=false        # LangSmith를 쓰지 않을 때
CHOK_AI_LOG_LEVEL=INFO         # 로그 레벨 (기본 INFO)
```

> `.env`·키·credential 등 민감 파일은 커밋/업로드하지 않습니다.

---

## 2. FastAPI 서버 실행

```bash
# 개발용 (코드 변경 시 자동 리로드)
uv run uvicorn app.main:app --reload

# 포트 지정 / 외부 접속 허용
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

실행 후 접속:

| 경로 | 용도 |
| --- | --- |
| `http://127.0.0.1:8000/docs` | **Swagger UI** — 브라우저에서 직접 요청·응답 시험 (가장 쉬움) |
| `http://127.0.0.1:8000/redoc` | ReDoc 문서 |
| `http://127.0.0.1:8000/health` | 헬스 체크 (키 불필요) |
| `POST /ai/v1/analyze` | 단건 분석 |
| `POST /ai/v1/analyze/batch` | 다건 분석 (최대 400건) |

### 수동 호출 예시

가장 쉬운 방법은 `http://127.0.0.1:8000/docs`(Swagger)에서 **Try it out** 으로 보내는 것입니다. CLI로는:

```bash
curl -X POST http://127.0.0.1:8000/ai/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "logId": 10293, "node": "R04-M1-N4-I:J18-U11", "nodeRepeat": "R04-M1-N4-I:J18-U11",
    "component": "APP", "logType": "RAS", "occurredAt": "2005-06-04 00:24:32",
    "logLevel": "FATAL", "content": "data storage interrupt", "domain": "BGL"
  }'
```

<details>
<summary>다건(batch) 호출 · PowerShell 예시</summary>

```bash
# 다건 분석 (최대 400건)
curl -X POST http://127.0.0.1:8000/ai/v1/analyze/batch \
  -H "Content-Type: application/json" \
  -d '{
    "logs": [
      {"logId": 10293, "node": "R04-M1-N4-I:J18-U11", "nodeRepeat": "R04-M1-N4-I:J18-U11",
       "component": "APP", "logType": "RAS", "occurredAt": "2005-06-04 00:24:32",
       "logLevel": "FATAL", "content": "data storage interrupt", "domain": "BGL"},
      {"logId": 10294, "node": "R16-M0-NB-C:J07-U11", "nodeRepeat": "R16-M0-NB-C:J07-U11",
       "component": "KERNEL", "logType": "RAS", "occurredAt": "2005-06-04 00:25:11",
       "logLevel": "FATAL", "content": "rts: kernel terminated for reason 1001", "domain": "BGL"}
    ]
  }'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/ai/v1/analyze `
  -ContentType "application/json" `
  -Body '{"logId":10293,"node":"R04-M1-N4-I:J18-U11","nodeRepeat":"R04-M1-N4-I:J18-U11","component":"APP","logType":"RAS","occurredAt":"2005-06-04 00:24:32","logLevel":"FATAL","content":"data storage interrupt","domain":"BGL"}'
```

</details>

### 로그

서버 로그는 **콘솔**과 **`logs/app.log`**(루트, 최초 실행 시 자동 생성)에 동시 기록됩니다.

- 10 MB 초과 시 자동 로테이션, 최대 5개 보관 (`app.log.1` ~ `app.log.5`)
- 레벨 조절: `.env`의 `CHOK_AI_LOG_LEVEL`(기본 `INFO`) 또는 실행 시 환경 변수

```powershell
# 예: DEBUG 레벨로 실행 (PowerShell)
$env:CHOK_AI_LOG_LEVEL = "DEBUG"; uv run uvicorn app.main:app --reload
```

---

## 3. LangGraph Studio 실행 및 사용

그래프 흐름과 각 단계(tool 호출)를 **시각적으로 보며 실행**하는 방법입니다. (FastAPI 서버와는 **별개 서버**입니다.)

### 실행

```powershell
# Windows PowerShell — cp949 인코딩 오류 방지를 위해 PYTHONUTF8=1 권장
$env:PYTHONUTF8 = "1"
uv run langgraph dev
```

```bash
# macOS / Linux
uv run langgraph dev
```

실행하면 콘솔에 접속 URL이 출력됩니다.

- **Studio UI**: `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`
- 로컬 API: `http://127.0.0.1:2024` (API 문서: `/docs`)

> Studio 화면은 smith.langchain.com에서 호스팅되지만 **데이터는 로컬 2024 서버**에 연결됩니다.
> 브라우저가 자동으로 열리지 않으면 위 Studio URL을 직접 입력하세요.

### 사용 방법

1. 좌측에서 그래프 **`analysis`** 를 선택합니다. (`langgraph.json`에 등록된 이름)
2. **Input** 패널에 로그 JSON을 입력합니다. (camelCase 그대로 — 입력 정규화 노드가 변환)

   ```json
   {
     "log": {
       "logId": 10293,
       "node": "R04-M1-N4-I:J18-U11",
       "nodeRepeat": "R04-M1-N4-I:J18-U11",
       "component": "APP",
       "logType": "RAS",
       "occurredAt": "2005-06-04 00:24:32",
       "logLevel": "FATAL",
       "content": "data storage interrupt",
       "domain": "BGL"
     }
   }
   ```

3. **Submit** 을 누르면 그래프가 단계별로 실행되며, 각 노드의 입력/출력 state와 LLM의 tool 호출 내역을 클릭해 확인할 수 있습니다.
4. 우측 결과에서 최종 `result`(`eventId`/`riskLevel`/`summary`/`analysis`/`action`/`clusterId`)를 확인합니다.

> **다른 입력으로 분기 확인**
> - `"content": "data storage interrupt"` → 이상(긴급)
> - `"content": "instruction cache parity error corrected"` → 정상

### 참고

- 실행에는 `.env`의 `OPENAI_API_KEY`가 필요합니다 (그래프가 실제 LLM을 호출).
- LangSmith 연동은 **선택**입니다. 사용하지 않으면 `.env`에 `LANGSMITH_TRACING=false`만 두면 Studio는 정상 동작합니다.
- Studio(`langgraph dev`, 포트 **2024**)와 Swagger(`uvicorn`, 포트 **8000**)는 별개 서버라, 한쪽 호출은 다른 쪽 화면에 보이지 않습니다.

---

<details>
<summary><b>📦 프로젝트 구조 · 패키지 책임</b></summary>

| Package | 책임 |
| --- | --- |
| `app` | FastAPI 애플리케이션 진입점과 전체 서버 골격 |
| `app.api` | Spring Boot에서 호출할 HTTP endpoint 경계 |
| `app.schemas` | Spring-FastAPI 요청/응답 DTO 계약 |
| `app.services` | 라우터와 Agent 사이의 분석 흐름 조합 |
| `app.agents` | 이상 로그 근거 설명 / 정상 사유 생성 로직, LangGraph 분석 파이프라인 |
| `app.agents.tools` | 결정적 분석 Tool(`event_template`·`anomaly_classifier`·`cluster`·`node_info`)과 메타데이터 |
| `app.core` | 설정, CORS, 로깅, 공통 예외 처리 등 서버 공통 정책 |
| `tests` | FastAPI 기본 동작, DTO 계약, 분석 흐름 검증 |

주요 패키지에는 `README.md`가 있어 담당자와 책임/제외 범위를 적어두었습니다.

**동작 흐름 (참고):** `ingest → agent ⇄ tools_exec → guard → reasoning → map`
LLM이 tool 호출을 결정하되, 어떤 툴이 실행되는지는 `tool_choice` 강제와 사후 가드레일로 결정적으로 보장됩니다.

</details>

<details>
<summary><b>🧭 프로젝트 범위 · 책임 경계 (Spring ↔ FastAPI)</b></summary>

P0 범위:

- Spring Boot에서 FATAL 레벨로 1차 필터링된 로그 분석 요청 처리
- 분석 파이프라인에서 정상/이상 직접 판정 및 긴급도 분류
- 이상 판정 로그의 근거 설명 / 정상 판정 로그의 정상 사유 생성
- Spring-FastAPI 요청/응답 DTO 계약 유지

책임 경계:

- FastAPI는 Spring Boot DB에 직접 접근하지 않으며, 분석 결과를 직접 저장하지 않습니다. (저장은 Spring `domain.analysis`/`domain.pattern` 책임)
- 로그 조회·분석 대상 선정은 Spring 책임입니다.
- FastAPI는 FATAL 1차 필터를 통과한 로그의 정상/이상을 직접 판정합니다.
- 정확도 검증(Precision/Recall/F1)은 **Spring 담당** — Spring이 저장한 BGL 라벨(정답)과 FastAPI status를 비교, 어드민(내부) 지표로만 사용. 분석 요청 DTO에는 label을 포함하지 않습니다(판정 누수 방지).
- 반복 패턴(클러스터)은 분류 Tool이 처리하며 별도 endpoint를 두지 않습니다.
- `app.api`는 HTTP 경계만 담당하고 분석 흐름은 `app.services`/`app.agents`로 분리합니다.

</details>

<details>
<summary><b>✅ 구현 현황</b></summary>

구현됨:

- FastAPI 애플리케이션 shell, Health check, CORS, `X-Process-Time` 미들웨어
- 전역 예외 처리 (VALIDATION_ERROR / LLM_TIMEOUT / LLM_ERROR / INTERNAL_ERROR)
- pydantic-settings 기반 공통 설정, 패키지별 담당/책임 README
- 분석 endpoint (`POST /ai/v1/analyze`, `POST /ai/v1/analyze/batch`)
- Spring-FastAPI 요청/응답 DTO (camelCase 계약, 응답 `isAbnormal` 포함)
- 이상 로그 근거 설명 / 정상 사유 Agent, OpenAI(LLM) 구조화 출력
- LangGraph 분석 파이프라인 — agentic tool-calling + 결정적 가드레일
- 분석 Tool: `anomaly_classifier`·`cluster`·`event_template`·`node_info` + 메타데이터
- LangGraph Studio(`langgraph dev`) 지원 — 입력 정규화 노드로 JSON 직접 실행
- 콘솔+파일 로깅(`logs/app.log`, 로테이션) 및 분석 완료 시 응답 판정값 로깅
- 분석 흐름 테스트 (analyze·batch·에러 매핑)
- 실 데이터 기반 Tool 파라미터·프롬프트 튜닝 및 시나리오 검증 보강
- Spring batch 연동 end-to-end 안정화


엔드포인트·분기·도구별 시험 항목 전체는 [`TEST_CASES.csv`](TEST_CASES.csv) 참고.

</details>

<details>
<summary><b>🔒 로컬 지침 파일</b></summary>

공유 지침 파일: `AGENTS.md`, `CLAUDE.md`

개인 로컬 지침 파일은 Git에서 제외됩니다: `AGENTS.local.md`, `CLAUDE.local.md`
로컬 지침 파일, `.env`, secret, credential, key, private config는 커밋/업로드하지 않습니다.

</details>
