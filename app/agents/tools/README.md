# Agent Tools

Agent가 사용하는 결정적(rule/검색 기반) Tool 구현을 둡니다. 각 Tool은 프레임워크(LangGraph 등)에
종속되지 않는 순수 함수 + Pydantic 결과 모델로 작성하고, 오케스트레이션 계층(`app/services`)이 노드로 감쌉니다.

## 담당 Tool

| Tool | 파일(예정) | 입력 | 출력 |
| --- | --- | --- | --- |
| ① 이벤트 템플릿 분류 (drain) | `event_template.py` | 로그 `content` | `eventId`, `template` |
| ③ 클러스터 분류 | `cluster.py` | `eventId`, `template` | `clusterId` (int) |

## 구조

- `event_template.py`, `cluster.py` — Tool 순수 함수
- `metadata/` — 판정에 사용하는 메타데이터 파일 (별도 README 참고)
