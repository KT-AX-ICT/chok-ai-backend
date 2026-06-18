# Services Module

## Package Owner

- 최종 구조/리뷰 책임: 박가희

## Scope Ownership

| Scope | Primary | Support | Notes |
| --- | --- | --- | --- |
| 분석 요청 처리 흐름 | 박가희 | 이예지, 고유경 | 라우터 입력을 검증하고 근거 설명 Agent 호출 결과를 조립한다. |
| 라벨 기준 필터링 | 이예지 | 박가희 | BGL 라벨 기준을 서비스 흐름에서 보존한다. |
| 반복 패턴 처리 흐름 | 박가희 | 윤혜림, 이예지 | 반복 패턴 Agent 호출 결과를 응답 계약에 맞춘다. |
| 검증 결과 산출 흐름 | 고유경, 윤혜림 | 박가희 | 발표/보고서용 검증 결과 산출 흐름을 구성한다. |

## Scope

- 라우터와 Agent 사이의 application/service 계층
- 요청 검증 이후 분석 대상 선별
- Agent 호출 결과 조립
- Spring에 반환할 응답 형태 구성

## Responsibilities

- 라우터에 분석 로직이 쌓이지 않도록 서비스 계층에서 흐름을 조합한다.
- AI가 정상/이상 여부를 새로 판단하지 않도록 라벨 기준을 유지한다.
- 분석 결과 저장은 수행하지 않고 Spring Boot가 저장할 수 있는 응답만 반환한다.
- Agent 실패, 입력 오류, 빈 분석 대상 같은 상황을 명확히 다룬다.

## Out Of Scope

- HTTP 라우터 정의
- LLM 프롬프트 세부 구현
- Spring DB 직접 접근
- BGL seed data 적재
- 화면 데이터 조회
