# Chok AI Backend

로그 분석 자동화 시스템의 FastAPI/Python AI 분석 백엔드 프로젝트입니다.

FastAPI는 Spring Boot에서 전달받은 로그를 기준으로 정상/이상 판정과 이상 로그 근거 설명(정상 사유 포함)을 담당합니다. 반복 패턴(클러스터)은 분류 Tool이 처리하며, 라벨 기반 정확도 검증 산출, BGL seed data 적재, 분석 결과 저장·조회, Scheduler 실행, 대시보드/어드민 API는 Spring Boot 영역입니다.

## 기술 스택

- Python 3.12
- FastAPI
- Uvicorn
- Pydantic v2
- pydantic-settings
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
- Spring-FastAPI 요청/응답 DTO (camelCase 계약, 정상/이상 status 포함)
- 이상 로그 근거 설명 / 정상 사유 Agent
- OpenAI(LLM) 연동 및 구조화 출력
- 분석 흐름 테스트 (analyze·batch·에러 매핑)

아직 미구현:

- Tool ①~④ 실제 연동 (현재 stub, 데이터 분석팀 구현 예정)
