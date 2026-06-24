"""BGL_2k 전건 정답 비율(정확도) 검증.

BGL_2k 구조화 로그의 raw ``Content`` 만으로 Tool① 이 정답 ``EventId`` 를
얼마나 복원하는지 측정한다. 정답 컬럼(EventId/EventTemplate)은 비교에만 쓰고
예측 입력에는 ``Content`` 만 넣는다 = "이벤트 템플릿 없는 입력" 모사.

실행:
    uv run pytest tests/test_event_template_accuracy.py -v -s
"""

import csv
import collections
from pathlib import Path

from app.agents.tools.event_template import extract_event_template

CSV_PATH = Path(__file__).parent.parent / "BGL" / "BGL_2k.log_structured.csv"


def _evaluate() -> dict:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    correct = 0
    unknown = 0
    mismatches: list[tuple[str, str, str]] = []
    wrong_by_truth: collections.Counter = collections.Counter()

    for r in rows:
        pred = extract_event_template(r["Content"]).event_id
        truth = r["EventId"]
        if pred == truth:
            correct += 1
        else:
            if pred == "unknown":
                unknown += 1
            wrong_by_truth[truth] += 1
            mismatches.append((truth, pred, r["Content"]))

    total = len(rows)
    return {
        "total": total,
        "correct": correct,
        "unknown": unknown,
        "accuracy": correct / total * 100 if total else 0.0,
        "mismatches": mismatches,
        "wrong_by_truth": wrong_by_truth,
    }


def test_bgl_2k_event_id_accuracy_is_100_percent() -> None:
    stats = _evaluate()

    summary = (
        f"\n총 {stats['total']}건 | 정확 {stats['correct']} | "
        f"오답 {stats['total'] - stats['correct']} | unknown {stats['unknown']} | "
        f"정확도 {stats['accuracy']:.2f}%"
    )
    print(summary)
    for truth, pred, content in stats["mismatches"][:20]:
        print(f"  {truth} -> {pred} | {content[:70]}")

    assert stats["accuracy"] == 100.0, (
        f"정답 비율 {stats['accuracy']:.2f}% (오답 {stats['total'] - stats['correct']}건). "
        f"오답 EventId: {dict(stats['wrong_by_truth'])}"
    )
