import json

from app.agents.tools.cluster import (
    METADATA_PATH,
    MISC_CLUSTER_ID,
    ClusterAssigner,
    ClusterResult,
    assign_cluster,
)

# 주입용 가짜 클러스터 (실제 clusters.json 비의존)
FAKE_CLUSTERS = [
    {"id": 3, "event_template": [
        {"event_id": "E111", "template": "rts: kernel terminated for reason <*>"},
        {"event_id": "E112", "template": "rts: kernel terminated for reason <*>: ..."},
    ]},
    {"id": 6, "event_template": [
        {"event_id": "E23", "template": "ciod: Error creating node map from file <*>: No child processes"},
    ]},
    {"id": 99, "event_template": []},  # 미분류 (빈 매핑)
]


def test_covered_event_id_returns_its_cluster() -> None:
    assigner = ClusterAssigner(clusters=FAKE_CLUSTERS)

    result = assigner.assign("E111")

    assert isinstance(result, ClusterResult)
    assert result.cluster_id == 3
    assert result.matched is True


def test_uncovered_valid_event_id_returns_misc_matched_true() -> None:
    assigner = ClusterAssigner(clusters=FAKE_CLUSTERS)

    result = assigner.assign("E1")  # 유효하지만 어떤 클러스터에도 없음

    assert result.cluster_id == MISC_CLUSTER_ID
    assert result.matched is True


def test_unknown_event_id_returns_misc_matched_true() -> None:
    assigner = ClusterAssigner(clusters=FAKE_CLUSTERS)

    result = assigner.assign("unknown")

    assert result.cluster_id == MISC_CLUSTER_ID
    assert result.matched is True


def test_multi_cluster_event_id_returns_misc_matched_false() -> None:
    # event_id 가 둘 이상 클러스터에 배정되면 단일 배정 불가 → 미분류 + matched=False
    ambiguous = [
        {"id": 0, "event_template": [{"event_id": "E1", "template": "a"}]},
        {"id": 1, "event_template": [{"event_id": "E1", "template": "b"}]},
    ]
    assigner = ClusterAssigner(clusters=ambiguous)

    result = assigner.assign("E1")

    assert result.cluster_id == MISC_CLUSTER_ID
    assert result.matched is False


def test_assign_cluster_real_metadata_covered() -> None:
    result = assign_cluster("E111")

    assert result.cluster_id == 3
    assert result.matched is True


def test_assign_cluster_real_metadata_uncovered_and_unknown() -> None:
    uncovered = assign_cluster("E1")
    unknown = assign_cluster("unknown")

    assert uncovered.cluster_id == 99 and uncovered.matched is True
    assert unknown.cluster_id == 99 and unknown.matched is True


def test_every_curated_event_id_maps_to_its_cluster() -> None:
    clusters = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    for cluster in clusters:
        if cluster["id"] == 99:  # 미분류는 빈 매핑
            continue
        for entry in cluster["event_template"]:
            result = assign_cluster(entry["event_id"])
            assert result.cluster_id == cluster["id"]
            assert result.matched is True
