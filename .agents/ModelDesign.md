# DTO·에러 모델 설계

> API의 **내부 구현 설계** 문서. 외부 계약(요청/응답·에러 응답 스키마)은 [API.md](API.md)를 단일 출처로 삼고,
> 이 문서는 그 계약을 구현하는 **Pydantic 모델 구조·필드 정의·검증·에러 처리**를 다룬다.
> 적용 위치: `models/`(DTO·열거형), `core/`(에러·예외), `services/`(LLM 구조화 출력).

---

## 1. 베이스모델 · 공통 타입

### 1-1. 명명 규칙 — 와이어 camelCase ↔ 내부 snake_case

- API 계약 필드는 모두 **camelCase**(`logId`, `nodeRepeat`, `riskLevel`, `analyzedAt` …)다.
- 파이썬 내부 속성은 **snake_case**를 유지한다.
- 둘을 잇기 위해 **공통 베이스모델**에서 `alias_generator`(snake → camel)와 `populate_by_name`을 설정한다.
  요청은 camelCase 별칭으로 받고, 응답은 camelCase 별칭으로 직렬화한다.

```python
# models/base.py
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """모든 요청/응답 DTO의 공통 베이스. 와이어는 camelCase, 내부는 snake_case."""
    model_config = ConfigDict(
        alias_generator=to_camel,   # snake_case 속성 → camelCase 별칭
        populate_by_name=True,      # 속성명·별칭 둘 다로 입력 허용
        extra="ignore",             # 미정의 필드는 무시(상위 시스템 확장에 견고)
    )
```

> 응답은 라우터의 `response_model` 지정 또는 `model_dump(by_alias=True)`로 camelCase 출력을 보장한다.

### 1-2. 공통 타입 (고정 값 집합)

값 집합이 고정된 문자열 필드는 좁은 타입으로 정의해 검증·OpenAPI 문서화를 강화한다.

- **`RiskLevel`은 `Literal` 타입 별칭으로 둔다.** 응답 문자열이 곧 한글 값이라 Enum 클래스가 불필요하다.
- **`is_abnormal`은 `bool`이다.** Spring DB 정의에 맞춰 **이상=`true` / 정상=`false`**. 별도 타입을 두지 않는다.
- **`ProcessStatus`는 Enum으로 둔다.** 멤버명이 값과 1:1이고, 배치 매핑·검증 로직에서 멤버를 참조한다.

```python
# models/enums.py
from enum import Enum
from typing import Literal

# Tool ②가 산출. 응답 result.riskLevel 값.
RiskLevel = Literal["긴급", "높음", "보통", "낮음"]

# is_abnormal(이상 여부)는 bool — 이상=True / 정상=False (Spring DB 정의). 별도 타입 불필요.


class ProcessStatus(str, Enum):   # 배치 항목의 "처리 완료 여부" (이상 여부와 별개)
    SUCCESS = "success"
    FAIL = "fail"
```

| 타입 | 값 | 산출 |
|------|-----|------|
| `RiskLevel` | `긴급` / `높음` / `보통` / `낮음` | Tool ② |
| `is_abnormal` (bool) | `true`=이상 / `false`=정상 | Tool ② |
| `ProcessStatus` | `success` / `fail` | 배치 처리 완료 여부 |

> `RiskLevel`·`is_abnormal`은 **Tool ②가 산출**하여 응답(`result.riskLevel`, `isAbnormal`)을 만들고 LLM 컨텍스트로도 주입된다. `is_abnormal`은 Spring DB와 동일하게 **이상=`true` / 정상=`false`** 불리언이다.
> `ProcessStatus`(success/fail)는 "이상 여부(`is_abnormal`)"와 **다른 개념** — 배치 항목의 처리 성공/실패를 가리킨다(2-5).

> `logLevel`·`logType`은 현재 자유 문자열로 둔다. 값 집합이 확정되면 `RiskLevel`처럼 `Literal`(또는 Enum)로 좁힌다(4장 확장 포인트). (`domain`은 BGL 고정 요청 입력이라 해당 없음)

---

## 2. DTO 상세 정의

> 필드 표의 **속성**은 파이썬 snake_case, **별칭**은 와이어 camelCase다. 타입은 파이썬 타입 기준.

### 2-1. 단건 요청 — `LogAnalyzeRequest` (통과형 / passthrough)

1차 필터(FATAL)를 거친 로그의 식별자·메타·원문. `label`·`eventId`는 **받지 않는다**([API.md 5.1](API.md)).

**설계 방침 — 변환·파싱하지 않는다.** 요청 값은 거의 그대로 Tool/LLM으로 전달되므로 모델은 *통과형*으로 둔다.
- 모든 메타·원문 필드는 **문자열 그대로** 보관한다. `occurredAt`도 `datetime`으로 파싱하지 않는다.
- 타입 강제 변환·범위 제약 등 부가 검증은 두지 않고, FastAPI가 **요청 형태(필드 존재·기본 타입)만 검증**하게 한다.
- 그럼에도 모델을 두는 이유: ① FastAPI의 **OpenAPI 계약** 자동 생성(Spring 연동), ② Tool들이 **필드를 이름으로 접근**(Tool④ `node`, Tool② `log_level`/`content` 등).

```python
# models/analyze.py
from .base import CamelModel


class LogAnalyzeRequest(CamelModel):
    log_id: int
    node: str
    node_repeat: str
    component: str
    log_type: str
    occurred_at: str   # "yyyy-MM-dd HH:mm:ss" 문자열 — datetime 파싱하지 않음
    log_level: str
    content: str
    domain: str        # BGL 고정값 (요청 입력, 응답에는 없음)
```

| 속성 | 별칭 | 타입 | 필수 | 설명 |
|------|------|------|:---:|------|
| log_id | logId | int | ✔ | 로그 식별자 |
| node | node | str | ✔ | 노드 |
| node_repeat | nodeRepeat | str | ✔ | 노드 반복 정보 |
| component | component | str | ✔ | 컴포넌트 |
| log_type | logType | str | ✔ | 로그 타입 |
| occurred_at | occurredAt | str | ✔ | 로그 발생 시각 — `yyyy-MM-dd HH:mm:ss` 형식 문자열 (파싱 없이 그대로 수신) |
| log_level | logLevel | str | ✔ | 로그 레벨 |
| content | content | str | ✔ | 로그 내용 |
| domain | domain | str | ✔ | 도메인 — **BGL 고정값** (요청 입력, 응답 미포함) |

### 2-2. 분석 결과 본문 — `AnalysisResult`

단건·배치가 **동일한 결과 본문**을 공유하며, **정상·이상 모두 `result`를 채운다.**
정상이면 `summary`·`analysis`에 **정상 사유**만 담고, 나머지는 빈값으로 둔다 — 문자열 필드(`action`)는 `""`, 이상 전용 필드(`eventId`·`riskLevel`·`clusterId`)는 `null`. `analyzedAt`은 공통.
> `eventId`는 **이상 로그에 대해서만 분류**되므로 `result` 안에 둔다(정상이면 `null`).
> `domain`은 **BGL 고정 요청 입력**이므로 결과 본문(응답)에는 포함하지 않는다.

```python
from datetime import datetime
from pydantic import Field, field_serializer
from .enums import RiskLevel

_TS_FMT = "%Y-%m-%d %H:%M:%S"


class AnalysisResult(CamelModel):
    event_id: str | None = None                    # 이상: 이벤트 ID / 정상: null (이상 로그만 분류)
    risk_level: RiskLevel | None = None            # 이상: 위험도 / 정상: null (Literal이라 "" 불가)
    summary: str                                   # 공통 — 정상이면 정상 사유
    analysis: str                                  # 공통 — 정상이면 정상 사유
    action: str                                    # 이상: 대응 방안 / 정상: "" (빈 문자열)
    cluster_id: int | None = Field(default=None, ge=0)  # 이상: 클러스터 / 정상: null
    analyzed_at: datetime                          # 공통, 판정/분석 시각

    @field_serializer("analyzed_at")
    def _fmt_analyzed_at(self, v: datetime) -> str:
        return v.strftime(_TS_FMT)   # "yyyy-MM-dd HH:mm:ss"
```

| 속성 | 별칭 | 타입 | 이상 | 정상 | 산출 |
|------|------|------|------|------|------|
| event_id | eventId | str \| None | 이벤트 식별자 | `null` | Tool ① |
| risk_level | riskLevel | `RiskLevel` \| None | 위험도 | `null` | Tool ② |
| summary | summary | str | 분석 요약 | 정상 사유 | LLM |
| analysis | analysis | str | 분석 내용 | 정상 사유 | LLM |
| action | action | str | 대응 방안 | `""` | LLM |
| cluster_id | clusterId | int \| None | 클러스터 식별자 | `null` | Tool ③ |
| analyzed_at | analyzedAt | datetime | 분석 시각 | 판정 시각 | 결과 매핑 (`yyyy-MM-dd HH:mm:ss` 직렬화) |

### 2-3. 단건 응답 — `LogAnalyzeResponse`

단건은 처리 실패 시 부분 응답이 아니라 **에러 응답**(§3)으로 떨어지므로, 성공 응답에는 `is_abnormal`·`result`가 항상 있다.
`is_abnormal`(이상=true/정상=false)에 따라 `result` 내부 필드 구성만 달라진다(2-2).

```python
from pydantic import Field


class LogAnalyzeResponse(CamelModel):
    log_id: int
    is_abnormal: bool           # 이상=True / 정상=False (Tool ②, Spring DB 정의)
    result: AnalysisResult      # eventId 포함. 항상 포함 (정상이면 일부 필드 빈값 — 2-2)
    processing_time_ms: int = Field(ge=0)
```

| 속성 | 별칭 | 타입 | 필수 | 산출 |
|------|------|------|:---:|------|
| log_id | logId | int | ✔ | 요청 echo |
| is_abnormal | isAbnormal | bool | ✔ | Tool ② (이상=true/정상=false) |
| result | result | `AnalysisResult` | ✔ | 결과 매핑 (`eventId` 포함; 정상이면 일부 필드 빈값) |
| processing_time_ms | processingTimeMs | int | ✔ | 측정 (`ge=0`) |

### 2-4. 다건 요청 — `LogBatchAnalyzeRequest`

```python
class LogBatchAnalyzeRequest(CamelModel):
    logs: list[LogAnalyzeRequest] = Field(min_length=1)
```

| 속성 | 별칭 | 타입 | 필수 | 제약/설명 |
|------|------|------|:---:|-----------|
| logs | logs | list[`LogAnalyzeRequest`] | ✔ | 최소 1건. 원소는 단건 요청 모델 재사용 |

### 2-5. 다건 응답 — `LogBatchResultItem` / `LogBatchAnalyzeResponse`

항목은 **두 개념을 구분**한다 — `processStatus`(처리 완료 여부, success/fail)와 `is_abnormal`(이상 여부, `true`=이상/`false`=정상).
- `processStatus="fail"` → `errorMessage`만 채우고 `is_abnormal`·`result`는 null.
- `processStatus="success"` → `is_abnormal`(이상=true/정상=false)와 `result`(eventId 포함)를 **모두 채운다.** 정상(false)이면 `result`의 일부 필드만 채워진다(2-2).

```python
from pydantic import Field, model_validator
from .enums import ProcessStatus


class LogBatchResultItem(CamelModel):
    log_id: int
    process_status: ProcessStatus          # 처리 완료 여부 (success/fail)
    is_abnormal: bool | None = None        # 이상 여부 (이상=True/정상=False). 처리 실패 시 null
    result: AnalysisResult | None = None    # 성공 시 채움(eventId 포함, 정상이면 일부 필드만). 처리 실패 시 null
    error_message: str | None = None        # 처리 실패 시 사유 (alias: errorMessage)

    @model_validator(mode="after")
    def _check(self):
        if self.process_status is ProcessStatus.FAIL:
            if self.error_message is None:
                raise ValueError("fail 항목은 errorMessage가 필요합니다")
        else:  # success
            if self.is_abnormal is None:
                raise ValueError("success 항목은 isAbnormal(이상 여부)가 필요합니다")
            if self.result is None:
                raise ValueError("success 항목은 result가 필요합니다")
        return self


class LogBatchAnalyzeResponse(CamelModel):
    total_count: int = Field(ge=0)
    processing_time_ms: int = Field(ge=0)
    results: list[LogBatchResultItem]
```

| 모델 | 속성 | 별칭 | 타입 | 필수 | 설명 |
|------|------|------|------|:---:|------|
| `LogBatchResultItem` | log_id | logId | int | ✔ | 로그 식별자 |
| | process_status | processStatus | `ProcessStatus` | ✔ | 처리 완료 여부 (success/fail) |
| | is_abnormal | isAbnormal | bool \| None | 성공 시 | 이상 여부 (이상=true/정상=false). 실패 시 null |
| | result | result | `AnalysisResult` \| None | 성공 시 | 본문(`eventId` 포함, 정상이면 일부 필드만). 처리 실패 시 null |
| | error_message | errorMessage | str \| None | 실패 시 | 실패 사유 메시지 |
| `LogBatchAnalyzeResponse` | total_count | totalCount | int | ✔ | 처리 총 개수 (`ge=0`) |
| | processing_time_ms | processingTimeMs | int | ✔ | 전체 소요(ms, `ge=0`) |
| | results | results | list[`LogBatchResultItem`] | ✔ | 로그별 결과 |

### 2-6. 에러 응답 — `ErrorResponse`

```python
class ErrorResponse(CamelModel):
    code: str
    message: str
    detail: str | None = None
```

| 속성 | 별칭 | 타입 | 필수 | 설명 |
|------|------|------|:---:|------|
| code | code | str | ✔ | 에러 코드([API.md 6](API.md)) |
| message | message | str | ✔ | 사람이 읽는 설명 |
| detail | detail | str \| None | | 추가 상세(디버깅용) |

### 2-7. LLM 구조화 출력 모델 — `LLMAnalysis` (내부 전용)

LLM이 산출하는 값만 담는 **내부 모델**. 외부 DTO와 분리해 `services/`에 둔다.
`risk_level`(Tool ②)·`cluster_id`(Tool ③)·`event_id`(Tool ①)·`domain`(BGL 고정·요청 입력)은 **LLM이 만들지 않으므로 포함하지 않는다.**

```python
# services/llm_schema.py
from pydantic import BaseModel  # 외부 노출 없음 → CamelModel 불필요


class LLMAnalysis(BaseModel):
    summary: str
    analysis: str
    action: str
    reason: str        # 사람이 읽을 근거 (시스템 프롬프트상 필수). 응답 미노출 — 로깅/검증용
```

> `with_structured_output(LLMAnalysis)`로 수신한다. **결과 매핑 단계**에서 `LLMAnalysis` + `event_id`(Tool ①) + `risk_level` + `cluster_id` + `analyzed_at`을 합쳐 `AnalysisResult`(단건·배치 공통)로 변환한다. `reason`은 응답에 싣지 않는다.
> 단, **`is_abnormal`이 정상(`false`)이면 전체 분석 대신 정상 사유만** 생성하여 `summary`·`analysis`에 담고, `action`은 `""`, `riskLevel`·`clusterId`는 `null`로 둔다(2-2). `result` 자체는 정상·이상 모두 채워진다.

---

## 3. 에러 처리 설계

### 3-1. 예외 계층

도메인 예외를 한 뿌리(`AppError`)에서 파생시키고, 각 예외가 **HTTP 상태·에러 코드**를 들고 있게 한다.

```python
# core/errors.py
class AppError(Exception):
    """애플리케이션 공통 예외. status_code / code / message 보유."""
    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: str | None = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class LLMTimeoutError(AppError):
    status_code = 503
    code = "LLM_TIMEOUT"


class LLMError(AppError):          # 호출 실패 + 구조화 출력 파싱 실패
    status_code = 502
    code = "LLM_ERROR"
```

> 요청 스키마 검증 실패(`VALIDATION_ERROR`, 422)는 FastAPI/Pydantic이 자동 발생시키므로 별도 예외를 정의하지 않고, **핸들러에서 공통 포맷으로 변환**만 한다.

### 3-2. 예외 → 응답 매핑

전역 예외 핸들러에서 모든 예외를 [API.md 6](API.md)의 `ErrorResponse` 스키마로 변환한다.

| 예외 | HTTP | code | 변환 위치 |
|------|------|------|-----------|
| `RequestValidationError` (FastAPI) | 422 | `VALIDATION_ERROR` | `validation_exception_handler` |
| `LLMTimeoutError` | 503 | `LLM_TIMEOUT` | `AppError` 핸들러 |
| `LLMError` | 502 | `LLM_ERROR` | `AppError` 핸들러 |
| `AppError`(기타)·미분류 `Exception` | 500 | `INTERNAL_ERROR` | `AppError`/전역 핸들러 |

### 3-3. 배치의 부분 실패

- 배치 요청에서 **개별 로그 실패는 전체 실패가 아니다.** `asyncio.gather(..., return_exceptions=True)`로 수집한 뒤,
  성공 → `processStatus="success"` + `is_abnormal`(이상=true/정상=false) + `result`(정상이면 일부 필드만), 실패 → `processStatus="fail"` + `errorMessage`(예외 메시지)로 항목별 매핑한다.
- 따라서 개별 실패는 `ErrorResponse`(공통 에러)가 아니라 `LogBatchResultItem.errorMessage`로 표현된다([API.md 5.2](API.md)).
- 요청 자체가 깨진 경우(스키마 검증 실패 등)에만 전체 요청이 `ErrorResponse`로 떨어진다.

---

## 4. 확장 포인트

- **고정 값 타입 확장:** `logLevel`·`logType` 값 집합이 확정되면 `RiskLevel`처럼 `Literal`(또는 Enum)로 좁힌다.
- **clusterId 미할당:** 클러스터가 없을 때의 표현(`null` 허용 vs `-1`/`0` 센티넬)을 Tool ③ 정책 확정 후 결정한다.
- **에러 코드 카탈로그:** 현재 표는 시작점이다. 이벤트 템플릿 매칭 실패, 내부 정의 문서 로드 실패(`CONFIG_ERROR` 등) 등 도메인 오류가 정해지면 코드·상태를 추가한다.
- **occurredAt 타입:** 현재 원문 문자열 수신. 포맷이 표준화되면 `datetime` 파싱으로 승격을 검토한다.
