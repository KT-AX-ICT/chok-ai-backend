# Tool③ 클러스터 분류(cluster assignment) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tool①의 `event_id`를 사전 정의된 클러스터에 결정적으로 배정해 `ClusterResult(cluster_id, matched)`를 반환하는 도구를 만든다.

**Architecture:** `clusters.json`의 `event_id → cluster` 고정 매핑을 역인덱스(dict)로 조회. 벡터 임베딩 없음. Tool①(`event_template.py`)과 동일한 구조(Pydantic 결과 모델 + 주입 가능한 Assigner + `lru_cache` 로더 + 순수 함수 진입점).

**Tech Stack:** Python 3.12, pydantic v2, 표준 라이브러리(`json`, `functools`, `pathlib`). 새 의존성 없음.

## Global Constraints

- Python `>=3.12,<3.13`. 새 의존성 추가 금지(stdlib + 기존 pydantic만).
- 프레임워크(LangGraph 등) 비종속 순수 함수로 작성.
- 메타데이터 로드/파싱 실패와 event_id 중복 배정은 **fail-fast**(예외를 삼키지 않음).
- `MISC_CLUSTER_ID = 99`. `matched`는 "event_id가 유효한지(unknown 아님) = 배정 성공 여부".
- unknown 판별은 Tool①의 `UNKNOWN_EVENT_ID` 상수를 재사용(단일 출처).
- 메타데이터: [app/agents/tools/metadata/clusters.json](../../../app/agents/tools/metadata/clusters.json) (id 0~7 큐레이션 + id 99 미분류, 빈 매핑).
- 참조 스펙: [docs/superpowers/specs/2026-06-22-cluster-assignment-tool-design.md](../specs/2026-06-22-cluster-assignment-tool-design.md)

---

### Task 1: ClusterResult 모델 + ClusterAssigner 핵심 로직 (주입식, 파일 I/O 없음)

**Files:**
- Create: `app/agents/tools/cluster.py`
- Test: `tests/cluster/test_cluster.py`

**Interfaces:**
- Consumes: `app.agents.tools.event_template.UNKNOWN_EVENT_ID` (값 `"unknown"`)
- Produces:
  - `MISC_CLUSTER_ID: int = 99`
  - `class ClusterResult(BaseModel)` — 필드 `cluster_id: int`, `matched: bool`
  - `class ClusterAssigner` — 생성자 `__init__(self, clusters: list[dict] | None = None)`, 메서드 `assign(self, event_id: str) -> ClusterResult`
  - `clusters` dict 형태: `{"id": int, "event_template": [{"event_id": str, "template": str}, ...]}`

- [ ] **Step 1: 실패 테스트 작성**

`tests/cluster/test_cluster.py`:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/cluster/test_cluster.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.tools.cluster'`

- [ ] **Step 3: 최소 구현 작성**

`app/agents/tools/cluster.py`:

```python
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
```

> 참고: `_load_clusters`는 Task 2에서 추가한다. Task 1 테스트는 `clusters`를 주입하므로 `_load_clusters`를 호출하지 않는다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/cluster/test_cluster.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/agents/tools/cluster.py tests/cluster/test_cluster.py
git commit -m "feat: cluster assigner 핵심 로직 (event_id -> cluster_id 역인덱스)"
```

---

### Task 2: 실제 메타데이터 로더 + 진입점 + 정합성 검증

**Files:**
- Modify: `app/agents/tools/cluster.py` (로더/진입점 추가)
- Test: `tests/cluster/test_cluster.py` (실제 metadata 테스트 추가)

**Interfaces:**
- Consumes: Task 1의 `ClusterAssigner`, `ClusterResult`, `MISC_CLUSTER_ID`
- Produces:
  - `METADATA_PATH: pathlib.Path` — `clusters.json` 경로
  - `_load_clusters() -> tuple[dict, ...]` (`@lru_cache`)
  - `_default_assigner() -> ClusterAssigner` (`@lru_cache`)
  - `assign_cluster(event_id: str) -> ClusterResult` — 공식 진입점

- [ ] **Step 1: 실패 테스트 작성 (파일 끝에 추가)**

`tests/cluster/test_cluster.py` 에 추가:

```python
import json

from app.agents.tools.cluster import METADATA_PATH, assign_cluster


def test_assign_cluster_real_metadata_covered() -> None:
    result = assign_cluster("E111")

    assert result.cluster_id == 3
    assert result.matched is True


def test_assign_cluster_real_metadata_uncovered_and_unknown() -> None:
    uncovered = assign_cluster("E1")
    unknown = assign_cluster("unknown")

    assert uncovered.cluster_id == 99 and uncovered.matched is True
    assert unknown.cluster_id == 99 and unknown.matched is False


def test_every_curated_event_id_maps_to_its_cluster() -> None:
    clusters = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    for cluster in clusters:
        if cluster["id"] == 99:  # 미분류는 빈 매핑
            continue
        for entry in cluster["event_template"]:
            result = assign_cluster(entry["event_id"])
            assert result.cluster_id == cluster["id"]
            assert result.matched is True
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/cluster/test_cluster.py -v`
Expected: FAIL — `ImportError: cannot import name 'METADATA_PATH'` (또는 `assign_cluster` 미정의)

- [ ] **Step 3: 로더/진입점 구현 (cluster.py 에 추가)**

`app/agents/tools/cluster.py` 상단 import 와 상수 보강:

```python
import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from app.agents.tools.event_template import UNKNOWN_EVENT_ID

METADATA_PATH = Path(__file__).parent / "metadata" / "clusters.json"
MISC_CLUSTER_ID = 99
```

파일 끝에 추가:

```python
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
```

> `clusters.json`은 최상위가 JSON 배열이므로 `tuple(data)` 로 그대로 감싼다.

- [ ] **Step 4: 테스트 통과 확인 (전체 스위트 포함)**

Run: `uv run pytest -q`
Expected: PASS (기존 8 + 신규 7 = 15 passed)

- [ ] **Step 5: 린트 + 커밋**

```bash
uv run ruff check app/agents/tools/cluster.py tests/cluster/test_cluster.py
git add app/agents/tools/cluster.py tests/cluster/test_cluster.py
git commit -m "feat: cluster 메타데이터 로더 + assign_cluster 진입점 + 정합성 검증"
```

---

## Self-Review

**1. Spec coverage:**
- 결정적 lookup(임베딩 없음) → Task 1 Assigner ✅
- 입출력 계약 `event_id → ClusterResult(cluster_id, matched)` → Task 1 ✅
- 미분류 99, matched 의미(유효=True, unknown=False) → Task 1 Step 1/3 ✅
- 미분류 clusters.json id:99 빈 매핑 → 메타데이터에 이미 존재, Task 2 정합성 테스트가 99 스킵 ✅
- 캐싱 로더 + 진입점 → Task 2 ✅
- fail-fast + 중복 배정 검증 → Task 1 `test_duplicate...` + 구현 ✅
- 테스트(커버/미커버/unknown/중복/정합성) → Task 1·2 ✅

**2. Placeholder scan:** "TBD"/"TODO"/"적절히" 없음. 모든 코드 스텝에 실제 코드 포함. ✅

**3. Type consistency:** `ClusterResult(cluster_id:int, matched:bool)`, `ClusterAssigner.assign(event_id:str)`, `assign_cluster(event_id:str)`, `MISC_CLUSTER_ID=99` — Task 1/2 전반 일치. `_load_clusters`는 Task 1 본문에서 "Task 2에서 추가"로 명시, Task 2에서 정의 → 일관. ✅
