from app.agents.tools.anomaly_classifier import (
    AnomalyClassifier,
    AnomalyResult,
    Urgency,
    classify_anomaly,
)


# ── 정상 이벤트 ──────────────────────────────────────────────────────────────

def test_normal_event_returns_is_anomaly_false() -> None:
    # E7: ECC 자동 정정 완료 — 정상 이벤트
    result = classify_anomaly("E7")

    assert result.is_anomaly is False
    assert result.urgency is None


def test_normal_event_includes_impact() -> None:
    # 정상 경로에서 LLM이 근거를 생성하려면 impact(정상 근거)가 있어야 한다
    result = classify_anomaly("E7")

    assert result.impact is not None


def test_normal_register_dump_event() -> None:
    # E43: core configuration register 덤프 — 순수 정보성 이벤트
    result = classify_anomaly("E43")

    assert result.is_anomaly is False
    assert result.urgency is None
    assert result.category == "UNKNOWN"


# ── 비정상 이벤트 — 긴급도별 ─────────────────────────────────────────────────

def test_critical_anomaly_event() -> None:
    # E52: data storage interrupt — KERN/Critical
    result = classify_anomaly("E52")

    assert result.is_anomaly is True
    assert result.urgency == Urgency.CRITICAL
    assert result.category == "KERN"


def test_high_anomaly_event() -> None:
    # E1: DDR 메모리 오류 — HARDWARE/High
    result = classify_anomaly("E1")

    assert result.is_anomaly is True
    assert result.urgency == Urgency.HIGH
    assert result.category == "HARDWARE"


def test_mid_anomaly_event() -> None:
    # E19: ciod 오류 — APP/Mid
    result = classify_anomaly("E19")

    assert result.is_anomaly is True
    assert result.urgency == Urgency.MID
    assert result.category == "APP"


def test_low_anomaly_event() -> None:
    # E5: L3 EDRAM 정정 가능 오류 — HARDWARE/Low (비정상이지만 자동 정정됨)
    result = classify_anomaly("E5")

    assert result.is_anomaly is True
    assert result.urgency == Urgency.LOW


def test_anomaly_event_includes_impact_and_action() -> None:
    # 비정상 이벤트는 클러스터링 tool + LLM을 위해 impact·action이 있어야 한다
    result = classify_anomaly("E1")

    assert result.impact is not None
    assert result.action is not None


# ── 미분류 이벤트 ────────────────────────────────────────────────────────────

def test_unknown_event_id_is_treated_as_anomaly() -> None:
    # 템플릿 매칭 실패 → event_id="unknown" → 에러로 처리
    result = classify_anomaly("unknown")

    assert result.is_anomaly is True
    assert result.category == "UNKNOWN"
    assert result.urgency == Urgency.MID


# ── 격리 테스트 (의존성 주입) ────────────────────────────────────────────────

def test_custom_events_injection() -> None:
    # AnomalyClassifier에 직접 이벤트를 주입해 메타데이터 파일과 독립적으로 검증
    events = {
        "E_TEST_NORMAL": {
            "category": "HARDWARE",
            "riskLevel": "Low",
            "is_anomaly": False,
            "impact": "정상 동작 범위.",
            "action": None,
        },
        "E_TEST_ERROR": {
            "category": "KERN",
            "riskLevel": "Critical",
            "is_anomaly": True,
            "impact": "치명적 오류.",
            "action": "즉각 점검",
        },
    }
    classifier = AnomalyClassifier(events=events)

    normal = classifier.classify("E_TEST_NORMAL")
    assert normal.is_anomaly is False
    assert normal.urgency is None

    error = classifier.classify("E_TEST_ERROR")
    assert error.is_anomaly is True
    assert error.urgency == Urgency.CRITICAL


def test_result_is_anomaly_result_instance() -> None:
    result = classify_anomaly("E1")

    assert isinstance(result, AnomalyResult)
