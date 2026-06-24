"""Tool③ 클러스터 분류 (cluster assignment).

Tool① 의 event_id 를 사전 정의된 클러스터(장애 유형군)에 배정한다.
clusters.json 의 event_id -> cluster 고정 매핑을 역인덱스로 조회(결정적). 임베딩 없음.
LangGraph 등 오케스트레이션 프레임워크에 의존하지 않는 순수 함수로 작성한다.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

METADATA_PATH = Path(__file__).parent / "metadata" / "clusters.json"
MISC_CLUSTER_ID = 99


class ClusterResult(BaseModel):
    """클러스터 배정 결과 (내부 Tool 결과 모델)."""

    cluster_id: int = Field(
        description="배정된 클러스터 ID. 단일 배정 실패·미커버·unknown 은 "
        "미분류(99). API result.clusterId 로 직결.",
    )
    matched: bool = Field(
        description="단일 배정 성공 여부. 0개 매핑(미분류)도 True, "
        "2개 이상(다중 배정 모호)만 False.",
    )


class ClusterAssigner:
    """event_id -> cluster_id 역인덱스. clusters 를 주입하면 테스트에서 격리 검증할 수 있다."""

    def __init__(self, clusters: list[dict] | None = None) -> None:
        if clusters is None:
            clusters = list(_load_clusters())
        # event_id 가 여러 클러스터에 걸칠 수 있으므로 cluster_id 집합으로 보관한다.
        self._index: dict[str, set[int]] = {}
        for cluster in clusters:
            cluster_id = cluster["id"]
            for entry in cluster.get("event_template", []):
                self._index.setdefault(entry["event_id"], set()).add(cluster_id)

    def assign(self, event_id: str) -> ClusterResult:
        cluster_ids = self._index.get(event_id, set())
        if len(cluster_ids) == 1:
            # 단일 클러스터에 명확히 배정.
            return ClusterResult(cluster_id=next(iter(cluster_ids)), matched=True)
        # 0개(미커버·unknown) → 미분류이지만 배정 가능 → matched=True
        # 2개 이상(다중 배정) → 단일 배정 불가 → matched=False
        return ClusterResult(
            cluster_id=MISC_CLUSTER_ID,
            matched=len(cluster_ids) == 0,
        )


@lru_cache
def _load_clusters() -> tuple[dict, ...]:
    data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return tuple(data)


@lru_cache
def _default_assigner() -> ClusterAssigner:
    return ClusterAssigner()


def assign_cluster(event_id: str) -> ClusterResult:
    """기본 메타데이터를 사용해 event_id 를 클러스터에 배정한다."""

    return _default_assigner().assign(event_id)
