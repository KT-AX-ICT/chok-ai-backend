# Chok AI Backend

로그 분석 자동화 시스템의 FastAPI/Python AI 분석 백엔드 프로젝트입니다.

FastAPI는 Spring Boot에서 전달받은 로그 데이터를 기준으로 이상 로그 근거 설명, 반복 패턴 분석, 라벨 기반 검증 산출을 담당합니다. BGL 로그 seed data 적재, 분석 결과 저장 및 조회, Scheduler 실행, 대시보드 API는 Spring Boot 영역입니다.

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

- Spring Boot에서 전달받은 로그 분석 요청 처리
- BGL 첫 번째 라벨 컬럼 기준 정상/이상 분류 결과 수신
- 라벨상 이상 로그에 대한 근거 설명 생성
- 누적 이상 로그의 반복 패턴 분석
- BGL 라벨 기준 정확도 검증 산출
- Spring-FastAPI 요청/응답 DTO 계약 유지

정상/이상 분류는 AI가 새로 판단하지 않습니다. BGL 로그 첫 번째 컬럼의 라벨을 기준으로 분류하고, AI는 라벨상 이상 로그에 대한 근거 설명을 생성합니다.

## 패키지 책임

| Package | 책임 |
| --- | --- |
| `app` | FastAPI 애플리케이션 진입점과 전체 서버 골격 |
| `app.api` | Spring Boot에서 호출할 HTTP endpoint 경계 |
| `app.schemas` | Spring-FastAPI 요청/응답 DTO 계약 |
| `app.services` | 라우터와 Agent 사이의 분석 흐름 조합 |
| `app.agents` | 이상 로그 근거 설명과 반복 패턴 분석 로직 |
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
- FastAPI는 정상/이상 여부를 새로 판단하지 않고 BGL 라벨 기반 분류 결과를 사용합니다.
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
- 전역 예외 처리
- pydantic-settings 기반 공통 설정
- 패키지별 담당/책임 README

아직 미구현:

- 분석 endpoint
- 반복 패턴 endpoint
- 검증 endpoint
- Spring-FastAPI 요청/응답 DTO
- 이상 로그 근거 설명 Agent
- 반복 패턴 분석 Agent
- 실제 LLM 연동
- 테스트 코드
