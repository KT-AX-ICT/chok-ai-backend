"""Tool③ 클러스터 분류 (cluster assignment).

Tool① 의 event_id 를 사전 정의된 클러스터(장애 유형군)에 배정한다.
clusters.json 의 event_id -> cluster 고정 매핑을 역인덱스로 조회(결정적). 임베딩 없음.
LangGraph 등 오케스트레이션 프레임워크에 의존하지 않는 순수 함수로 작성한다.
"""

from pydantic import BaseModel

from app.agents.tools.event_template import UNKNOWN_EVENT_ID

MISC_CLUSTER_ID = 99


class ClusterResult(BaseModel):
    """클러스터 배정 결과 (내부 Tool 결과 모델)."""

    cluster_id: int
    matched: bool


class ClusterAssigner:
    """event_id -> cluster_id 역인덱스. clusters 를 주입하면 테스트에서 격리 검증할 수 있다."""

    def __init__(self, clusters: list[dict] | None = None) -> None:
        if clusters is None:
            clusters = list(_load_clusters())
        self._index: dict[str, int] = {}
        for cluster in clusters:
            cluster_id = cluster["id"]
            for entry in cluster.get("event_template", []):
                event_id = entry["event_id"]
                if event_id in self._index:
                    raise ValueError(
                        f"event_id {event_id!r} assigned to multiple clusters "
                        f"({self._index[event_id]} and {cluster_id})"
                    )
                self._index[event_id] = cluster_id

    def assign(self, event_id: str) -> ClusterResult:
        cluster_id = self._index.get(event_id)
        if cluster_id is not None:
            return ClusterResult(cluster_id=cluster_id, matched=True)
        # 미커버: 유효 event_id 는 미분류로 배정(matched=True), unknown 만 matched=False
        return ClusterResult(
            cluster_id=MISC_CLUSTER_ID,
            matched=event_id != UNKNOWN_EVENT_ID,
        )
