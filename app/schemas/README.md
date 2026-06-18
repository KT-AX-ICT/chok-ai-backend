# Schemas Module

## Package Owner

- 최종 구조/리뷰 책임: 박가희

## Scope Ownership

| Scope | Primary | Support | Notes |
| --- | --- | --- | --- |
| Spring-FastAPI DTO 계약 | 박가희 | 박연지, 이석진, 이예지 | 기존 API 명세와 Spring `integration.fastapi` DTO를 기준으로 맞춘다. |
| 로그 입력 스키마 | 이예지 | 박가희 | BGL 파서/seed data 구조와 분석 입력 필드를 맞춘다. |
| 분석 결과 스키마 | 박가희 | 고유경, 이석진 | 근거 설명, 위험도, reason 필드를 포함한다. |
| 반복 패턴 스키마 | 박가희 | 윤혜림, 이석진 | 패턴 그룹, 대표 메시지, 발생 빈도 표현을 맞춘다. |

## Scope

- Pydantic 요청/응답 DTO
- Spring-FastAPI 계약 필드 관리
- 분석 결과와 반복 패턴 결과의 응답 구조
- API 문서화에 노출될 schema description/example

## Responsibilities

- DTO는 FastAPI 내부 구현 모델과 분리해 외부 계약 변경 영향을 줄인다.
- 정상/이상 여부는 BGL 라벨 기반 결과를 표현하고 AI 재판정 결과처럼 표현하지 않는다.
- 이상 로그 분석 응답에는 사람이 읽을 수 있는 reason을 포함한다.
- 기존 API 명세와 다르게 구현해야 할 경우 먼저 합의한다.

## Out Of Scope

- endpoint 라우팅
- Agent 내부 로직
- Spring DB 저장 모델
- BGL seed data 적재
- 인증/인가 DTO
