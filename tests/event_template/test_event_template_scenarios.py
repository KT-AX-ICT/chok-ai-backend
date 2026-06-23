"""이벤트 템플릿 추출 Tool — 시나리오 검증 + 팀 공유용 리포트 생성.

각 시나리오마다 입력 -> 매칭 후보(literal_len/wildcard_count) -> tie-break 판정
근거 -> 출력 값을 추적해 보여준다. 2k 원본뿐 아니라 합성(임의) 로그로 엣지를 검증한다.

실행:
    uv run pytest tests/event_template/test_event_template_scenarios.py -s

부수 효과: tests/event_template/SCENARIO_REPORT.md 를 생성(덮어쓰기)한다.
"""

import datetime as _dt
from pathlib import Path

from app.agents.tools.event_template import EventTemplateExtractor

REPORT_PATH = Path(__file__).parent / "SCENARIO_REPORT.md"

# 합성 시나리오에서 주입할 템플릿 묶음 ---------------------------------------
_TIE_LL = [
    {"event_id": "MANYWILD", "event_template": "a <*> b <*> c",
     "regex": r"^a\ (.*?)\ b\ (.*?)\ c$", "literal_len": 6, "wildcard_count": 2},
    {"event_id": "FEWWILD", "event_template": "a <*> b x c",
     "regex": r"^a\ (.*?)\ b\ x\ c$", "literal_len": 6, "wildcard_count": 1},
]
_CATCH_ALL = [
    {"event_id": "CATCHALL", "event_template": "svc done: <*>",
     "regex": r"^svc\ done:\ (.*?)$", "literal_len": 9, "wildcard_count": 1},
    {"event_id": "SPECIFIC", "event_template": "svc done: detail <*> <*>",
     "regex": r"^svc\ done:\ detail\ (.*?)\ (.*?)$", "literal_len": 16, "wildcard_count": 2},
]
_FULL_TIE = [
    {"event_id": "E_ZZZ", "event_template": "<*> foo",
     "regex": r"^(.*?)\ foo$", "literal_len": 4, "wildcard_count": 1},
    {"event_id": "E_AAA", "event_template": "<*> foo",
     "regex": r"^(.*?)\ foo$", "literal_len": 4, "wildcard_count": 1},
]

# 시나리오 정의: (id, 제목, 입력, 기대 event_id, 주입템플릿|None, 설명) ----------
SCENARIOS = [
    ("S1", "정상 단일 매칭",
     "instruction cache parity error corrected", "E77", None,
     "단일 후보 happy path"),
    ("S2a", "wildcard 정규화 #1",
     "12 ddr error(s) detected and corrected on rank 0, symbol 4 over 1234 seconds", "E1", None,
     "<*> 가 값을 흡수 → 같은 유형"),
    ("S2b", "wildcard 정규화 #2",
     "99 ddr error(s) detected and corrected on rank 7, symbol 1 over 5 seconds", "E1", None,
     "다른 값이어도 S2a 와 같은 E1 로 정규화"),
    ("S4", "tie-break 정상(실제 2k 케이스)",
     "rts: kernel terminated for reason 1001: bad message header: invalid cpu, "
     "type=0x5, cpu=3, index=2, total=4", "E112", None,
     "E111(catch-all) 과 E112 동시 매칭 → literal_len 으로 E112"),
    ("S5", "tie-break 비교군",
     "rts: kernel terminated for reason 1001", "E111", None,
     "짧은 로그는 E111 단독 매칭(tie 없음) — '언제 애매한가' 대조"),
    ("S6a", "unknown — 무관 텍스트",
     "this is not a real bgl log at all", "unknown", None,
     "매칭 0건"),
    ("S6b", "unknown — near-miss",
     "instruction cache parity error CORRECTED", "unknown", None,
     "대소문자 1글자 차이도 ^...$ 엄격 매칭으로 불일치 (fuzzy 안 함)"),
    ("S7a", "엣지 — 앞뒤 공백",
     "   instruction cache parity error corrected   ", "E77", None,
     "strip 후 정상 매칭"),
    ("S7b", "엣지 — 빈 문자열",
     "", "unknown", None,
     "빈 입력 → unknown"),
    ("S8", "합성 — literal_len 동률",
     "a 1 b x c", "FEWWILD", _TIE_LL,
     "ll 동률(6) → wildcard_count 적은 FEWWILD 선택 (2번 키)"),
    ("S9", "합성 — catch-all 삼킴",
     "svc done: detail alpha beta", "SPECIFIC", _CATCH_ALL,
     "catch-all 이 다 삼켜도 literal_len 으로 구체 SPECIFIC 선택 (1번 키)"),
    ("S10", "합성 — 완전 동률",
     "x foo", "E_AAA", _FULL_TIE,
     "모든 키 동률 → event_id 오름차순으로 결정적 선택 (3번 키, 리스트순서 무관)"),
]

_real_extractor = EventTemplateExtractor()


def _run(content, templates):
    extractor = EventTemplateExtractor(templates) if templates else _real_extractor
    text = content.strip()
    candidates = [t for t in extractor._templates if t.pattern.match(text)]
    candidates.sort(key=lambda t: (-t.literal_len, t.wildcard_count, t.event_id))
    result = extractor.extract(content)
    return candidates, result


def _decision(candidates) -> str:
    if not candidates:
        return "매칭 0건 → unknown"
    if len(candidates) == 1:
        return "단일 매칭"
    return f"다중 매칭 {len(candidates)}개 → tie-break(literal_len↓, wildcard_count↑, event_id↑)"


def test_scenarios_and_generate_report() -> None:
    header: list[str] = []
    detail: list[str] = ["\n## 상세 트레이스\n"]
    summary: list[str] = []
    failures: list[str] = []

    header.append("# 이벤트 템플릿 추출 Tool — 시나리오 검증 리포트\n")
    header.append(
        f"- 생성: {_dt.date.today().isoformat()}\n"
        "- 대상 함수: `extract_event_template(content)`\n"
        "- tie-break 규칙: **literal_len 내림차순 → wildcard_count 오름차순 → event_id 오름차순**\n"
    )

    print("\n" + "=" * 78)
    for sid, title, content, expected, templates, note in SCENARIOS:
        candidates, result = _run(content, templates)
        ok = result.event_id == expected
        mark = "✅ PASS" if ok else "❌ FAIL"
        if not ok:
            failures.append(f"{sid}: 기대 {expected} != 실제 {result.event_id}")

        cand_str = (
            ", ".join(
                f"{t.event_id}(ll={t.literal_len},wc={t.wildcard_count})"
                for t in candidates
            )
            or "없음"
        )
        shown = content if len(content) <= 90 else content[:90] + "…"

        # --- 콘솔 트레이스 ---
        print(f"[{sid}] {title}")
        print(f"  입력 : {content!r}")
        print(f"  후보 : {cand_str}")
        print(f"  판정 : {_decision(candidates)}")
        print(f"  출력 : event_id={result.event_id}, matched={result.matched}")
        print(f"  기대 : {expected}  →  {mark}")
        print("-" * 78)

        # --- 리포트 누적 ---
        summary.append(f"| {sid} | {title} | `{shown}` | {expected} | {result.event_id} | {mark} |")
        detail.append(f"### {sid}. {title}\n")
        detail.append(f"- 설명: {note}")
        detail.append(f"- 입력: `{content}`")
        detail.append(f"- 후보(매칭 템플릿): {cand_str}")
        detail.append(f"- 판정: {_decision(candidates)}")
        detail.append(
            f"- 출력: `event_id={result.event_id}`, `matched={result.matched}`"
        )
        detail.append(f"- 기대: `{expected}` → **{mark}**\n")

    table = ["\n## 요약\n",
             "| # | 시나리오 | 입력(요약) | 기대 | 실제 | 결과 |",
             "|---|---|---|---|---|---|", *summary, ""]
    report = "\n".join(header + table + detail) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"리포트 생성: {REPORT_PATH}")
    print("=" * 78)

    assert not failures, "시나리오 실패:\n" + "\n".join(failures)
