# Core Module

## Package Owner

- 최종 구조/리뷰 책임: 박가희

## Scope Ownership

| Scope | Primary | Support | Notes |
| --- | --- | --- | --- |
| 공통 설정 | 박가희 | 박연지 | 앱 이름, 버전, CORS 등 비밀이 아닌 서버 설정을 관리한다. |
| CORS 정책 | 박가희 | 박연지 | Spring Boot의 CORS 설정과 개발 환경 origin을 맞춘다. |
| 공통 예외 처리 | 박가희 | 박연지 | Spring 연동 시 일정한 오류 응답 형식을 유지한다. |
| 서버 공통 정책 | 박가희 | 박연지 | 미들웨어, 로깅 등 전체 앱에 적용되는 정책을 관리한다. |

## Scope

- FastAPI 앱 공통 설정
- CORS origin, method, header 정책
- 공통 예외 응답
- 전역 서버 정책

## Responsibilities

- secret 값이 필요한 설정은 읽거나 출력하지 않는다.
- 개발 origin은 Spring Boot CORS 정책과 일관되게 관리한다.
- 내부 예외 메시지를 응답으로 그대로 노출하지 않는다.
- 기능별 분석 로직을 core에 넣지 않는다.

## Out Of Scope

- Agent 프롬프트 관리
- 분석 endpoint 구현
- Spring DB 저장
- BGL 파싱
- 인증/인가 구현
