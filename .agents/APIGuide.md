# 로그 분석 API 명세

## 엔드포인트 요약

| Method | URI | Parameter | 설명 |
|--------|-----|-----------|------|
| POST | `/ai/v1/analyze` | - | 로그 1건 분석 (수동 / 개별 재처리용) |
| POST | `/ai/v1/analyze/batch` | - | 로그 다건 분석 (스케줄러 기본 경로) |

---

## 1. POST `/ai/v1/analyze` — 로그 1건 분석

수동 또는 개별 재처리 용도로 로그 한 건을 분석합니다.

### Request

```json
{
  "logId": 0,
  "label": "string",
  "node": "string",
  "nodeRepeat": "string",
  "component": "string",
  "logType": "string",
  "logTs": "string",
  "logLevel": "string",
  "content": "string",
  "eventId": "string"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| logId | int | 로그 식별자 |
| label | str | 라벨 |
| node | str | 노드 |
| nodeRepeat | str | 노드 반복 정보 |
| component | str | 컴포넌트 |
| logType | str | 로그 타입 |
| logTs | str | 로그 타임스탬프 |
| logLevel | str | 로그 레벨 |
| content | str | 로그 내용 |
| eventId | str | 이벤트 식별자 |

### Response

```json
{
  "logId": 0,
  "result": {
    "domain": "string",
    "riskLevel": "string",
    "summary": "string",
    "analysis": "string",
    "action": "string",
    "clusterId": 0,
    "analyzedAt": "timestamp"
  },
  "processingTimeMs": 0
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| logId | int | 분석 대상 로그 식별자 |
| result.domain | str | 도메인 |
| result.riskLevel | str | 위험도 |
| result.summary | str | 요약 |
| result.analysis | str | 분석 내용 |
| result.action | str | 대응 방안 |
| result.clusterId | int | 클러스터 식별자 |
| result.analyzedAt | timestamp | 분석 시각 |
| processingTimeMs | int | 처리 소요 시간 (ms) |

---

## 2. POST `/ai/v1/analyze/batch` — 로그 다건 분석

스케줄러 기본 경로로, 여러 로그를 한 번에 분석합니다.

### Request

```json
{
  "logs": [
    {
      "logId": 0,
      "label": "string",
      "node": "string",
      "nodeRepeat": "string",
      "component": "string",
      "logType": "string",
      "logTs": "string",
      "logLevel": "string",
      "content": "string",
      "eventId": "string"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| logs | array | 분석할 로그 객체 배열 (각 객체 필드는 단건 분석 Request와 동일) |

### Response

```json
{
  "totalCount": 0,
  "processingTimeMs": 0,
  "results": [
    {
      "logId": 0,
      "status": "string",
      "result": {
        "domain": "string",
        "riskLevel": "string",
        "summary": "string",
        "analysis": "string",
        "action": "string",
        "clusterId": 0
      }
    },
    {
      "logId": 0,
      "status": "string",
      "error": "string"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| totalCount | int | 처리한 로그 총 개수 |
| processingTimeMs | int | 전체 처리 소요 시간 (ms) |
| results | array | 로그별 분석 결과 배열 |
| results[].logId | int | 로그 식별자 |
| results[].status | str | 처리 상태 (성공 / 실패) |
| results[].result | object | 성공 시 분석 결과 (domain, riskLevel, summary, analysis, action, clusterId) |
| results[].error | str | 실패 시 오류 메시지 |