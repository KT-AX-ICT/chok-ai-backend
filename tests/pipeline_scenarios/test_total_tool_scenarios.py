"""Tool①→②→③→④ 전체 파이프라인 시나리오 검증

각 시나리오마다 Content + Node → 4단계 파이프라인을 추적해 보여준다.
파이프라인은 FATAL 레벨 event_id 한정으로 진입한다.

  Tool①  extract_event_template(Content)  → event_id (FATAL 레벨 로그 대상)
  Tool②  classify_anomaly(event_id)       → is_anomaly, urgency
         is_anomaly=False → LLM 라우팅 (FastAPI 담당)
         is_anomaly=True  → Tool③ 진행
  Tool③  assign_cluster(event_id)         → cluster_id  (이상 건만)
  Tool④  get_node_info(node_id)           → node_metadata + alert_stats (전건)

실행:
    uv run pytest tests/pipeline_scenarios/test_total_tool_scenarios.py -s
"""

import datetime as _dt
from pathlib import Path

from app.agents.tools.anomaly_classifier import classify_anomaly
from app.agents.tools.cluster import assign_cluster
from app.agents.tools.event_template import extract_event_template
from app.agents.tools.node_info import get_node_info

REPORT_PATH = Path(__file__).parent / "SCENARIO_REPORT.md"

# ── 시나리오 정의 ─────────────────────────────────────────────────────────────
# (id, 제목, content, node_id,
#  기대 event_id, 기대 is_anomaly, 기대 urgency, 기대 cluster_id|None,
#  기대 rack|None, 기대 alert_pct|None,
#  설명)
SCENARIOS = [
    (
        "S1", "정상 — 명령어 캐시 패리티 자동 정정",
        "instruction cache parity error corrected",
        "R30-M0-N9-C:J16-U01",
        "E77", False, "None", None,
        "R30", 41.96,
        "E77(정상) → LLM 라우팅. 최고위험 노드(41.96%)에서 발생.",
    ),
    (
        "S2", "정상 — job 수준 실패 (ciod 파일 없음)",
        "ciod: Error loading /foo: invalid or missing program image, No such file or directory",
        "R04-M1-N4-I:J18-U11",
        "E28", False, "None", None,
        "R04", 0.7,
        "E28(정상) → LLM 라우팅. 시스템 장애 아닌 job 수준 실패. I/O 노드.",
    ),
    (
        "S3", "비정상 Critical — 데이터 스토리지 인터럽트",
        "data storage interrupt",
        "R30-M0-N9-C:J16-U01",
        "E52", True, "Critical", 0,
        "R30", 41.96,
        "E52 → cluster 0 배정. 최고위험 노드(41.96%) 연계.",
    ),
    (
        "S4", "비정상 Critical — 커널 비정상 종료",
        "rts: kernel terminated for reason 1001",
        "R16-M0-NB-C:J07-U11",
        "E111", True, "Critical", 3,
        "R16", 0.7,
        "E111 → cluster 3 배정. hex 노드카드 NB→N11 변환 확인.",
    ),
    (
        "S5", "비정상 High — DDR 메모리 오류",
        "12 ddr error(s) detected and corrected on rank 0, symbol 4 over 1234 seconds",
        "R10-M1-N5-C:J15-U11",
        "E1", True, "High", 99,
        "R10", 0.7,
        "E1 → 미분류(cluster 99) 배정.",
    ),
    (
        "S6", "비정상 Mid — ciod 미인식 메시지",
        "ciod: cpu 0 at treeaddr 1 sent unrecognized message 0x0",
        "R13-M1-N2-C:J17-U01",
        "E19", True, "Mid", 99,
        "R13", 0.7,
        "E19 → 미분류(cluster 99) 배정.",
    ),
    (
        "S7", "비정상 Low — L3 EDRAM 정정 가능 오류",
        "5 L3 EDRAM error(s) (dcr 0x0) detected and corrected",
        "R15-M0-N9-C:J05-U11",
        "E5", True, "Low", 99,
        "R15", 0.7,
        "E5 → 미분류(cluster 99) 배정.",
    ),
    (
        "S8", "미분류 — 템플릿 매칭 실패 → unknown",
        "this is not a real bgl log at all",
        "R01-M1-NA-C:J13-U01",
        "unknown", True, "Mid", 99,
        "R01", 0.7,
        "매칭 실패 → unknown → is_anomaly=True/Mid/cluster 99.",
    ),
    (
        "S9", "NULL 노드 — 파싱 불가, 이상 경로",
        "data storage interrupt",
        "NULL",
        "E52", True, "Critical", 0,
        None, None,
        "노드 위치 미식별(NULL) → Tool④ 전 필드 None. 파이프라인 나머지는 정상 진행.",
    ),
    (
        "S10", "소문자 노드 — 자동 정규화 후 정상 조회",
        "instruction cache parity error corrected",
        "r30-m0-n9-c:j16-u01",
        "E77", False, "None", None,
        "R30", 41.96,
        "소문자 node_id → .upper() 정규화 → S1과 동일 결과.",
    ),
]


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _run(content: str, node_id: str):
    t1 = extract_event_template(content)
    t2 = classify_anomaly(t1.event_id)
    t3 = assign_cluster(t1.event_id) if t2.is_anomaly else None
    t4 = get_node_info(node_id)
    return t1, t2, t3, t4


def _routing(is_anomaly: bool) -> str:
    return "Tool③ (클러스터 배정)" if is_anomaly else "LLM 라우팅 (FastAPI)"


def _node_summary(t4) -> str:
    m = t4.node_metadata
    parts = []
    if m.rack:      parts.append(f"rack={m.rack}")
    if m.node_slot: parts.append(f"slot={m.node_slot}")
    if m.node_role: parts.append(f"role={m.node_role}")
    pct = t4.alert_stats.alert_pct if t4.alert_stats else None
    parts.append(f"alert_pct={pct}%")
    return ", ".join(parts) if parts else "파싱 실패 → 전 필드 None"


# ── 메인 테스트 ───────────────────────────────────────────────────────────────

def test_total_tool_scenarios_and_generate_report() -> None:
    header:  list[str] = []
    detail:  list[str] = ["\n## 상세 트레이스\n"]
    summary: list[str] = []
    failures: list[str] = []

    header.append("# Tool①→②→③→④ 전체 파이프라인 시나리오 검증 리포트\n")
    header.append(
        f"- 생성: {_dt.date.today().isoformat()}\n"
        "- 진입 조건: FATAL 레벨 event_id 한정\n"
        "- 파이프라인: `extract_event_template` → `classify_anomaly` → `assign_cluster` → `get_node_info`\n"
        "- 라우팅 기준: `is_anomaly=False` → LLM  /  `is_anomaly=True` → Tool③ 진행\n"
    )

    print("\n" + "=" * 78)
    for (sid, title, content, node_id,
         exp_eid, exp_anomaly, exp_urgency, exp_cluster,
         exp_rack, exp_pct, note) in SCENARIOS:

        t1, t2, t3, t4 = _run(content, node_id)

        urgency_val = t2.urgency.value
        cluster_val = t3.cluster_id if t3 else None
        actual_rack = t4.node_metadata.rack
        actual_pct  = t4.alert_stats.alert_pct if t4.alert_stats else None

        ok = (
            t1.event_id   == exp_eid     and
            t2.is_anomaly == exp_anomaly and
            urgency_val   == exp_urgency and
            cluster_val   == exp_cluster and
            actual_rack   == exp_rack    and
            actual_pct    == exp_pct
        )
        mark = "✅ PASS" if ok else "❌ FAIL"
        if not ok:
            mismatches = []
            if t1.event_id   != exp_eid:     mismatches.append(f"event_id={t1.event_id}(기대:{exp_eid})")
            if t2.is_anomaly != exp_anomaly:  mismatches.append(f"is_anomaly={t2.is_anomaly}(기대:{exp_anomaly})")
            if urgency_val   != exp_urgency:  mismatches.append(f"urgency={urgency_val}(기대:{exp_urgency})")
            if cluster_val   != exp_cluster:  mismatches.append(f"cluster={cluster_val}(기대:{exp_cluster})")
            if actual_rack   != exp_rack:     mismatches.append(f"rack={actual_rack}(기대:{exp_rack})")
            if actual_pct    != exp_pct:      mismatches.append(f"alert_pct={actual_pct}(기대:{exp_pct})")
            failures.append(f"{sid} [{', '.join(mismatches)}]")

        routing     = _routing(t2.is_anomaly)
        node_str    = _node_summary(t4)
        cluster_str = f"cluster {cluster_val}" if cluster_val is not None else "미진행"

        # 콘솔 트레이스
        print(f"[{sid}] {title}")
        print(f"  Content  : {content[:65]}")
        print(f"  Node     : {node_id}")
        print(f"  Tool①    : event_id={t1.event_id}")
        print(f"  Tool②    : is_anomaly={t2.is_anomaly}, urgency={urgency_val} → {routing}")
        print(f"  Tool③    : {cluster_str}")
        print(f"  Tool④    : {node_str}")
        print(f"  기대     : eid={exp_eid}, anomaly={exp_anomaly}, urgency={exp_urgency}, cluster={exp_cluster}, rack={exp_rack}, pct={exp_pct}%")
        print(f"  결과     : {mark}")
        print("-" * 78)

        # 리포트 누적
        summary.append(
            f"| {sid} | {title} | `{t1.event_id}` | {t2.is_anomaly} / {urgency_val} "
            f"| {cluster_str} | {actual_pct}% | {mark} |"
        )
        detail.append(f"### {sid}. {title}\n")
        detail.append(f"- 설명: {note}")
        detail.append(f"- Content: `{content}`")
        detail.append(f"- Node: `{node_id}`")
        detail.append(f"- Tool①: `event_id={t1.event_id}`")
        detail.append(f"- Tool②: `is_anomaly={t2.is_anomaly}`, `urgency={urgency_val}` → **{routing}**")
        detail.append(f"- Tool③: `{cluster_str}`")
        detail.append(f"- Tool④: `{node_str}`")
        detail.append(
            f"- 기대: eid=`{exp_eid}`, anomaly=`{exp_anomaly}`, urgency=`{exp_urgency}`,"
            f" cluster=`{exp_cluster}`, rack=`{exp_rack}`, alert_pct=`{exp_pct}%`"
        )
        detail.append(f"- 결과: **{mark}**\n")

    table = [
        "\n## 요약\n",
        "| # | 시나리오 | event_id | is_anomaly / urgency | 클러스터 | alert_pct | 결과 |",
        "|---|---|---|---|---|---|---|",
        *summary,
        "",
    ]
    report = "\n".join(header + table + detail) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"리포트 생성: {REPORT_PATH}")
    print("=" * 78)

    assert not failures, "시나리오 실패:\n" + "\n".join(failures)
