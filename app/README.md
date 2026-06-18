# AI Backend Application

## Package Owner

- 최종 구조/리뷰 책임: 박가희

## Scope Ownership

| Scope | Primary | Support | Notes |
| --- | --- | --- | --- |
| FastAPI 서버 구조 | 박가희 | 박연지 | Spring Boot에서 호출할 AI 분석 서버의 기본 구조를 관리한다. |
| Spring-FastAPI 책임 경계 | 박가희 | 박연지, 이석진, 이예지 | FastAPI는 분석 결과를 생성하고, 저장/조회는 Spring Boot 책임으로 둔다. |
| 공통 서버 정책 | 박가희 | 박연지 | CORS, 예외 처리, 공통 미들웨어 기준을 관리한다. |
| 분석 입력 구조 정합성 | 이예지 | 박가희 | BGL 파서/seed data 구조와 FastAPI 입력 구조가 어긋나지 않게 한다. |
| 분석 기준 품질 | 고유경, 윤혜림 | 박가희 | 이상 로그 근거와 반복 패턴 표현 기준을 검토한다. |

## Scope

- FastAPI 애플리케이션 진입점
- Spring Boot가 호출하는 AI 분석 API의 서버 골격
- 공통 설정, CORS, 미들웨어, 예외 처리 연결
- 근거 설명 Agent와 반복 패턴 분석 Agent를 호출할 기반 구조

## Responsibilities

- FastAPI는 AI 분석/근거 생성/반복 패턴 분석 결과를 생성한다.
- 분석 결과 저장, 조회, 스케줄링은 Spring Boot 책임으로 둔다.
- 정상/이상 여부를 AI가 새로 판단하지 않고 BGL 첫 번째 라벨 컬럼 기준을 따른다.
- 라벨상 이상 로그에 대해서만 사람이 읽을 수 있는 근거 설명을 생성한다.
- Spring-FastAPI 요청/응답 계약 변경 시 `schemas` 문서와 실제 DTO 구현을 함께 정리한다.

## Out Of Scope

- Spring Boot DB 직접 접근
- 분석 결과 영속화
- BGL seed data 초기 적재
- 인증/인가
- 실제 운영 시스템 제어 또는 자동 복구
- 진짜 실시간 스트리밍 감시
