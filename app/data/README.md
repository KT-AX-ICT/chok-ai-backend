# Data Module

## Package Owner

- 최종 구조/리뷰 책임: 이예지

## Scope Ownership

| Scope | Primary | Support | Notes |
| --- | --- | --- | --- |
| BGL 로그 구조 확인 | 이예지 | 윤혜림, 고유경 | 첫 번째 컬럼 라벨 기준은 정확도 검증 경로에 반영한다. 분석 요청 입력 DTO에는 label을 포함하지 않는다. |
| 분석 입력 구조 정리 | 이예지 | 박가희 | Spring에서 전달할 로그 필드와 Agent 입력 필드가 맞도록 한다. |
| 패턴 seed 처리 | 고유경, 윤혜림 | 이예지 | Tool③ 매칭용 패턴 seed 파일(FastAPI 로컬)을 적재·로드한다. 현재 파일 미수령. |

## Scope

- BGL 로그 구조 확인용 유틸
- FastAPI 분석 입력 구조 검토
- Tool③ 매칭용 패턴 seed 파일 적재·로드 (FastAPI 로컬, 수령 후)
- Spring seed data 구조와 FastAPI 입력 구조 사이의 정합성 확인

## Responsibilities

- BGL 첫 번째 라벨 컬럼 기준을 보존한다.
- `-`는 정상, 그 외 값은 이상이라는 기준을 흔들지 않는다.
- FastAPI 내부 검증/분석 입력을 위한 구조화만 담당한다.
- Spring Boot의 seed data 적재 책임과 겹치지 않게 한다.

## Out Of Scope

- Spring DB seed data 저장
- `LogSeedService` 구현
- FastAPI endpoint 구현
- Agent 분석 로직
- 실제 운영 시스템 실시간 감시
