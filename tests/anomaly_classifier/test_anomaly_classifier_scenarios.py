"""이상 여부 + 긴급도 분류 Tool — 시나리오 검증 + 팀 공유용 리포트 생성.

각 시나리오마다 입력 event_id → is_anomaly 판정 근거 → urgency → 출력값을
추적해 보여준다. 정상/비정상/미분류 전 경로를 커버한다.

실행:
    uv run pytest tests/anomaly_classifier/test_anomaly_classifier_scenarios.py -s

부수 효과: tests/anomaly_classifier/SCENARIO_REPORT.md 를 생성(덮어쓰기)한다.
"""

import datetime as _dt
from pathlib import Path

from app.agents.tools.anomaly_classifier import AnomalyClassifier, classify_anomaly

REPORT_PATH = Path(__file__).parent / "SCENARIO_REPORT.md"

# 시나리오 정의: (id, 제목, event_id, 기대 is_anomaly, 기대 urgency, 설명) ----
SCENARIOS = [
    ("S1", "정상 — ECC 자동 정정",
     "E7", False, None,
     "하드웨어가 자동 정정 완료. 단발성 발생은 정상 범위."),
    ("S2", "정상 — 레지스터 덤프",
     "E43", False, None,
     "장애 발생 시 자동 출력되는 CPU 설정 레지스터 덤프. 오류 자체가 아닌 컨텍스트 정보."),
    ("S3", "정상 — 명령어 캐시 패리티 자동 정정",
     "E77", False, None,
     "캐시 패리티 오류 자동 정정됨. 반복 발생 시에만 주의."),
    ("S4", "정상 — job 수준 실패 (ciod 파일 없음)",
     "E28", False, None,
     "사용자 프로그램 경로 오류로 해당 작업만 종료. 시스템은 계속 운영 가능. "
     "FATAL 레벨이지만 시스템 장애가 아닌 job 수준 실패."),
    ("S5", "비정상 Critical — 데이터 스토리지 인터럽트",
     "E52", True, "Critical",
     "메모리 읽기/쓰기 중 오류. 데이터 무결성 직접 위협."),
    ("S6", "비정상 Critical — 커널 비정상 종료",
     "E111", True, "Critical",
     "커널 강제 중단. 실행 중 작업 전체 상태 소실."),
    ("S7", "비정상 High — DDR 메모리 오류",
     "E1", True, "High",
     "DDR 메모리 오류. 데이터 무결성 영향 가능."),
    ("S8", "비정상 High — 토러스 네트워크 오류",
     "E8", True, "High",
     "토러스 인터커넥트 오류. 노드 간 통신 이상."),
    ("S9", "비정상 Mid — ciod 시스템 자원 고갈",
     "E19", True, "Mid",
     "파일 디스크립터 부족으로 ciod 실패. 시스템 자원 고갈 — "
     "job 수준 실패(S4)와 달리 다른 작업에도 영향 가능."),
    ("S10", "비정상 Low — L3 EDRAM 정정 가능 오류",
     "E5", True, "Low",
     "L3 캐시 ECC 정정됨. 반복 시 메모리 열화 징후."),
    ("S11", "미분류 — 템플릿 매칭 실패",
     "unknown", True, "Mid",
     "event_template.py 매칭 실패. 에러로 처리 후 클러스터링 tool로 전달."),
]


def _run(event_id: str):
    return classify_anomaly(event_id)


def _route(is_anomaly: bool, category: str | None) -> str:
    if not is_anomaly:
        return "정상 근거 산출 LLM"
    if category == "UNKNOWN":
        return "클러스터링 tool (미분류)"
    return "클러스터링 tool"


def test_scenarios_and_generate_report() -> None:
    header: list[str] = []
    detail: list[str] = ["\n## 상세 트레이스\n"]
    summary: list[str] = []
    failures: list[str] = []

    header.append("# 이상 여부 + 긴급도 분류 Tool — 시나리오 검증 리포트\n")
    header.append(
        f"- 생성: {_dt.date.today().isoformat()}\n"
        "- 대상 함수: `classify_anomaly(event_id)`\n"
        "- 판정 기준: `is_anomaly` → 클러스터링 tool / 정상 근거 산출 LLM 라우팅\n"
    )

    print("\n" + "=" * 78)
    for sid, title, event_id, expected_anomaly, expected_urgency, note in SCENARIOS:
        result = _run(event_id)

        urgency_val = result.urgency.value if result.urgency else None
        ok = (result.is_anomaly == expected_anomaly) and (urgency_val == expected_urgency)
        mark = "✅ PASS" if ok else "❌ FAIL"
        if not ok:
            failures.append(
                f"{sid}: 기대 is_anomaly={expected_anomaly}/urgency={expected_urgency} "
                f"!= 실제 is_anomaly={result.is_anomaly}/urgency={urgency_val}"
            )

        route = _route(result.is_anomaly, result.category)

        # --- 콘솔 트레이스 ---
        print(f"[{sid}] {title}")
        print(f"  event_id  : {event_id}")
        print(f"  is_anomaly: {result.is_anomaly}  urgency: {urgency_val}")
        print(f"  category  : {result.category}")
        print(f"  라우팅    : {route}")
        print(f"  impact    : {result.impact}")
        print(f"  action    : {result.action}")
        print(f"  기대      : is_anomaly={expected_anomaly}, urgency={expected_urgency}  →  {mark}")
        print("-" * 78)

        # --- 리포트 누적 ---
        summary.append(
            f"| {sid} | {title} | `{event_id}` | {expected_anomaly} / {expected_urgency} "
            f"| {result.is_anomaly} / {urgency_val} | {mark} |"
        )
        detail.append(f"### {sid}. {title}\n")
        detail.append(f"- 설명: {note}")
        detail.append(f"- event_id: `{event_id}`")
        detail.append(f"- is_anomaly: `{result.is_anomaly}` / urgency: `{urgency_val}`")
        detail.append(f"- category: `{result.category}`")
        detail.append(f"- 라우팅: **{route}**")
        detail.append(f"- impact: `{result.impact}`")
        detail.append(f"- action: `{result.action}`")
        detail.append(f"- 기대: is_anomaly=`{expected_anomaly}`, urgency=`{expected_urgency}` → **{mark}**\n")

    table = [
        "\n## 요약\n",
        "| # | 시나리오 | event_id | 기대(anomaly/urgency) | 실제(anomaly/urgency) | 결과 |",
        "|---|---|---|---|---|---|",
        *summary, "",
    ]
    report = "\n".join(header + table + detail) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"리포트 생성: {REPORT_PATH}")
    print("=" * 78)

    assert not failures, "시나리오 실패:\n" + "\n".join(failures)
