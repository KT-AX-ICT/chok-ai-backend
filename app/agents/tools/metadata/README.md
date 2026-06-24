# Tool 메타데이터

Tool ①(이벤트 템플릿 분류) · Tool ③(클러스터 분류)가 판정에 사용하는 메타데이터 파일을 둡니다.

## 넣을 파일

| 파일명(예시) | 사용 Tool | 설명 |
| --- | --- | --- |
| `event_templates.*` | Tool ① 이벤트 템플릿 분류 | drain 기반 이벤트 템플릿 사전 (template ↔ eventId 매핑) |
| `clusters.*` | Tool ③ 클러스터 분류 | 이벤트 템플릿 → clusterId 배정 정보 |

> 확장자(`.json` / `.csv` / `.parquet` 등)는 받은 메타데이터 형식에 맞춰 확정합니다.

## 참고

- Tool ③의 클러스터 배정 결과(`clusterId`)는 API 응답 `result.clusterId`(int)로 직결됩니다.
- 메타데이터는 코드(`app/agents/tools/`)와 분리해 이 폴더에서만 관리합니다.
- 실제 운영 데이터/secret은 커밋하지 않습니다.
