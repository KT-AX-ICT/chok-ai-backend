# Services Module

## Package Owner

- 최종 구조/리뷰 책임: 박가희

## Scope Ownership

| Scope | Primary | Support | Notes |
| --- | --- | --- | --- |
| 분석 요청 처리 흐름 | 박가희 | 이예지, 고유경 | 라우터 입력을 검증하고 근거 설명 Agent 호출 결과를 조립한다. |
| 정상/이상 판정 흐름 | 이예지 | 박가희 | Tool② 정상/이상 판정 결과(status)와 분기를 서비스 흐름에서 보존한다. 정답 라벨은 분석 입력에 쓰지 않는다. |
| 패턴 매칭 흐름 | 박가희 | 윤혜림, 이예지 | analyze 흐름에서 Tool③ 매칭 결과(cluster_id)를 응답에 반영한다. |
| 정확도 산출 연계 | 고유경, 윤혜림 | 박가희 | 정확도 산출은 Spring 담당. FastAPI는 분석 status만 제공한다. |

## Scope

- 라우터와 Agent 사이의 application/service 계층
- 요청 검증 이후 분석 대상 선별
- Agent 호출 결과 조립
- Spring에 반환할 응답 형태 구성

## Responsibilities

- 라우터에 분석 로직이 쌓이지 않도록 서비스 계층에서 흐름을 조합한다.
- 정상/이상 판정은 Tool②가 수행하고, 서비스는 그 결과(status)와 정상/이상 분기를 보존한다.
- 분석 결과 저장은 수행하지 않고 Spring Boot가 저장할 수 있는 응답만 반환한다.
- Agent 실패, 입력 오류, 빈 분석 대상 같은 상황을 명확히 다룬다.

## Out Of Scope

- HTTP 라우터 정의
- LLM 프롬프트 세부 구현
- Spring DB 직접 접근
- BGL seed data 적재
- 화면 데이터 조회
