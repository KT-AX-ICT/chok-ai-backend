# API Module

## Package Owner

- 최종 구조/리뷰 책임: 박가희

## Scope Ownership

| Scope | Primary | Support | Notes |
| --- | --- | --- | --- |
| FastAPI endpoint 구현 | 박가희 | 박연지 | Spring Scheduler/WebClient가 호출할 HTTP 경계를 구현한다. |
| API 명세 정합성 | 박가희 | 박연지, 이석진, 이예지 | 기존에 작성된 API 명세를 기준으로 구현한다. |
| 분석 endpoint 흐름 | 박가희 | 고유경, 이예지 | 로그 입력을 받아 status·근거 설명·cluster_id를 반환하는 흐름을 구성한다. |

## Scope

- FastAPI 라우터와 endpoint 정의
- 요청 DTO 검증 후 서비스 계층 호출
- Spring Boot에 반환할 HTTP 응답 구성
- 기존 API 명세와 실제 구현의 정합성 유지

## Responsibilities

- endpoint 경로, method, 요청/응답 필드는 기존 API 명세를 확인한 뒤 구현한다.
- 라우터는 HTTP 경계만 담당하고 분석 로직은 `services` 또는 `agents`로 위임한다.
- Spring Boot가 처리해야 하는 저장, 조회, 스케줄링 책임을 endpoint 내부에 넣지 않는다.
- API 응답은 Spring의 `integration.fastapi` DTO와 맞도록 관리한다.
- 분석 요청 DTO에는 정답 label을 포함하지 않는다(판정 누수 방지). 정확도 검증(Precision/Recall/F1)은 Spring이 담당하며 FastAPI endpoint로 두지 않는다.

## Out Of Scope

- API 명세 원본 관리
- AI/Agent 내부 분석 로직
- Spring DB 저장
- BGL seed data 적재
- 인증/인가
