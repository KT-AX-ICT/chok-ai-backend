"""
분석 요청/응답 DTO — Spring Boot ↔ FastAPI 계약
API.md / ModelDesign.md 기준

[계약 원칙]
1. 들어오는 로그는 FATAL 1차 필터만 통과한 상태 → 정상/이상 판정을 AI가 직접 수행
2. event_id(Tool①)·status·risk_level(Tool②)·cluster_id(Tool③)는 결정적 Tool 산출
   → LLM이 재판단하지 않음
3. LLM은 summary/analysis/action 텍스트만 작성
4. 와이어는 camelCase, 내부 속성은 snake_case (CamelModel)
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    model_validator,
)
from pydantic.alias_generators import to_camel

# analyzed_at 직렬화 포맷 — KST, Spring 기준 (yyyy-MM-dd HH:mm:ss)
_TS_FMT = "%Y-%m-%d %H:%M:%S"


# ──────────────────────────────────────────────
# 공통 베이스 / 타입
# ──────────────────────────────────────────────

class CamelModel(BaseModel):
    """모든 요청/응답 DTO의 공통 베이스. 와이어 camelCase ↔ 내부 snake_case."""

    model_config = ConfigDict(
        alias_generator=to_camel,   # snake_case 속성 → camelCase 별칭
        populate_by_name=True,      # 속성명·별칭 둘 다로 입력 허용
        extra="ignore",             # 미정의 필드는 무시 (상위 시스템 확장에 견고)
    )


# Tool②가 산출. 응답 result.risk_level / status 값. 값이 곧 클라이언트 수신 문자열이라 한글 고정.
RiskLevel = Literal["긴급", "높음", "보통", "낮음"]
LogStatus = Literal["정상", "이상"]


class ProcessStatus(str, Enum):
    """배치 항목의 '처리 완료 여부' — 로그 판정(정상/이상)과는 별개 개념."""

    SUCCESS = "success"
    FAIL = "fail"


# ──────────────────────────────────────────────
# 요청 DTO — Spring Boot → FastAPI  (통과형 / passthrough)
# 1차 필터(FATAL)를 거친 로그의 식별자·메타·원문. label·event_id는 받지 않음.
# ──────────────────────────────────────────────

class AnalyzeRequest(CamelModel):
    """단건 분석 요청 — 값을 파싱·변환하지 않고 그대로 Tool/LLM에 전달."""

    log_id: int = Field(..., examples=[10293])
    node: str = Field(..., examples=["R04-M1-N4-I:J18-U11"])
    node_repeat: str = Field(..., examples=["R04-M1-N4-I:J18-U11"])
    component: str = Field(..., examples=["APP"])
    log_type: str = Field(..., examples=["RAS"])
    # "yyyy-MM-dd HH:mm:ss" 문자열 — datetime 파싱하지 않음 (통과형)
    log_ts: str = Field(..., examples=["2005-06-04 00:24:32"])
    log_level: str = Field(..., examples=["FATAL"])
    content: str = Field(
        ...,
        examples=["ciod: failed to read message prefix on control stream"],
    )


class BatchAnalyzeRequest(CamelModel):
    """다건 분석 요청 — 스케줄러 기본 경로. 최대 500건(초과 시 422)."""

    logs: list[AnalyzeRequest] = Field(..., min_length=1, max_length=500)


# ──────────────────────────────────────────────
# 분석 결과 본문 — 단건·배치 공통
# 정상·이상 모두 채움. 정상이면 summary·analysis(정상 사유)만, 나머지는 빈값.
# ──────────────────────────────────────────────

class AnalyzeResult(CamelModel):
    """분석 결과 본문 (log_analysis 한 행에 매핑)."""

    domain: str                                          # 이상: 도메인 / 정상: ""
    risk_level: RiskLevel | None = None                  # 이상: 위험도 / 정상: null
    summary: str                                         # 공통 — 정상이면 정상 사유
    analysis: str                                        # 공통 — 정상이면 정상 사유
    action: str                                          # 이상: 대응 방안 / 정상: ""
    cluster_id: int | None = Field(default=None, ge=0)   # 이상: 클러스터 / 정상: null
    analyzed_at: datetime                                # 공통 — 판정/분석 시각

    @field_serializer("analyzed_at")
    def _fmt_analyzed_at(self, v: datetime) -> str:
        return v.strftime(_TS_FMT)   # KST "yyyy-MM-dd HH:mm:ss"


# ──────────────────────────────────────────────
# 응답 DTO — 단건  (POST /ai/v1/analyze)
# ──────────────────────────────────────────────

class AnalyzeResponse(CamelModel):
    """단건 응답 — 처리 실패는 에러 응답(ErrorResponse)으로 떨어지므로 항상 status·result 존재."""

    log_id: int
    event_id: str                            # Tool①
    status: LogStatus                        # Tool② (정상/이상)
    result: AnalyzeResult                    # 항상 포함 (정상이면 일부 필드 빈값)
    processing_time_ms: int = Field(..., ge=0)


# ──────────────────────────────────────────────
# 응답 DTO — 배치  (POST /ai/v1/analyze/batch)
# processStatus(처리 완료 여부) 와 status(로그 판정) 두 개념을 구분.
# ──────────────────────────────────────────────

class BatchItemResult(CamelModel):
    """배치 내 개별 항목 결과 — 개별 실패가 전체 배치를 막지 않음."""

    log_id: int
    event_id: str | None = None              # Tool① 산출. 처리 실패 시 null
    process_status: ProcessStatus            # 처리 완료 여부 (success/fail)
    status: LogStatus | None = None          # 로그 판정 (정상/이상). 처리 실패 시 null
    result: AnalyzeResult | None = None      # 성공 시 채움. 처리 실패 시 null
    error: str | None = None                 # 처리 실패 시 사유

    @model_validator(mode="after")
    def _check(self):
        if self.process_status is ProcessStatus.FAIL:
            if self.error is None:
                raise ValueError("fail 항목은 error가 필요합니다")
        else:  # success
            if self.status is None:
                raise ValueError("success 항목은 status(정상/이상)가 필요합니다")
            if self.result is None:
                raise ValueError("success 항목은 result가 필요합니다")
        return self


class BatchAnalyzeResponse(CamelModel):
    """배치 응답."""

    total_count: int = Field(..., ge=0)
    processing_time_ms: int = Field(..., ge=0)
    results: list[BatchItemResult]


# ──────────────────────────────────────────────
# 공통 에러 응답  (API.md §6)
# ──────────────────────────────────────────────

class ErrorResponse(CamelModel):
    """요청 자체 실패 시 공통 에러 스키마 (배치 개별 실패는 BatchItemResult.error로 표현)."""

    code: str = Field(..., examples=["VALIDATION_ERROR"])
    message: str = Field(..., examples=["요청 스키마 검증 실패"])
    detail: str | None = None
