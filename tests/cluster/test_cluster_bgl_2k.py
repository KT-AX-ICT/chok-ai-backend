"""BGL_2k 전건 클러스터 배정 검증 (Tool① → Tool③ 통합).

structured CSV 의 raw Content 를 Tool① 로 event_id 판정 → Tool③ 로 클러스터 배정한다.
2000건 전부 규칙대로 배정되는지(커버→해당 클러스터, 그 외→99, 전건 matched=True) 확인하고
클러스터별 배정 분포를 출력한다.

실행:
    uv run pytest tests/cluster/test_cluster_bgl_2k.py -s
"""

import csv
import json
from collections import Counter
from pathlib import Path

from app.agents.tools.cluster import METADATA_PATH, assign_cluster
from app.agents.tools.event_template import extract_event_template

CSV_PATH = Path(__file__).parent.parent / "BGL" / "BGL_2k.log_structured.csv"


def _expected_event_to_cluster() -> dict[str, int]:
    clusters = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    mapping: dict[str, int] = {}
    for cluster in clusters:
        for entry in cluster["event_template"]:
            mapping[entry["event_id"]] = cluster["id"]
    return mapping


def test_bgl_2k_all_rows_assigned_by_rule() -> None:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    expected = _expected_event_to_cluster()
    distribution: Counter = Counter()

    for r in rows:
        event_id = extract_event_template(r["Content"]).event_id
        result = assign_cluster(event_id)
        distribution[result.cluster_id] += 1

        # 실데이터에는 다중 배정 event_id 가 없으므로 전건 matched=True
        assert result.matched is True, f"{event_id} → matched=False (예상치 못한 다중 배정)"
        # 커버된 event_id 는 정확한 클러스터, 그 외(미커버·unknown)는 미분류(99)
        if event_id in expected:
            assert result.cluster_id == expected[event_id], (
                f"{event_id}: 기대 {expected[event_id]} != 실제 {result.cluster_id}"
            )
        else:
            assert result.cluster_id == 99

    print(f"\n[BGL_2k 클러스터 배정 분포] 총 {sum(distribution.values())}건")
    for cluster_id in sorted(distribution):
        label = "미분류" if cluster_id == 99 else f"cluster {cluster_id}"
        print(f"  {label}: {distribution[cluster_id]}건")

    assert sum(distribution.values()) == len(rows)
