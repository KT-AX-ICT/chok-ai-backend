"""BGL_2k.log_structured.csv 정답 데이터 기반 정확도 검증.

실제 시스템 흐름을 재현한다:
  1. Level="FATAL" 로그만 필터 (실제 시스템은 FATAL만 Tool로 전달)
  2. Content → Tool ①(extract_event_template) → event_id 예측
  3. event_id → Tool ②(classify_anomaly) → is_anomaly 판정
  4. BGL Label 기준과 비교 (Label="-" → 정상, 그 외 → 비정상)

실행:
    uv run pytest tests/anomaly_classifier/test_anomaly_classifier_accuracy.py -v -s
"""

import csv
from collections import defaultdict
from pathlib import Path

from app.agents.tools.anomaly_classifier import classify_anomaly
from app.agents.tools.event_template import extract_event_template

STRUCTURED_CSV = Path("tests/BGL/BGL_2k.log_structured.csv")
REPORT_PATH = Path(__file__).parent / "ACCURACY_REPORT.md"


def _load_ground_truth() -> list[dict]:
    rows = []
    with STRUCTURED_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Level"] != "FATAL":
                continue
            rows.append({
                "line_id": row["LineId"],
                "content": row["Content"],
                "gt_event_id": row["EventId"],
                "label": row["Label"],
                "gt_anomaly": row["Label"] != "-",
            })
    return rows


def test_accuracy_against_bgl_ground_truth() -> None:
    rows = _load_ground_truth()

    tp = fp = tn = fn = 0
    mismatches: list[str] = []

    # event_id별 오분류 집계 (중복 제거 목적)
    event_errors: dict[str, dict] = defaultdict(lambda: {"fp": 0, "fn": 0, "label_set": set()})

    for row in rows:
        # Tool ① → Tool ② 실제 파이프라인 실행
        predicted_event_id = extract_event_template(row["content"]).event_id
        result = classify_anomaly(predicted_event_id)
        pred = result.is_anomaly
        gt = row["gt_anomaly"]

        if pred and gt:
            tp += 1
        elif pred and not gt:
            fp += 1
            event_errors[row["gt_event_id"]]["fp"] += 1
            event_errors[row["gt_event_id"]]["label_set"].add(row["label"])
            mismatches.append(
                f"FP  LineId={row['line_id']} event_id={row['gt_event_id']} "
                f"label={row['label']} → 비정상으로 잘못 분류"
            )
        elif not pred and gt:
            fn += 1
            event_errors[row["gt_event_id"]]["fn"] += 1
            event_errors[row["gt_event_id"]]["label_set"].add(row["label"])
            mismatches.append(
                f"FN  LineId={row['line_id']} event_id={row['gt_event_id']} "
                f"label={row['label']} → 정상으로 잘못 분류"
            )
        else:
            tn += 1

    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # ── 콘솔 출력 ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  BGL_2k 정확도 검증 결과  (총 {total}건)")
    print(f"{'='*60}")
    print(f"  Accuracy : {accuracy:.1%}  ({tp+tn}/{total})")
    print(f"  Precision: {precision:.1%}  (비정상 예측 중 실제 비정상)")
    print(f"  Recall   : {recall:.1%}  (실제 비정상 중 잡아낸 비율)")
    print(f"  F1 Score : {f1:.3f}")
    print(f"\n  TP={tp}  FP={fp}  TN={tn}  FN={fn}")

    if event_errors:
        print(f"\n  오분류 EventId별 요약:")
        for eid, err in sorted(event_errors.items()):
            print(f"    {eid}  FP={err['fp']}  FN={err['fn']}  labels={err['label_set']}")

    # ── 리포트 생성 ──────────────────────────────────────────────────────────
    lines = [
        "# anomaly_classifier 정확도 검증 리포트\n",
        f"- 데이터: `tests/BGL/BGL_2k.log_structured.csv` FATAL-level {total}건\n",
        f"- 파이프라인: Content → Tool①(extract_event_template) → Tool②(classify_anomaly)\n",
        f"- 정답 기준: `Label != \"-\"` → is_anomaly=True\n",
        "\n## 지표\n",
        f"| 지표 | 값 |",
        f"|---|---|",
        f"| Accuracy | **{accuracy:.1%}** ({tp+tn}/{total}) |",
        f"| Precision | {precision:.1%} |",
        f"| Recall | {recall:.1%} |",
        f"| F1 Score | {f1:.3f} |",
        f"\n## 혼동 행렬\n",
        f"| | 예측 정상 | 예측 비정상 |",
        f"|---|---|---|",
        f"| **실제 정상** | TN={tn} | FP={fp} |",
        f"| **실제 비정상** | FN={fn} | TP={tp} |",
    ]

    if event_errors:
        lines += [
            "\n## 오분류 EventId 요약\n",
            "| EventId | FP | FN | BGL Label |",
            "|---|---|---|---|",
        ]
        for eid, err in sorted(event_errors.items()):
            lines.append(
                f"| {eid} | {err['fp']} | {err['fn']} | {', '.join(sorted(err['label_set']))} |"
            )

    if mismatches:
        lines += ["\n## 오분류 상세 (처음 30건)\n"]
        for m in mismatches[:30]:
            lines.append(f"- {m}")
        if len(mismatches) > 30:
            lines.append(f"\n_... 외 {len(mismatches)-30}건_")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n  리포트: {REPORT_PATH}")
    print(f"{'='*60}")

    # Accuracy 80% 미만이면 실패로 처리
    assert accuracy >= 0.80, (
        f"Accuracy {accuracy:.1%} < 80% 기준치 미달 — 오분류 내역 확인 필요"
    )
