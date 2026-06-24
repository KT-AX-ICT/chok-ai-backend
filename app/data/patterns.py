"""
패턴 seed 로더 — Tool③(클러스터 분류)용

Spring의 pattern_view(클러스터 카탈로그)를 export한 로컬 seed 파일(clusters.json)을
적재해, Tool①이 산출한 event_id로 cluster_id를 매칭한다.

[계약]
- seed 출처 : Spring pattern_view 기반 클러스터 정의 (event_template에 event_id 포함)
- 매칭 키   : event_id (Tool① 산출) → cluster_id (= cluster.id)
- 한 클러스터가 여러 event_id를 가짐 → event_id → cluster_id 역색인으로 매칭
- 미일치    : '미분류' catch-all 버킷(event_template이 빈 클러스터)으로 배정.
              그런 버킷이 없거나 seed 미적재면 None (log_analysis.cluster_id NULL 허용)

seed 파일 위치는 app/data/clusters.json (데이터팀 수령분).
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

logger = logging.getLogger(__name__)

# patterns.py 와 같은 디렉터리(app/data)의 clusters.json
_SEED_PATH = Path(__file__).resolve().parent / "clusters.json"


class TemplateEntry(BaseModel):
    """클러스터에 속한 이벤트 템플릿 한 건 (event_id ↔ 템플릿 문자열)."""

    model_config = ConfigDict(extra="ignore")

    event_id: str
    template: str = ""


class Cluster(BaseModel):
    """패턴(클러스터) 한 건 — clusters.json 한 원소. id = cluster_id."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., ge=0)                                   # cluster_id
    cluster_title: str = ""                                      # 클러스터 제목
    description: str = ""                                        # 클러스터 설명
    event_template: list[TemplateEntry] = Field(default_factory=list)
    importance: str = ""                                         # High/Middle/Low


@lru_cache
def load_clusters() -> list[Cluster]:
    """clusters.json을 적재(1회 캐시). 파일 없으면 빈 리스트."""
    if not _SEED_PATH.exists():
        logger.warning(
            "패턴 seed 파일 없음: %s — Tool③ 매칭 비활성(cluster_id=None)", _SEED_PATH
        )
        return []
    raw = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    return TypeAdapter(list[Cluster]).validate_python(raw)


@lru_cache
def _event_index() -> dict[str, int]:
    """event_id → cluster_id 역색인."""
    index: dict[str, int] = {}
    for cluster in load_clusters():
        for entry in cluster.event_template:
            index[entry.event_id] = cluster.id
    return index


@lru_cache
def _clusters_by_id() -> dict[int, Cluster]:
    return {c.id: c for c in load_clusters()}


@lru_cache
def _unclassified_id() -> int | None:
    """미분류 catch-all 버킷 id — event_template이 빈 클러스터(없으면 None)."""
    for cluster in load_clusters():
        if not cluster.event_template:
            return cluster.id
    return None


def match_cluster_id(event_id: str | None) -> int | None:
    """event_id로 cluster_id를 매칭. event_id가 None이거나 미일치면 미분류 버킷(없으면 None)."""
    if event_id is None:
        return _unclassified_id()
    return _event_index().get(event_id, _unclassified_id())


def match_cluster(event_id: str | None) -> Cluster | None:
    """event_id로 클러스터(패턴) 전체를 매칭. None/미일치 시 미분류 버킷(없으면 None)."""
    cluster_id = match_cluster_id(event_id)
    if cluster_id is None:
        return None
    return _clusters_by_id().get(cluster_id)
