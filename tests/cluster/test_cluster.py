from app.agents.tools.cluster import (
    MISC_CLUSTER_ID,
    ClusterAssigner,
    ClusterResult,
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


def test_unknown_event_id_returns_misc_matched_false() -> None:
    assigner = ClusterAssigner(clusters=FAKE_CLUSTERS)

    result = assigner.assign("unknown")

    assert result.cluster_id == MISC_CLUSTER_ID
    assert result.matched is False


def test_duplicate_event_id_across_clusters_raises() -> None:
    bad = [
        {"id": 0, "event_template": [{"event_id": "E1", "template": "a"}]},
        {"id": 1, "event_template": [{"event_id": "E1", "template": "b"}]},
    ]

    try:
        ClusterAssigner(clusters=bad)
    except ValueError as e:
        assert "E1" in str(e)
    else:
        raise AssertionError("중복 event_id 인데 ValueError 가 발생하지 않음")
