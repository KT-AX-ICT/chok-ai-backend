# 로그 분석 자동화 AI 백엔드 개발 계획

- FastAPI 기반 AI 백엔드의 단계별 개발 순서를 제안
- 이 순서는 의존성이 없는 기본 뼈대부터 시작하여 점진적으로 AI 기능을 통합하고, 최종적으로 API 게이트웨이를 완성하는 방향으로 구성

## 1단계: 프로젝트 환경 설정 및 기본 뼈대 구축
가장 먼저 FastAPI 프로젝트의 구조를 잡고 필요한 패키지를 설치합니다.
- **의존성 설치:** `fastapi`, `uvicorn`, `pydantic`, `chromadb`, `langchain`, `langgraph`(Agent 오케스트레이션), 그리고 LLM 연동 라이브러리(`langchain-openai` 등)
- **디렉토리 구조 설계:** 
  - `routers/`: API 엔드포인트 정의
  - `models/`: Pydantic Request/Response 스키마
  - `services/`: 비즈니스 로직 및 Agent 워크플로우   
      > [수정 제안] 현재 `agents/`를 `services/`로 통합하는 것을 제안
  - `tools/`: Agent가 사용할 도구 (긴급도 판정, 패턴 검색 등)
  - `core/`: DB 연결(Chroma) 및 환경 변수 설정
- **환경 변수 설정:** `.env` 파일 생성 및 `config.py` (API 키, DB 설정 관리) 작성   
  > [참고] `config.py`는 `core/`에서 관리

## 2단계: API 데이터 모델 (DTO) 정의
`APIGuide.md`의 명세를 바탕으로 클라이언트(Spring Boot)와 주고받을 데이터 규격을 정의합니다. (`models/` 폴더 하위)
- **단건 분석 모델:** Request(`LogAnalyzeRequest`), Response(`LogAnalyzeResponse`, `LogAnalyzeResult`)
- **다건 분석 모델:** Request(`LogBatchAnalyzeRequest`), Response(`LogBatchAnalyzeResponse`, `LogBatchResultItem`)
  > [참고] API 명세서 기반 작성

## 3단계: Agent용 Tool(도구) 모듈 개발
Agent가 의사결정을 내리기 위해 사용할 기반 도구들을 독립적으로 개발하고 테스트합니다.
- **긴급도 분류 Tool (`tools/urgency.py`):** 로그 레벨이나 특정 키워드를 기반으로 긴급도를 판정하는 규칙 기반 로직
  > [참고] 데이터 분석 기반 분류 로직 작성
- **패턴 분류 Tool & ChromaDB 연동 (`tools/pattern.py`, `core/chromadb.py`):** 
  - ChromaDB 클라이언트 설정 및 초기화 로직
  - 과거 로그/패턴을 벡터화하여 검색(RAG)하는 기능 구현
  > [참고] chromadb 유사도 검색 진행하는 tool

## 4단계: LangGraph 기반 AI Agent 구축
개발한 도구들을 LangGraph `StateGraph`의 노드로 명시적으로 연결하여, 긴급도 분류와 패턴 분류가 **항상 실행되도록** 분석 흐름을 구성합니다. (Tool 호출 여부를 LLM의 임의 판단에 맡기지 않고, 그래프로 순서를 고정)
- **State 정의:** 원본 로그, 긴급도 결과, 패턴 컨텍스트, 최종 분석 결과를 담는 상태(`TypedDict`) 설계
- **노드 구성 (`services/agent_service.py`):**
  - `긴급도 분류 노드`: 긴급도 분류 Tool 호출 → State에 `riskLevel` 기록
  - `패턴 분류 노드`: 패턴 분류 Tool(ChromaDB 검색) 호출 → State에 유사 사례(Context) 기록
  - `LLM 분석 노드`: 확보된 긴급도·패턴 컨텍스트와 원본 로그를 LLM에 전달하여 분석 내용·대응 방안 작성
  - `결과 매핑 노드`: LLM 응답을 JSON으로 파싱하여 API 응답 규격에 매핑
- **엣지 연결:** `START → (긴급도 분류 · 패턴 분류) → LLM 분석 → 결과 매핑 → END` 형태로 명시적 연결 (두 Tool 노드는 병렬 fan-out 후 LLM 분석 노드에서 합류)
- **시스템 프롬프트 설계:** 이상 로그의 근거 설명, 요약, 대응 방안을 작성하도록 지시하고 출력 형식을 지정

## 5단계: FastAPI 라우터 및 API 엔드포인트 구현
완성된 Agent 서비스를 실제 웹 요청과 연결합니다.
- **라우터 연결 (`routers/analyze.py`):**
  - `POST /ai/v1/analyze`: 단건 분석 요청 수신 -> `agent_service` 단건 분석 호출 -> 결과 반환
  - `POST /ai/v1/analyze/batch`: 다건 분석 요청 수신 -> 비동기 병렬 처리(`asyncio.gather` 등 활용) -> 전체 결과 취합 및 반환
- **에러 핸들링 보완:** AI 응답 지연, DB 연결 실패, 파싱 오류 등 예외 처리 추가

## 6단계: 테스트 및 고도화
- **단위 및 통합 테스트:** 정상 흐름과 예외 상황에 대한 API 테스트
- **모의(Mock) 통신 테스트:** Spring Boot에서 넘어오는 것과 동일한 구조의 더미 데이터를 사용해 게이트웨이 테스트
- **최적화:** 대량의 배치 로그 분석 시 동시성 제어(Rate Limit 방지 등) 및 프롬프트 튜닝
