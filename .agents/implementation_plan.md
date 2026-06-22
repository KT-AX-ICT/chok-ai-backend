# 로그 분석 자동화 AI 백엔드 개발 계획

- FastAPI 기반 AI 백엔드의 단계별 개발 순서를 제안
- 이 순서는 의존성이 없는 기본 뼈대부터 시작하여 점진적으로 AI 기능을 통합하고, 최종적으로 API 게이트웨이를 완성하는 방향으로 구성

## 1단계: 프로젝트 환경 설정 및 기본 뼈대 구축
가장 먼저 FastAPI 프로젝트의 구조를 잡고 필요한 패키지를 설치합니다.
- **의존성 설치:** `fastapi`, `uvicorn`, `pydantic`, `langchain`, `langgraph`(Agent 오케스트레이션), 그리고 LLM 연동 라이브러리(`langchain-openai` 등)
  > [변경] ChromaDB 미사용 — Tool이 **내부 정의 문서를 직접 참조**하므로 벡터 DB 의존성 제거
- **디렉토리 구조 설계:** 
  - `routers/`: API 엔드포인트 정의
  - `models/`: Pydantic Request/Response 스키마
  - `services/`: 비즈니스 로직 및 Agent 워크플로우   
      > [수정 제안] 현재 `agents/`를 `services/`로 통합하는 것을 제안
  - `tools/`: Agent가 사용할 도구 (이벤트 템플릿 분류, 이상 여부+긴급도 분류, 클러스터 분류, Node 정보 조회)
  - `core/`: 내부 정의 문서 참조 및 환경 변수 설정
- **환경 변수 설정:** `.env` 파일 생성 및 `config.py` (API 키, 내부 정의 문서 경로 등 설정 관리) 작성   
  > [참고] `config.py`는 `core/`에서 관리

## 2단계: API 데이터 모델(DTO) 정의 및 라우터 뼈대 구현
[API.md](API.md)의 명세·설계를 바탕으로 데이터 규격을 정의하고, 그 즉시 엔드포인트 뼈대를 만들어 **API 계약을 일찍 고정**합니다. (라우터 뼈대는 DTO만 있으면 만들 수 있으므로 함께 진행)
- **DTO 정의 (`models/` 폴더 하위):**
  - **공통 베이스모델:** `CamelModel` (camelCase 별칭 + `populate_by_name`)
  - **공통 타입:** `RiskLevel`·`LogStatus`(Literal 한글), `ProcessStatus`(Enum `success`/`fail`)
  - **분석 결과 본문(공통):** `AnalysisResult` (단건·배치 공유, 개별 로그 `analyzedAt` 포함)
  - **단건 분석 모델:** Request(`LogAnalyzeRequest`), Response(`LogAnalyzeResponse` — `status` 포함, `result`는 정상·이상 모두 포함)
  - **다건 분석 모델:** Request(`LogBatchAnalyzeRequest`), Response(`LogBatchAnalyzeResponse`, `LogBatchResultItem` — `processStatus`/`status` 구분)
  - **에러 모델:** `ErrorResponse` (`code`·`message`·`detail`)
  > [참고] API 명세([API.md](API.md)) 기반 작성. 요청에서 `label`·`eventId` 제외, 응답에 `eventId`·`status`(정상/이상) 포함
  > [참고] 베이스모델 구조·에러 처리 설계는 [ModelDesign.md](ModelDesign.md)
- **라우터 뼈대 (`routers/analyze.py`):** 경로·시그니처·DTO 연결까지만 구성하고, 내부 로직은 **Mock 응답으로 대체**
  - `POST /ai/v1/analyze`, `POST /ai/v1/analyze/batch` 엔드포인트 정의
  - 실제 Agent 연결은 4단계 완성 후 5단계에서 교체
  > [효과] Agent 미완성 상태에서도 Spring 팀이 API 스펙 기준으로 병렬 연동 테스트 가능

## 3단계: Agent용 Tool(도구) 모듈 개발
Agent가 분석에 필요한 컨텍스트를 산출할 **4개의 Tool**을 독립적으로 개발하고 테스트합니다.
모든 Tool은 ChromaDB 대신 **내부 정의 문서를 직접 참조**합니다.
> 상세 구현 목록: [step3_tools.md](step3_tools.md)
- **① 이벤트 템플릿 분류 Tool:** 로그를 사전 정의된 이벤트 템플릿에 매칭하여 `eventId` 산출 (규칙 기반)
  > [참고] ②·③의 **선행 조건** — 템플릿이 분류돼야 이상 여부·클러스터 판정이 가능
- **② 이상 여부 판단 + 긴급도 분류 Tool:** 템플릿 기반으로 정상/이상 판정 및 위험도(`riskLevel`) 산정
  > [참고] 1차 필터(FATAL)만 거친 로그이므로, **이상 여부를 내부에서 최종 판단**
- **③ 클러스터(패턴) 분류 Tool:** 템플릿 기반으로 유사 로그 패턴(클러스터)을 식별하여 `clusterId` 산출
- **④ Node별 정보 조회 Tool:** `node` 기준 부가 정보를 조회해 분석 컨텍스트로 제공 (②③과 마찬가지로 ① 결과 이후 수행)

## 4단계: LangGraph 기반 AI Agent 구축
개발한 4개 도구를 LangGraph `StateGraph`의 노드로 명시적으로 연결하여 분석 흐름을 구성합니다. (Tool 호출 여부·순서를 LLM의 임의 판단에 맡기지 않고 그래프로 고정. 단, **②가 정상으로 판정하면 ③④를 건너뛰는 빠른 경로**로 분기)
> 상세 구현 목록: [step4_agent.md](step4_agent.md)
- **State 정의:** 원본 로그, `eventId`, 이상 여부(`status`)·`riskLevel`, `clusterId`, Node 컨텍스트, 최종 분석 결과를 담는 상태(`TypedDict`) 설계
- **노드 구성 (`services/agent_service.py`):**
  - `이벤트 템플릿 분류 노드`: ① Tool 호출 → State에 `eventId` 기록 (**선행 노드**)
  - `이상 여부 + 긴급도 분류 노드`: ② Tool 호출 → State에 이상 여부(`status`)·`riskLevel` 기록 (**분기 기준 노드**)
  - `클러스터 분류 노드`: ③ Tool 호출 → State에 `clusterId` 기록 (이상일 때)
  - `Node 정보 조회 노드`: ④ Tool 호출 → State에 Node 컨텍스트 기록 (이상일 때)
  - `LLM 분석 노드`: 확보된 컨텍스트와 원본 로그를 LLM에 전달하여 분석 내용·대응 방안 작성 (정상이면 정상 사유만)
  - `결과 매핑 노드`: LLM 구조화 출력(`with_structured_output`)을 받아 API 응답 규격에 매핑 (`eventId`·`status` 포함, `정상`이면 `result`에 정상 사유만)
- **엣지 연결:**
  - `START → 이벤트 템플릿 분류 → 이상 여부 + 긴급도 분류`
  - **조건부 분기**(`add_conditional_edges`, 기준은 ② 노드): **정상**이면 곧장 `LLM 분석`으로, **이상**이면 `클러스터 분류`·`Node 정보 조회` 두 노드로 fan-out
  - `(클러스터 분류 · Node 정보 조회) → LLM 분석`
  - `LLM 분석 → 결과 매핑 → END`
- **시스템 프롬프트 설계:** 이상 로그의 근거 설명, 요약, 대응 방안을 작성하도록 지시하고 출력 형식을 지정

## 5단계: Agent 서비스 연결 및 에러 핸들링
2단계에서 만든 라우터 뼈대의 **Mock 응답을 실제 Agent 서비스 호출로 교체**합니다.
- **서비스 연결 (`routers/analyze.py`):**
  - `POST /ai/v1/analyze`: Mock 제거 → `agent_service` 단건 분석 호출 → 결과 반환
  - `POST /ai/v1/analyze/batch`: 다건 요청 비동기 병렬 처리(`asyncio.gather` 등 활용) → 전체 결과 취합 및 반환
- **에러 핸들링 보완:** AI 응답 지연(타임아웃), 내부 정의 문서 로드 실패, 구조화 출력 파싱 오류 등 예외 처리 추가

## 6단계: 테스트 및 고도화
- **단위 및 통합 테스트:** 정상 흐름과 예외 상황에 대한 API 테스트
- **모의(Mock) 통신 테스트:** Spring Boot에서 넘어오는 것과 동일한 구조의 더미 데이터를 사용해 게이트웨이 테스트
- **최적화:** 대량의 배치 로그 분석 시 동시성 제어(Rate Limit 방지 등) 및 프롬프트 튜닝
