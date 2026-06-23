# 로그 분석 서비스 API 명세서 — FastAPI ↔ Spring 연동

## 1. 개요

- FastAPI는 로그를 분석하는 역할만 담당하고, RDBMS 관리는 Spring이 전담
- Spring은 `level='FATAL'`이면서 아직 `log_analysis`가 없는 로그만 모아 FastAPI로 보냄 (FATAL 1차 필터)
- `status`는 FastAPI에서 이상/정상 로그 판단한 결과. (`true` = 이상 로그 / `false` = 정상 로그)
- 분석 컨텍스트는 **4개 Tool**이 산출
— ① 이벤트 템플릿 분류
— ② 이상 여부 판단 + 긴급도 분류
— ③ 클러스터(패턴) 분류
— ④ Node 정보 조회 Tool
- Tool이 도출한 결과는 LLM이 다시 판단하지 않고 그대로 응답에 실으며, LLM은 그 값들을 맥락으로 받아 `summary`/`analysis`/`action` 텍스트만 작성
- `domain`은 **BGL 고정값**으로 **요청에만** 포함되고 응답에는 싣지 않음
- **[참고] Agent 구성도**
    
    !agent_architecture_v3.png
    

## 2. 공통 사항

Base URL은 `/ai/v1`, `Content-Type`은 `application/json`, 시각 필드는 `yyyy-MM-dd HH:mm:ss` 형식 문자열. 인증 방식은 미정(보류).

## 3. 엔드포인트 요약

| Method | URI | Parameter | 설명 |
| --- | --- | --- | --- |
| POST | `/ai/v1/analyze` | - | 로그 1건 분석 (수동 / 개별 재처리용) |
| POST | `/ai/v1/analyze/batch` | - | 로그 다건 분석 (스케줄러 기본 경로) |

---

### 1) POST `/ai/v1/analyze` — 로그 1건 분석

수동 또는 개별 재처리 용도로 로그 한 건을 분석합니다.

### Request

```json
{
  "logId": 0,
  "node": "string",
  "nodeRepeat": "string",
  "component": "string",
  "logType": "string",
  "logTs": "string",
  "logLevel": "string",
  "content": "string",
  "domain": "string"
}
```

| 필드 | 타입 | 설명 | 부가설명 (예시) |
| --- | --- | --- | --- |
| logId | int | 로그 식별자 | DB에서 부여된 값 |
| node | str | 로그 발생 노드 | R02-M1-N0-C:J12-U11 |
| nodeRepeat | str | 로그 전달 노드 | R02-M1-N0-C:J12-U11 |
| component | str | 컴포넌트 | KERNEL, APP, … |
| logType | str | 로그 타입 | RAS, … |
| logTs | str | 로그 타임스탬프 (`yyyy-MM-dd HH:mm:ss` 형식 문자열) |  |
| logLevel | str | 로그 레벨 | FATAL, ERROR, … |
| content | str | 로그 내용 |  |
| domain | str | 도메인 | **BGL 고정값** (요청 입력, 응답 미포함) |

### Response

- `result`는 정상·이상인 경우 모두 포함.
- **`정상`이면** `summary`·`analysis`에 정상 사유만 담기고, `action`은 `""`, `eventId`·`riskLevel`·`clusterId`는 `null`
- 아래 예시는 **`이상`**인 경우

```json
{
  "logId": 0,
  "status": true | false,
  "result": {
    "eventId": "string",
    "riskLevel": "string",
    "summary": "string",
    "analysis": "string",
    "action": "string",
    "clusterId": 0,
    "analyzedAt": "yyyy-MM-dd HH:mm:ss"
  },
  "processingTimeMs": 0
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| logId | int | 분석 대상 로그 식별자 |
| status | bool | 이상 여부 (`true`=이상 / `false`=정상) |
| result | object | 분석 결과 (정상·이상 모두 포함) |
| result.eventId | str | null | 이벤트 식별자 (`정상`이면 `null`) |
| result.riskLevel | str | null | 위험도 (`긴급` / `높음` / `보통` / `낮음`). `정상`이면 `null` |
| result.summary | str | 요약 — `정상`이면 정상 사유 |
| result.analysis | str | 분석 내용 — `정상`이면 정상 사유 |
| result.action | str | 대응 방안 (`정상`이면 `""`) |
| result.clusterId | int | null | 클러스터 식별자 (`정상`이면 `null`) |
| result.analyzedAt | str | 분석/판정 시각 (`yyyy-MM-dd HH:mm:ss` 문자열) |
| processingTimeMs | int | 처리 소요 시간 (ms) |

---

### 2) POST `/ai/v1/analyze/batch` — 로그 다건 분석

- 스케줄러 기본 경로, 여러 로그를 한 번에 분석
- 개별 로그 실패가 전체 배치를 막지 않음
- 아래 필드명 구분 필요
    - **`processStatus`**(처리 완료 여부, `success`/`fail`)
    - **`status`**(이상 로그 여부, `true`/`false`)
- 조건에 따라 반환 필드 달라짐
    - 처리 실패면 `errorMessage`만 반환
    - 성공 - 이상 로그면 `status`와 `result`(`eventId` 포함) 반환
    - 성공 - 정상 로그면 `result` 일부 필드만 반환

### Request

```json
{
  "logs": [
    {
      "logId": 0,
      "node": "string",
      "nodeRepeat": "string",
      "component": "string",
      "logType": "string",
      "logTs": "string",
      "logLevel": "string",
      "content": "string",
      "domain": "string"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| logs | array | 분석할 로그 객체 배열 (각 객체 필드는 단건 분석 Request와 동일, `domain` 포함) |

### Response

```json
{
  "totalCount": 0,
  "processingTimeMs": 0,
  "results": [
    {
      "logId": 0,
      "processStatus": "success",
      "status": true | false,
      "result": {
        "eventId": "string",
        "riskLevel": "string",
        "summary": "string",
        "analysis": "string",
        "action": "string",
        "clusterId": 0,
        "analyzedAt": "yyyy-MM-dd HH:mm:ss"
      }
    },
    {
      "logId": 0,
      "processStatus": "fail",
      "errorMessage": "string"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| totalCount | int | 처리한 로그 총 개수 |
| processingTimeMs | int | 전체 처리 소요 시간 (ms) |
| results | array | 로그별 분석 결과 배열 |
| results[].logId | int | 로그 식별자 |
| results[].processStatus | str | 처리 완료 여부 (`success` / `fail`) |
| results[].status | bool | null | 이상 여부 (`true`=이상 / `false`=정상). 처리 실패 시 null |
| results[].result | object | null | • 성공·`이상`이면 분석 결과 (eventId, riskLevel, summary, analysis, action, clusterId, analyzedAt)<br>• 성공·`정상`이면 일부 필드만(summary·analysis; eventId·riskLevel·clusterId는 null)<br>• 처리 실패 시 null |
| results[].errorMessage | str | 처리 실패 시 오류 메시지 |

---

## 4. 에러 응답

- **요청 처리가 전체 실패**하면 HTTP 4xx/5xx 상태코드와 함께 아래 공통 에러 스키마로 응답
- 배치의 **개별 로그 실패**는 전체 실패가 아니라 HTTP 200 + 항목별 `processStatus="fail"`로 표현

### 공통 에러 스키마

```json
{
  "code": "string",
  "message": "string",
  "detail": "string"
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| code | str | 에러 코드 (아래 표) |
| message | str | 사람이 읽을 수 있는 에러 설명 |
| detail | str | 추가 상세 (선택, 디버깅용) |

| HTTP 상태 | code | 발생 상황 |
| --- | --- | --- |
| 422 | `VALIDATION_ERROR` | 요청 스키마 검증 실패 (필수 필드 누락·타입 오류 등) |
| 503 | `LLM_TIMEOUT` | LLM 응답 지연/타임아웃 |
| 502 | `LLM_ERROR` | LLM 호출 실패·구조화 출력 파싱 실패 |
| 500 | `INTERNAL_ERROR` | 그 외 내부 처리 오류 |

### 4-1. 단건 — 에러 응답

단건은 부분 응답이 없다. 분석이 실패하면 위 공통 스키마(HTTP 4xx/5xx)로 응답한다.

예) `500 Internal Server Error`

```json
{
  "code": "INTERNAL_ERROR",
  "message": "분석 처리 중 오류가 발생했습니다.",
  "detail": "..."
}
```

### 4-2. 다건 — 일부 에러 (부분 실패)

개별 로그 실패는 전체 배치를 막지 않는다. **HTTP 200**으로 응답하며, 실패한 로그만 `processStatus="fail"` + `errorMessage`로 표시된다(성공·실패 혼재).

예) `200 OK`

```json
{
  "totalCount": 2,
  "processingTimeMs": 1234,
  "results": [
    {
      "logId": 1,
      "processStatus": "success",
      "status": true,
      "result": {
        "eventId": "string",
        "riskLevel": "높음",
        "summary": "string",
        "analysis": "string",
        "action": "string",
        "clusterId": 7,
        "analyzedAt": "2026-06-22 10:00:00"
      }
    },
    {
      "logId": 2,
      "processStatus": "fail",
      "errorMessage": "LLM 응답 파싱 실패"
    }
  ]
}
```

### 4-3. 다건 — 전체 에러

요청 자체가 깨졌거나(스키마 검증 실패 등) 배치 전체를 처리할 수 없는 경우, 개별 항목이 아니라 **요청 전체**가 공통 에러 스키마(HTTP 4xx/5xx)로 응답한다. 이때 `results`는 반환되지 않는다.

예) `422 Unprocessable Entity`

```json
{
  "code": "VALIDATION_ERROR",
  "message": "요청 형식이 올바르지 않습니다.",
  "detail": "logs: field required"
}
```