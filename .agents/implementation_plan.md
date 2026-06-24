구현 계획 — feat/langgraph API 완성

Phase 0. 환경 복구 (선행 필수 — 지금은 import조차 안 됨)

의존성·락 문제부터 풀어야 어떤 코드도 돌릴 수 있습니다.
- pyproject.toml에 langgraph, tzdata 추가 (둘 다 미선언)
- uv.lock 재생성 — docstring-parser source 누락으로 파싱 깨짐
- dev의 httpx2(오타 의심) → TestClient용 httpx 확인
- .venv/Scripts/python.exe -c "import app.main" + 기존 tests/test_analyze.py green 확인
- 완료 기준: app import 성공, 기존 회귀 테스트 통과

Phase 1. 빠른 정합성 수정 (저비용, 확정 설계 반영)

- 배치 한도 500 → 400: schemas/analysis.py(max_length=400) + tests/test_analyze.py(501/600 → 401/500) + 라우터 docstring("최대 500건")
- main.py 죽은/중복 핸들러 제거(미import Request/JSONResponse 참조 global_exception_handler)
- step4_agent.md 4-5 LLM provider를 OpenAI로 정정(현재 "ChatAnthropic 권장"이나 코드·Tier1 한도 모두 OpenAI)

Phase 2. Tool ①②③④ 실연동 (스텁 제거)

app/agents/tools/*.py의 실제 구현을 analysis_service.py의 4개 스텁과 교체.
- ① extract_event_template → event_id
- ② classify_anomaly → is_anomaly/urgency(영문)/impact/action ⇒ 내부 status(정상/이상)·risk_level(한글) 변환, 정상이면 risk_level=None
- ③ assign_cluster → cluster_id(미분류 99 그대로)
- ④ get_node_info → 노드 컨텍스트 문자열
- 동기 순수함수이므로 async 노드 내 호출 방식 결정(직접 호출/to_thread)
- 완료 기준: 하드코딩 "E00"/항상-이상 제거, 실제 메타데이터 기반 판정

Phase 3. LangGraph StateGraph 전환 (핵심)

- langgraph.StateGraph + TypedDict State (step4_agent.md 4-1 필드)
- 노드 add_node: template/anomaly/cluster/node_info/llm/map
- add_conditional_edges("anomaly", route_by_anomaly): 정상→llm, 이상→["cluster","node_info"] fan-out → llm fan-in
- graph.compile() 모듈 레벨 1회
- analyze_single_log을 graph.ainvoke로 교체, 결과 매핑 노드가 AnalyzeResult로 변환(impact/action은 LLM 입력 컨텍스트, 최종 analysis/action은 LLM 생성)
- 완료 기준: 정상=③④ 미실행 / 이상=③④ 실행이 그래프 구조로 강제

Phase 4. 배치 회복탄력성 (확정 설계 반영)

- analyze_batch_logs에 asyncio.Semaphore(8) 동시성 캡
- ChatOpenAI(max_retries=6) 지수 백오프
- 타임아웃 2단: 전체 5분, 개별 LLM 호출 30~60s
- config.py에 동시성·타임아웃·재시도 설정 추가(CHOK_AI_ prefix)
- 완료 기준: 400건 배치가 동시 8건으로 처리, 429 시 백오프 재시도

Phase 5. 테스트·검증

- 분기 테스트(정상/이상별 ③④ 실행 여부)
- Tool 실연동 통합 테스트(메타데이터 기반)
- 배치 동시성 상한 테스트
- 전체 스위트 green

---
의존 순서: Phase 0 → 1 → 2 → 3 → 4 → 5 (0이 막히면 전부 막힘). Phase 1·2는 독립적이라 병행 가능, Phase 3는 2 위에서 진행.

리스크: ① uv.lock 재생성이 다른 의존성 충돌을 부를 수 있음(Phase 0에서 조기 확인) ② Tool 동기함수를 async 그래프에 넣을 때 이벤트 루프 블로킹(asyncio.to_thread
권장) ③ Phase 3에서 기존 tests/test_analyze.py의 monkeypatch 대상 경로(SVC.run_diagnosis 등)가 그래프 구조로 바뀌며 깨질 수 있어 테스트도 같이 손봐야 함. 