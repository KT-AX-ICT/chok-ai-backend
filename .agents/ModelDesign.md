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

- **`RiskLevel`은 `Literal` 타입 별칭으로 둔다.** 응답 문자열이 곧 한글 값이고 영문 멤버명↔한글 값 매핑이 불필요하므로, Enum 클래스를 만들지 않는다.
- **`BatchItemStatus`는 Enum으로 둔다.** 멤버명이 값과 1:1이라 군더더기가 없고, 배치 매핑·검증 로직에서 멤버를 참조한다.

```python
# models/enums.py
from enum import Enum
from typing import Literal

# 응답 문자열 그대로. Tool ②가 이 중 하나를 산출.
RiskLevel = Literal["긴급", "높음", "보통", "낮음"]


class BatchItemStatus(str, Enum):
    SUCCESS = "success"
    FAIL = "fail"
```

| 타입 | 값(응답 문자열) | 산출 |
|------|-----|------|
| `RiskLevel` | `긴급` / `높음` / `보통` / `낮음` | Tool ② |
| `BatchItemStatus` | `success` / `fail` | 배치 처리 결과 |

> `RiskLevel`은 **Tool ②가 산출**하여 응답 `result.riskLevel`을 만들 때 쓰이고, 동시에 LLM 프롬프트 컨텍스트로도 주입된다. 값이 곧 클라이언트가 받는 문자열이라 **한글**로 고정한다.
> 검증조차 불필요하면 plain `str`로 둬도 된다(통과형 선호 시) — 다만 그 경우 허용 값은 [API.md](API.md) 문서로만 보장된다.

> `logLevel`·`logType`·`domain`은 현재 자유 문자열로 둔다. 값 집합이 확정되면 동일 방식으로 Enum화한다(3장 확장 포인트).

---

## 2. DTO 상세 정의

> 필드 표의 **속성**은 파이썬 snake_case, **별칭**은 와이어 camelCase다. 타입은 파이썬 타입 기준.

### 2-1. 단건 요청 — `LogAnalyzeRequest` (통과형 / passthrough)

1차 필터(FATAL)를 거친 로그의 식별자·메타·원문. `label`·`eventId`는 **받지 않는다**([API.md 5.1](API.md)).

**설계 방침 — 변환·파싱하지 않는다.** 요청 값은 거의 그대로 Tool/LLM으로 전달되므로 모델은 *통과형*으로 둔다.
- 모든 메타·원문 필드는 **문자열 그대로** 보관한다. `logTs`도 `datetime`으로 파싱하지 않는다.
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
    log_ts: str        # 원문 문자열 그대로 — datetime 파싱하지 않음
    log_level: str
    content: str
```

| 속성 | 별칭 | 타입 | 필수 | 설명 |
|------|------|------|:---:|------|
| log_id | logId | int | ✔ | 로그 식별자 |
| node | node | str | ✔ | 노드 |
| node_repeat | nodeRepeat | str | ✔ | 노드 반복 정보 |
| component | component | str | ✔ | 컴포넌트 |
| log_type | logType | str | ✔ | 로그 타입 |
| log_ts | logTs | str | ✔ | 로그 타임스탬프(원문 문자열 그대로 수신) |
| log_level | logLevel | str | ✔ | 로그 레벨 |
| content | content | str | ✔ | 로그 내용 |

### 2-2. 분석 결과 본문 — `AnalysisResultBase` / `LogAnalyzeResult`

단건·다건이 결과 본문을 공유하되, **`analyzedAt`은 단건에만** 존재한다([API.md](API.md) 계약 차이). 공통 필드를 베이스로 분리한다.

```python
from datetime import datetime
from .enums import RiskLevel


class AnalysisResultBase(CamelModel):
    domain: str
    risk_level: RiskLevel
    summary: str
    analysis: str
    action: str
    cluster_id: int = Field(ge=0)


class LogAnalyzeResult(AnalysisResultBase):
    analyzed_at: datetime          # 직렬화 시 ISO 8601
```

| 속성 | 별칭 | 타입 | 단건 | 다건 | 산출 |
|------|------|------|:---:|:---:|------|
| domain | domain | str | ✔ | ✔ | LLM 분석 |
| risk_level | riskLevel | `RiskLevel` | ✔ | ✔ | Tool ② |
| summary | summary | str | ✔ | ✔ | LLM 분석 |
| analysis | analysis | str | ✔ | ✔ | LLM 분석 |
| action | action | str | ✔ | ✔ | LLM 분석 |
| cluster_id | clusterId | int | ✔ | ✔ | Tool ③ (`ge=0`) |
| analyzed_at | analyzedAt | datetime | ✔ | ✗ | 결과 매핑 (단건 전용) |

### 2-3. 단건 응답 — `LogAnalyzeResponse`

```python
class LogAnalyzeResponse(CamelModel):
    log_id: int
    event_id: str
    result: LogAnalyzeResult
    processing_time_ms: int = Field(ge=0)
```

| 속성 | 별칭 | 타입 | 필수 | 산출 |
|------|------|------|:---:|------|
| log_id | logId | int | ✔ | 요청 echo |
| event_id | eventId | str | ✔ | Tool ① |
| result | result | `LogAnalyzeResult` | ✔ | 결과 매핑 |
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

항목은 `status`에 따라 `result`(성공) **또는** `error`(실패) 중 하나만 채운다. 둘의 **상호 배타성**을 검증한다.

```python
from pydantic import model_validator
from .enums import BatchItemStatus


class LogBatchResultItem(CamelModel):
    log_id: int
    event_id: str | None = None        # 템플릿 분류 전 실패 시 None 허용
    status: BatchItemStatus
    result: AnalysisResultBase | None = None   # analyzedAt 없음 (계약상 다건 본문)
    error: str | None = None

    @model_validator(mode="after")
    def _check_exclusive(self):
        if self.status is BatchItemStatus.SUCCESS and self.result is None:
            raise ValueError("success 항목은 result가 필요합니다")
        if self.status is BatchItemStatus.FAIL and self.error is None:
            raise ValueError("fail 항목은 error가 필요합니다")
        return self


class LogBatchAnalyzeResponse(CamelModel):
    total_count: int = Field(ge=0)
    processing_time_ms: int = Field(ge=0)
    results: list[LogBatchResultItem]
```

| 모델 | 속성 | 별칭 | 타입 | 필수 | 설명 |
|------|------|------|------|:---:|------|
| `LogBatchResultItem` | log_id | logId | int | ✔ | 로그 식별자 |
| | event_id | eventId | str \| None | ✔* | Tool ① 산출. 분류 전 실패 시 null |
| | status | status | `BatchItemStatus` | ✔ | success / fail |
| | result | result | `AnalysisResultBase` \| None | 성공 시 | 성공 항목 본문 (analyzedAt 제외) |
| | error | error | str \| None | 실패 시 | 실패 사유 메시지 |
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
`risk_level`(Tool ②)·`cluster_id`(Tool ③)·`event_id`(Tool ①)는 **LLM이 만들지 않으므로 포함하지 않는다.**

```python
# services/llm_schema.py
from pydantic import BaseModel  # 외부 노출 없음 → CamelModel 불필요


class LLMAnalysis(BaseModel):
    domain: str
    summary: str
    analysis: str
    action: str
    reason: str        # 사람이 읽을 근거 (시스템 프롬프트상 필수). 응답 미노출 — 로깅/검증용
```

> `with_structured_output(LLMAnalysis)`로 수신한다. **결과 매핑 단계**에서 `LLMAnalysis` + `risk_level` + `cluster_id` + `analyzed_at`을 합쳐 `LogAnalyzeResult`(단건) 또는 `AnalysisResultBase`(다건)로 변환한다. `reason`은 응답에 싣지 않는다.

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
  성공 → `status="success"` + `result`, 실패 → `status="fail"` + `error`(예외 `message`)로 항목별 매핑한다.
- 따라서 개별 실패는 `ErrorResponse`(공통 에러)가 아니라 `LogBatchResultItem.error`로 표현된다([API.md 5.2](API.md)).
- 요청 자체가 깨진 경우(스키마 검증 실패 등)에만 전체 요청이 `ErrorResponse`로 떨어진다.

---

## 4. 확장 포인트

- **Enum 확장:** `logLevel`·`logType`·`domain` 값 집합이 확정되면 `RiskLevel`과 동일하게 Enum화한다.
- **clusterId 미할당:** 클러스터가 없을 때의 표현(`null` 허용 vs `-1`/`0` 센티넬)을 Tool ③ 정책 확정 후 결정한다.
- **에러 코드 카탈로그:** 현재 표는 시작점이다. 이벤트 템플릿 매칭 실패, 내부 정의 문서 로드 실패(`CONFIG_ERROR` 등) 등 도메인 오류가 정해지면 코드·상태를 추가한다.
- **logTs 타입:** 현재 원문 문자열 수신. 포맷이 표준화되면 `datetime` 파싱으로 승격을 검토한다.
