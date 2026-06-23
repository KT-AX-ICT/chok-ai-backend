"""Node 정보 조회 Tool — 시나리오 검증 + 팀 공유용 리포트 생성.

각 시나리오마다 node_id → 파싱 결과(rack/midplane/node_slot 등) → alert_pct 조회 경로
→ 출력값을 추적해 보여준다. Compute/I/O 롤, 16진수 노드카드, rack/midplane 단위 조회,
미등록 노드, NULL/빈 문자열 예외를 전 경로 커버한다.

실행:
    uv run pytest tests/node_info/test_node_info_scenarios.py -s

부수 효과: tests/node_info/SCENARIO_REPORT.md 를 생성(덮어쓰기)한다.
"""

import datetime as _dt
from pathlib import Path

from app.agents.tools.node_info import _load_alert_stats, get_node_info, parse_node_id

REPORT_PATH = Path(__file__).parent / "SCENARIO_REPORT.md"

# ── 시나리오 정의 ─────────────────────────────────────────────────────────────
# (id, 제목, node_id 입력, 기대 메타데이터 dict, 기대 alert_pct|None, 설명)
SCENARIOS = [
    (
        "S1", "Compute 노드 — 최고빈도 이상 노드",
        "R30-M0-N9-C:J16-U01",
        {"rack": "R30", "midplane": "R30-M0", "node_slot": "N9",
         "node_role": "Compute", "socket_position": "J16", "processor_unit": "U01"},
        41.96,
        "BGL_2k 이상 로그 143건 중 60건(41.96%)이 집중된 노드. 직접 조회 경로.",
    ),
    (
        "S2", "I/O 노드 — role 파싱 확인",
        "R04-M1-N4-I:J18-U11",
        {"rack": "R04", "midplane": "R04-M1", "node_slot": "N4",
         "node_role": "I/O", "socket_position": "J18", "processor_unit": "U11"},
        0.7,
        "ntype=I → node_role=I/O 파싱 및 alert_pct 0.7% 직접 조회.",
    ),
    (
        "S3", "hex nodecard B — NB → node_slot N11",
        "R16-M0-NB-C:J07-U11",
        {"rack": "R16", "midplane": "R16-M0", "node_slot": "N11",
         "node_role": "Compute", "socket_position": "J07", "processor_unit": "U11"},
        0.7,
        "hex nodecard NB(=11) → node_slot=N11 변환. alert_pct 조회는 원본 키 그대로.",
    ),
    (
        "S4", "hex nodecard A — NA → node_slot N10",
        "R01-M1-NA-C:J13-U01",
        {"rack": "R01", "midplane": "R01-M1", "node_slot": "N10",
         "node_role": "Compute", "socket_position": "J13", "processor_unit": "U01"},
        0.7,
        "hex nodecard NA(=10) → node_slot=N10 변환.",
    ),
    (
        "S5", "rack 단위 조회 — 하위 최대 alert_pct",
        "R30",
        {"rack": "R30", "midplane": None, "node_slot": None,
         "node_role": None, "socket_position": None, "processor_unit": None},
        41.96,
        "rack 수준 조회: stats에 없으면 'R30-' 접두사 하위 노드 중 최대 41.96% 반환.",
    ),
    (
        "S6", "midplane 단위 조회 — 하위 최대 alert_pct",
        "R30-M0",
        {"rack": "R30", "midplane": "R30-M0", "node_slot": None,
         "node_role": None, "socket_position": None, "processor_unit": None},
        41.96,
        "midplane 수준 조회: 'R30-M0-' 접두사 하위 노드 중 최대 41.96% 반환.",
    ),
    (
        "S7", "미등록 노드 — alert_stats=None",
        "R99-M0-N0-C:J01-U01",
        {"rack": "R99", "midplane": "R99-M0", "node_slot": "N0",
         "node_role": "Compute", "socket_position": "J01", "processor_unit": "U01"},
        None,
        "node_stats.json에 없는 노드 → 파싱은 정상, alert_stats=None.",
    ),
    (
        "S8", "NULL 입력 — 전 필드 None",
        "NULL",
        {"rack": None, "midplane": None, "node_slot": None,
         "node_role": None, "socket_position": None, "processor_unit": None},
        None,
        "NULL은 누락 위치 플레이스홀더 → 파싱 불가, alert_stats=None.",
    ),
    (
        "S9", "빈 문자열 — 전 필드 None",
        "",
        {"rack": None, "midplane": None, "node_slot": None,
         "node_role": None, "socket_position": None, "processor_unit": None},
        None,
        "빈 입력 → 파싱 불가, alert_stats=None.",
    ),
    (
        "S10", "소문자 입력 — 자동 대문자 정규화",
        "r30-m0-n9-c:j16-u01",
        {"rack": "R30", "midplane": "R30-M0", "node_slot": "N9",
         "node_role": "Compute", "socket_position": "J16", "processor_unit": "U01"},
        41.96,
        "get_node_info 진입 시 .upper() 적용 → S1과 동일 결과.",
    ),
]


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _run(node_id: str):
    return get_node_info(node_id)


def _parse_summary(meta) -> str:
    parts = []
    if meta.rack:            parts.append(f"rack={meta.rack}")
    if meta.midplane:        parts.append(f"mp={meta.midplane}")
    if meta.node_slot:       parts.append(f"slot={meta.node_slot}")
    if meta.node_role:       parts.append(f"role={meta.node_role}")
    if meta.socket_position: parts.append(f"socket={meta.socket_position}")
    if meta.processor_unit:  parts.append(f"unit={meta.processor_unit}")
    return ", ".join(parts) if parts else "파싱 실패 → 전 필드 None"


def _lookup_path(node_id: str) -> str:
    """alert_pct 조회 경로를 설명 문자열로 반환."""
    stats = _load_alert_stats()
    norm = node_id.strip().upper()
    if norm in stats:
        return f"직접 조회 (exact match)"
    if norm.startswith("R"):
        candidates = [
            v for k, v in stats.items()
            if k == norm or k.startswith(norm + "-") or k.startswith(norm + ":")
        ]
        if candidates:
            best = max(candidates, key=lambda x: x.get("alert_pct", 0))
            return f"prefix 조회 → 후보 {len(candidates)}개 중 최대 {best['alert_pct']}%"
    return "미등록 → None"


# ── 메인 테스트 ───────────────────────────────────────────────────────────────

def test_scenarios_and_generate_report() -> None:
    header: list[str] = []
    detail: list[str] = ["\n## 상세 트레이스\n"]
    summary: list[str] = []
    failures: list[str] = []

    header.append("# Node 정보 조회 Tool — 시나리오 검증 리포트\n")
    header.append(
        f"- 생성: {_dt.date.today().isoformat()}\n"
        "- 대상 함수: `get_node_info(node_id)`\n"
        "- 판정 기준: node_id 파싱 계층(rack/midplane/node_slot/node_role) + alert_pct 조회 경로\n"
    )

    print("\n" + "=" * 78)
    for sid, title, node_id, expected_meta, expected_pct, note in SCENARIOS:
        result = _run(node_id)
        meta   = result.node_metadata

        # 파싱 검증
        ok_parse = all(getattr(meta, k) == v for k, v in expected_meta.items())
        # alert_pct 검증
        actual_pct = result.alert_stats.alert_pct if result.alert_stats else None
        ok_alert   = actual_pct == expected_pct
        ok = ok_parse and ok_alert
        mark = "✅ PASS" if ok else "❌ FAIL"

        if not ok:
            parse_errors = [
                f"{k}: 기대={v} / 실제={getattr(meta, k)}"
                for k, v in expected_meta.items()
                if getattr(meta, k) != v
            ]
            if not ok_alert:
                parse_errors.append(f"alert_pct: 기대={expected_pct} / 실제={actual_pct}")
            failures.append(f"{sid} [{', '.join(parse_errors)}]")

        parse_str  = _parse_summary(meta)
        lookup_str = _lookup_path(node_id)

        # 콘솔 트레이스
        print(f"[{sid}] {title}")
        print(f"  입력     : {node_id!r}")
        print(f"  파싱 결과: {parse_str}")
        print(f"  조회 경로: {lookup_str}")
        print(f"  alert_pct: {actual_pct}%")
        print(f"  기대 pct : {expected_pct}%  →  {mark}")
        print("-" * 78)

        # 리포트 누적
        pct_str = f"{actual_pct}%" if actual_pct is not None else "None"
        exp_pct_str = f"{expected_pct}%" if expected_pct is not None else "None"
        summary.append(
            f"| {sid} | {title} | `{node_id}` | {exp_pct_str} | {pct_str} | {mark} |"
        )
        detail.append(f"### {sid}. {title}\n")
        detail.append(f"- 설명: {note}")
        detail.append(f"- 입력: `{node_id}`")
        detail.append(f"- 파싱 결과: `{parse_str}`")
        detail.append(f"- 조회 경로: {lookup_str}")
        detail.append(f"- alert_pct: `{pct_str}`")
        detail.append(f"- 기대 alert_pct: `{exp_pct_str}` → **{mark}**\n")

    table = [
        "\n## 요약\n",
        "| # | 시나리오 | node_id | 기대 alert_pct | 실제 alert_pct | 결과 |",
        "|---|---|---|---|---|---|",
        *summary,
        "",
    ]
    report = "\n".join(header + table + detail) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"리포트 생성: {REPORT_PATH}")
    print("=" * 78)

    assert not failures, "시나리오 실패:\n" + "\n".join(failures)
