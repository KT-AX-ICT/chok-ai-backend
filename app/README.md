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
| 분석 기준 품질 | 고유경, 윤혜림 | 박가희 | 이상 로그 근거 설명 기준을 검토한다. |

## Scope

- FastAPI 애플리케이션 진입점
- Spring Boot가 호출하는 AI 분석 API의 서버 골격
- 공통 설정, CORS, 미들웨어, 예외 처리 연결
- 근거 설명 Agent를 호출할 기반 구조

## Responsibilities

- FastAPI는 AI 분석/근거 생성 결과를 생성한다. 반복 패턴(클러스터)은 Tool③가 FastAPI 로컬 패턴 seed로 매칭해 cluster_id를 부착한다.
- 분석 결과 저장, 조회, 스케줄링, 정확도 산출은 Spring Boot 책임으로 둔다.
- 정상/이상 여부는 FastAPI 분석 파이프라인(Tool②)이 직접 판정한다. 정답 라벨은 분석 요청에 포함하지 않는다.
- 이상 판정 로그에는 근거 설명을, 정상 판정 로그에는 정상 사유를 생성한다.
- Spring-FastAPI 요청/응답 계약 변경 시 `schemas` 문서와 실제 DTO 구현을 함께 정리한다.

## Out Of Scope

- Spring Boot DB 직접 접근
- 분석 결과 영속화
- BGL seed data 초기 적재
- 인증/인가
- 실제 운영 시스템 제어 또는 자동 복구
- 진짜 실시간 스트리밍 감시
