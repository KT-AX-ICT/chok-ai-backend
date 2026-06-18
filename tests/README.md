# Tests

## Package Owner

- 최종 구조/리뷰 책임: 박가희

## Scope Ownership

| Scope | Primary | Support | Notes |
| --- | --- | --- | --- |
| FastAPI smoke test | 박가희 | 박연지 | 서버 기본 기동과 health check를 검증한다. |
| DTO contract test | 박가희 | 이석진, 이예지 | Spring-FastAPI 요청/응답 DTO 계약을 검증한다. |
| 분석 흐름 test | 박가희 | 고유경, 윤혜림 | 라벨 기준과 reason 포함 여부를 검증한다. |
| 반복 패턴 test | 박가희 | 윤혜림 | 패턴 응답 구조와 필수 필드를 검증한다. |

## Scope

- FastAPI 기본 동작 검증
- Spring-FastAPI DTO 계약 검증
- 라벨 기반 분석 흐름 검증
- 반복 패턴 응답 구조 검증

## Responsibilities

- OpenAI API key 같은 secret 없이 통과 가능한 테스트를 우선 작성한다.
- AI 호출 자체보다 라벨 기준, 응답 필드, 오류 흐름을 검증한다.
- 분석 결과에 reason이 포함되는지 확인한다.
- BGL 라벨 기준을 재현 가능한 방식으로 검증한다.

## Out Of Scope

- 실제 LLM 품질 평가
- Spring Boot 통합 테스트
- DB 저장 검증
- 외부 네트워크 의존 테스트
