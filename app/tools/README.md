# Agents Module

## Package Owner

- 최종 구조/리뷰 책임: 박가희

## Scope Ownership

| Scope | Primary | Support | Notes |
| --- | --- | --- | --- |
| 이상 로그 근거 설명 기준 | 고유경 | 윤혜림, 박가희 | 이상 판정 로그에 대해 사람이 읽을 수 있는 근거 기준을 정한다. |
| 근거 설명 Agent 구현 | 박가희 | 이예지, 고유경 | FastAPI 분석 endpoint에서 호출할 설명 생성 로직을 만든다. |
| 패턴 매칭 기준 | 윤혜림 | 이예지, 박가희 | Tool③가 패턴 seed로 cluster_id를 매칭하는 기준을 정한다. |
| Tool③ 패턴 매칭 연동 | 박가희 | 윤혜림, 이예지 | 데이터팀 패턴 seed(FastAPI 로컬)를 받아 cluster_id 매칭을 연결한다. |

## Scope

- 이상 판정 로그 근거 설명 / 정상 판정 로그 정상 사유 생성
- Tool③ 패턴 매칭(cluster_id) 연동 — FastAPI 로컬 패턴 seed 기반
- Spring으로 반환할 분석 결과의 설명 필드 생성
- LLM 사용 시 프롬프트와 출력 형식 관리

## Responsibilities

- 정상/이상 여부는 분석 파이프라인(Tool②)이 판정하며, Agent는 그 판정을 뒤집지 않는다.
- 정답 라벨은 분석 입력으로 쓰지 않고, 정확도 검증 경로에서만 사용한다.
- 모든 이상 로그 분석 결과에는 사람이 읽을 수 있는 reason을 포함한다.
- 패턴(클러스터)은 Tool③가 FastAPI 로컬 패턴 seed로 매칭하며, 패턴 생성/저장은 범위 외(Spring 저장)다.
- LLM 호출 실패 시 서비스 계층에서 다룰 수 있는 명확한 오류를 반환한다.

## Out Of Scope

- Spring DB 직접 접근
- 분석 결과 저장
- BGL seed data 적재
- FastAPI 라우터 정의
- 인증/인가
- 실제 운영 시스템 제어 또는 자동 복구
