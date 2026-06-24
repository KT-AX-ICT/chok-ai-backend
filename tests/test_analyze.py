"""
분석 endpoint 흐름 회귀 테스트 — POST /ai/v1/analyze, /analyze/batch

LLM/Tool은 monkeypatch로 대체해 외부(OpenAI) 호출 없이 계약을 검증한다.
검증 대상: camelCase 직렬화·status(정상/이상) 분기·KST 포맷·에러 매핑(422/502/503)·배치 부분 실패.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.core.errors import LLMError, LLMTimeoutError
from app.main import app

client = TestClient(app, raise_server_exceptions=False)

# KST "yyyy-MM-dd HH:mm:ss"
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

# 서비스가 import한 이름 경로 (monkeypatch 대상)
SVC = "app.services.analysis_service"


def make_log(log_id: int = 10293, log_level: str = "FATAL") -> dict:
    return {
        "logId": log_id,
        "node": "R04-M1-N4",
        "nodeRepeat": "R04-M1-N4",
        "component": "APP",
        "logType": "RAS",
        "occurredAt": "2005-06-04 00:24:32",
        "domain": "BGL",
        "logLevel": log_level,
        "content": "ciod: failed to read message prefix on control stream",
    }


async def _fake_diagnosis(*args, **kwargs) -> dict:
    return {
        "summary": "요약",
        "analysis": "분석",
        "action": "대응",
    }


async def _fake_normal_reason(*args, **kwargs) -> dict:
    return {
        "summary": "정상 사유 요약",
        "analysis": "정상 사유 근거",
    }


# ──────────────────────────────────────────────
# 단건 — 이상 경로
# ──────────────────────────────────────────────

def test_analyze_abnormal_success(monkeypatch) -> None:
    monkeypatch.setattr(f"{SVC}.run_diagnosis", _fake_diagnosis)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 200
    body = r.json()

    # 최상위 camelCase 계약
    assert body["logId"] == 10293
    assert body["eventId"]  # Tool① stub
    assert body["isAbnormal"] is True
    assert isinstance(body["processingTimeMs"], int)

    result = body["result"]
    assert result["riskLevel"] == "긴급"          # FATAL → Tool② stub
    assert result["summary"] == "요약"
    assert result["action"] == "대응"
    assert isinstance(result["clusterId"], int)
    assert TS_RE.match(result["analyzedAt"])       # KST 포맷


# ──────────────────────────────────────────────
# 단건 — 정상 경로 (FATAL→정상)
# ──────────────────────────────────────────────

def test_analyze_normal_path(monkeypatch) -> None:
    async def fake_status(log, event_id):
        return "정상", None

    monkeypatch.setattr(f"{SVC}.classify_status_urgency", fake_status)
    monkeypatch.setattr(f"{SVC}.run_normal_reason", _fake_normal_reason)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 200
    body = r.json()

    assert body["isAbnormal"] is False
    result = body["result"]
    assert result["riskLevel"] is None             # 정상 → null
    assert result["clusterId"] is None             # 정상 → null
    assert result["action"] == ""                  # 정상 → ""
    assert result["summary"] == "정상 사유 요약"
    assert TS_RE.match(result["analyzedAt"])


# ──────────────────────────────────────────────
# 단건 — 에러 매핑
# ──────────────────────────────────────────────

def test_analyze_validation_error() -> None:
    r = client.post("/ai/v1/analyze", json={"logId": 1})   # 필수 필드 누락
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_analyze_llm_error_maps_502(monkeypatch) -> None:
    async def boom(*a, **k):
        raise LLMError("호출 실패")

    monkeypatch.setattr(f"{SVC}.run_diagnosis", boom)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 502
    assert r.json()["code"] == "LLM_ERROR"


def test_analyze_llm_timeout_maps_503(monkeypatch) -> None:
    async def slow(*a, **k):
        raise LLMTimeoutError("타임아웃")

    monkeypatch.setattr(f"{SVC}.run_diagnosis", slow)

    r = client.post("/ai/v1/analyze", json=make_log())
    assert r.status_code == 503
    assert r.json()["code"] == "LLM_TIMEOUT"


# ──────────────────────────────────────────────
# 배치 — 부분 실패 격리
# ──────────────────────────────────────────────

def test_batch_partial_failure(monkeypatch) -> None:
    async def diagnosis_by_id(log, *a, **k):
        if log.log_id == 2:
            raise LLMError("이 건만 실패")
        return {"summary": "요약", "analysis": "분석", "action": "대응"}

    monkeypatch.setattr(f"{SVC}.run_diagnosis", diagnosis_by_id)

    payload = {"logs": [make_log(1), make_log(2), make_log(3)]}
    r = client.post("/ai/v1/analyze/batch", json=payload)
    assert r.status_code == 200
    body = r.json()

    assert body["totalCount"] == 3
    by_id = {item["logId"]: item for item in body["results"]}

    assert by_id[1]["processStatus"] == "success"
    assert by_id[1]["isAbnormal"] is True
    assert by_id[1]["result"] is not None

    assert by_id[2]["processStatus"] == "fail"
    assert by_id[2]["error"] == "LLMError"
    assert by_id[2]["result"] is None


def test_batch_empty_is_422() -> None:
    r = client.post("/ai/v1/analyze/batch", json={"logs": []})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("size", [501, 600])
def test_batch_over_limit_is_422(size: int) -> None:
    payload = {"logs": [make_log(i) for i in range(size)]}
    r = client.post("/ai/v1/analyze/batch", json=payload)
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"
