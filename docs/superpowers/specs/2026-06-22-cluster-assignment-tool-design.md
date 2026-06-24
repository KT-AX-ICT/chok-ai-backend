# Tool③ 클러스터 분류(cluster assignment) 설계

- 날짜: 2026-06-22
- 대상: `app/agents/tools/cluster.py` (신규)
- 관련: Tool① 이벤트 템플릿 추출([event_template.py](../../../app/agents/tools/event_template.py)), [clusters.json](../../../app/agents/tools/metadata/clusters.json)

## 1. 목적

Tool①이 산출한 `event_id`를 사전 정의된 **클러스터(장애 유형군)** 에 배정해 API 응답의 `result.clusterId`(int)를 만든다. 분석 파이프라인에서 Tool① 다음에 실행되는 결정적 단계다.

## 2. 접근 결정 — 결정적 역인덱스 lookup (임베딩 없음)

`clusters.json`이 이미 사람이 큐레이션한 `event_id → cluster` 고정 매핑을 제공한다(중복 배정 0건). 따라서 런타임은 **dict 조회**만 하면 된다.

| 접근 | 채택 | 사유 |
| --- | --- | --- |
| 결정적 역인덱스 lookup | ✅ | 매핑이 확정적. Tool①과 동일 철학(메타데이터 기반·결정적·캐싱). |
| ChromaDB 벡터 유사도 | ❌ | 처음 보는 로그를 의미 유사도로 묶을 때만 필요. 우리는 알려진 event_id를 알려진 클러스터에 배정할 뿐. |
| LLM 분류 | ❌ | 비결정적·비용↑. 과함. |

> 원 설계(ArchitectureGuide)의 ChromaDB RAG 방안에서 벗어나는 결정이며, Tool①의 "online Drain 대신 offline 메타데이터" 결정과 동일한 맥락(재현성 > 적응력). 메타데이터 담당과 공유 필요.

## 3. 입력 / 출력 계약

- **입력**: `event_id: str` — Tool①의 출력(`"E111"`, `"unknown"` 등)
- **출력**: `ClusterResult` (Pydantic, 최소 필드)

```python
class ClusterResult(BaseModel):
    cluster_id: int   # API result.clusterId 로 직결
    matched: bool     # event_id 가 유효한지(unknown 아님) = 클러스터 배정 성공 여부
```

| 입력 event_id | cluster_id | matched | 의미 |
| --- | --- | --- | --- |
| 큐레이션 클러스터의 event_id (E111 등 15종) | 0~7 | True | 정상 분류 |
| 유효하지만 미커버 event_id (E1, E77 등) | 99 | True | 유효 로그, 미분류 버킷 → 관리자 검토 |
| `"unknown"` | 99 | False | Tool① 미매칭 (잠정, 아래 라우팅 참고) |

`matched` 는 "큐레이션 클러스터 배정 성공"이 아니라 **"event_id 가 유효한가(unknown 아님)"** 를 뜻한다. 따라서 미커버 유효 event_id 도 matched=True 로 미분류(99)에 배정된다. "큐레이션 클러스터에 들어갔는지" 는 `cluster_id != 99` 로 판별한다.

`cluster_title`/`importance`는 결과 모델에 포함하지 않는다(필요 시 Spring이 별도 조회). 메타데이터에는 존재한다.

> **unknown 라우팅 (논의 중)**: `event_id == "unknown"` 로그는 오케스트레이션 단계에서 클러스터 노드를 건너뛰고 답변 생성으로 직행할 가능성이 높다(라우팅은 오케스트레이션 책임, 확정 전). Tool③ 자체는 방어적으로 `99 / matched=False` 를 반환하되, 이 동작은 unknown 처리 구조 확정 시 재검토한다.

## 4. 미분류 클러스터 (id: 99)

`clusters.json`에 실제 엔트리로 추가됨:

```json
{
  "id": 99,
  "cluster_title": "미분류 (관리자 검토 필요)",
  "description": "사전 정의된 클러스터(0~7) 중 어디에도 매핑되지 않는 event_id가 배정되는 기타 버킷. 신규·희소 로그 유형이거나 unknown일 수 있어 관리자 검토가 필요하다. (전문은 clusters.json 참조)",
  "event_template": [],
  "importance": "Low"
}
```

- `event_template`이 **빈 배열** = 어떤 event_id도 명시적으로 속하지 않는 fallback 버킷.
- 코드에는 `MISC_CLUSTER_ID = 99` 상수를 둔다. 역인덱스에 없는 event_id는 모두 여기로.

## 5. 아키텍처 (Tool①과 동일 구조)

```
app/agents/tools/cluster.py
 ├ MISC_CLUSTER_ID = 99
 ├ ClusterResult(BaseModel)            # cluster_id, matched
 ├ ClusterAssigner                     # event_id→cluster_id 역인덱스 (clusters 주입 가능 = 테스트 용이)
 │    └ assign(event_id) -> ClusterResult
 ├ _load_clusters()        @lru_cache    # clusters.json 1회 로드
 ├ _default_assigner()     @lru_cache    # assigner 1회 생성·캐싱
 └ assign_cluster(event_id) -> ClusterResult   # 공식 진입점
```

- 역인덱스는 `event_template`이 **비어있지 않은** 클러스터(0~7)에서만 구성. 99(미분류)는 인덱스에 넣지 않음.
- `assign(event_id)` 로직: 역인덱스에 있으면 `(cluster_id, matched=True)`. 없으면 `(99, matched = (event_id != UNKNOWN_EVENT_ID))` — 즉 유효 미커버는 True, `"unknown"`만 False. unknown 판별은 Tool①의 `UNKNOWN_EVENT_ID` 상수를 재사용(단일 출처).
- 프레임워크 비종속 순수 함수. 오케스트레이션이 노드로 감쌈.

## 6. 엣지 / 에러 처리 (Tool① 원칙 계승)

- `clusters.json` 로드/파싱 실패 → **fail-fast**(예외 삼키지 않음). 신뢰된 정적 자산.
- **중복 배정 검증**: 한 event_id가 둘 이상 클러스터에 있으면 로드 시 명확한 에러로 재발생(현재 0건이지만 메타데이터 회귀 방지).
- 정상/미분류는 에러가 아니라 `matched` 플래그로 표현.

## 7. 테스트 계획

`tests/cluster/` (Tool① 테스트 구조와 동일 패턴):

- **단위**
  - 커버된 event_id → 올바른 cluster_id, matched=True (예: `E111` → 3, `E23` → 6)
  - 미커버 유효 event_id (예: `E1`) → 99, **matched=True** (유효 로그 → 미분류 배정)
  - `"unknown"` → 99, **matched=False** (Tool① 미매칭)
  - 중복 배정 메타데이터 주입 → 로드 시 에러(fail-fast) 검증
- **정합성**: clusters.json의 15개 event_id가 전부 1:1 매핑되는지 전수 확인
- (선택) Tool① → Tool③ 연계 스모크: 로그 `content` → `event_id` → `cluster_id`

## 8. 범위 밖 (out of scope)

- alert/긴급도 판정 (Tool②)
- 클러스터 정의 자체의 생성·갱신 (offline 큐레이션)
- LLM 분석/대응 작성 (LLM 노드)
- 분석 결과 저장 (Spring)
