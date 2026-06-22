"""Tool ② 이상 여부 + 긴급도 분류.

Tool ①(event_template.py)에서 받은 ``event_id``를 ``metadata/event_analysis_v2.json``
기반으로 판정한다. 라우팅 결정은 호출 측(FastAPI 엔드포인트 또는 오케스트레이터)이
``is_anomaly`` 를 보고 직접 수행한다.

- is_anomaly=False → 정상
  - impact: 정상 판단 근거 (LLM → result.analysis)
  - action: 주의 조건 또는 None (LLM → result.action)
- is_anomaly=True  → 비정상, urgency(Critical/High/Mid/Low) + 상세 정보 반환
  - impact: 장애 영향 범위 (LLM → result.analysis)
  - action: 권장 대응 조치 (LLM → result.action)
- event_id="unknown" 또는 미등록 → is_anomaly=True, category="UNKNOWN"

LangGraph 등 오케스트레이션 프레임워크에 의존하지 않는 순수 함수로 작성한다.
"""

import json
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

METADATA_PATH = Path(__file__).parent / "metadata" / "event_analysis_v2.json"

UNKNOWN_EVENT_ID = "unknown"


# ── 긴급도 ──────────────────────────────────────────────────────────────────
# API 응답 result.riskLevel 값으로 그대로 사용된다.
# NONE: 정상 이벤트 (is_anomaly=False) 전용.
class Urgency(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MID = "Mid"
    LOW = "Low"
    NONE = "None"


# ── Tool 출력 모델 ───────────────────────────────────────────────────────────
# 정상/비정상 모두 impact·action을 포함한다.
# - 정상: impact=정상 근거, action=주의 조건(없으면 None)
# - 비정상: impact=장애 영향, action=권장 대응
class AnomalyResult(BaseModel):
    event_id: str
    is_anomaly: bool
    urgency: Urgency        # 정상이면 Urgency.NONE
    category: str | None = None
    impact: str | None = None
    action: str | None = None


# ── 분류기 ───────────────────────────────────────────────────────────────────
class AnomalyClassifier:
    """이상 여부 + 긴급도 분류기. ``events`` 를 주입하면 테스트에서 격리 검증할 수 있다."""

    def __init__(self, events: dict | None = None) -> None:
        if events is None:
            events = _load_events()
        self._events = events

    def classify(self, event_id: str) -> AnomalyResult:
        # event_template.py 매칭 실패 → "unknown" 반환
        if event_id == UNKNOWN_EVENT_ID or event_id not in self._events:
            return AnomalyResult(
                event_id=event_id,
                is_anomaly=True,
                urgency=Urgency.MID,
                category="UNKNOWN",
                impact="알 수 없는 이벤트 — 직접 판단 필요.",
                action="로그 내용 직접 확인",
            )

        ev = self._events[event_id]
        is_anomaly: bool = ev["is_anomaly"]

        if not is_anomaly:
            return AnomalyResult(
                event_id=event_id,
                is_anomaly=False,
                urgency=Urgency.NONE,
                category=ev.get("category"),
                impact=ev.get("impact"),   # 정상 판단 근거
                action=ev.get("action"),   # 주의 조건 (없으면 None)
            )

        # 비정상 이벤트: riskLevel → urgency 변환 후 장애 상세 반환
        return AnomalyResult(
            event_id=event_id,
            is_anomaly=True,
            urgency=Urgency(ev["riskLevel"]),
            category=ev.get("category"),
            impact=ev.get("impact"),   # 장애 영향 범위
            action=ev.get("action"),   # 권장 대응 조치
        )


# ── 내부 로더 (프로세스 기동 시 1회만 읽음) ──────────────────────────────────
@lru_cache
def _load_events() -> dict:
    data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return data["events"]


@lru_cache
def _default_classifier() -> AnomalyClassifier:
    return AnomalyClassifier()


# ── FastAPI 호출 함수 ─────────────────────────────────────────────────────────────────
def classify_anomaly(event_id: str) -> AnomalyResult:
    """기본 메타데이터를 사용해 ``event_id``의 이상 여부와 긴급도를 판정한다."""
    return _default_classifier().classify(event_id)
