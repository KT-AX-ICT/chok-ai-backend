"""Tool ④ 노드 정보 조회

- node_id 문자열을 파싱해 하드웨어 계층(rack/midplane/node_slot 등)을 분리한다.
- node_stats.json에서 해당 노드의 과거 이상 발생 비율(alert_pct)을 조회한다.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

NODE_STATS_PATH = Path(__file__).parent / "metadata" / "node_stats.json"

_NC_HEX  = {f"{i:X}": str(i) for i in range(16)}  # 노드카드 16진수(0~F) → 10진수 변환 테이블
_NODE_RE = re.compile(                              # BGL 노드 ID 계층 파싱 정규식 (R-M-N-C/I:J-U)
    r"R(?P<rack>[0-9A-Fa-f]+)"
    r"(?:-M(?P<midplane>\d)"
    r"(?:-N(?P<nodecard>[0-9A-Fa-f]+)"
    r"(?:-(?P<ntype>C|I)"
    r"(?::J(?P<jslot>\d+)-U(?P<unit>\d+))?)?)?)?"
    r"$"
)


# ── Pydantic 출력 모델 ────────────────────────────────────────────────────────

class NodeMetadata(BaseModel):
    rack:            str | None = None  # 예: "R30"
    midplane:        str | None = None  # 예: "R30-M0"
    node_slot:       str | None = None  # 예: "N9"
    node_role:       str | None = None  # "Compute" 또는 "I/O"
    socket_position: str | None = None  # 예: "J16"
    processor_unit:  str | None = None  # 예: "U01"


class AlertStats(BaseModel):
    alert_pct: float  # 2k 샘플 기준 전체 이상 로그 중 이 노드 발생 비율(%)


class NodeInfoResult(BaseModel):
    node_metadata: NodeMetadata       # node_id 파싱 결과
    alert_stats:   AlertStats | None  # 사전 집계 이상 비율 (미등록 노드는 None)


# ── 노드 ID 파서 ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=None)
def parse_node_id(node_id: str) -> NodeMetadata:
    if not node_id or node_id in ("NULL", "UNKNOWN_LOCATION"):
        return NodeMetadata()

    m = _NODE_RE.match(node_id)
    if not m or not m.group("rack"):
        return NodeMetadata()

    rack  = m.group("rack")
    mp    = m.group("midplane")
    nc    = m.group("nodecard")
    ntype = m.group("ntype")
    jslot = m.group("jslot")
    unit  = m.group("unit")

    nc_num = _NC_HEX.get(nc, nc) if nc else None

    return NodeMetadata(
        rack=f"R{rack}",
        midplane=f"R{rack}-M{mp}"                        if mp    is not None else None,
        node_slot=f"N{nc_num}"                           if nc    is not None else None,
        node_role=("Compute" if ntype == "C" else "I/O") if ntype is not None else None,
        socket_position=f"J{jslot}"                      if jslot is not None else None,
        processor_unit=f"U{unit}"                        if unit  is not None else None,
    )


# ── 데이터 로더 ───────────────────────────────────────────────────────────────

@lru_cache
def _load_alert_stats(path: str = str(NODE_STATS_PATH)) -> dict:
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("nodes", {})


# ── alert_pct 조회 ────────────────────────────────────────────────────────────

def _get_alert_stats(node_id: str, stats: dict) -> AlertStats | None:
    stat = stats.get(node_id)
    if stat is None and node_id.startswith("R"):
        # 랙/미드플레인 단위 조회 시 하위 노드 중 alert_pct 가 가장 높은 항목 반환
        candidates = [
            v for k, v in stats.items()
            if k == node_id or k.startswith(node_id + "-") or k.startswith(node_id + ":")
        ]
        if candidates:
            stat = max(candidates, key=lambda x: x.get("alert_pct", 0))
    if stat is None:
        return None
    return AlertStats(alert_pct=stat.get("alert_pct", 0.0))


# ── 진입점 ───────────────────────────────────────────────────────────────────

def get_node_info(node_id: str) -> NodeInfoResult:
    node_id = (node_id or "").strip().upper()
    return NodeInfoResult(
        node_metadata=parse_node_id(node_id),
        alert_stats=_get_alert_stats(node_id, _load_alert_stats()),
    )
