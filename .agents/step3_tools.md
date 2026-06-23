# 3단계 구현 상세: Agent용 Tool(도구) 모듈 개발

> 상위 계획: [implementation_plan.md](implementation_plan.md) 3단계
> 목표: 4단계 LangGraph 노드에서 호출할 **독립 실행 가능한 도구 4개**를 완성하고 단위 테스트한다.
> 원칙
> - 각 Tool은 **프레임워크(LangGraph 등)에 종속되지 않는 순수 함수 + Pydantic 결과 모델**로 작성한다. (오케스트레이션 계층 `app/services`가 노드로 감쌈)
> - **ChromaDB(RAG)를 쓰지 않는다.** 모든 Tool은 `app/agents/tools/metadata/`의 **내부 정의 JSON을 직접 참조**해 결정적으로 판정한다.
> - 위치: 코드는 `app/agents/tools/`, 판정 메타데이터는 `app/agents/tools/metadata/`(코드와 분리).

## Tool 의존·실행 순서

```
① 이벤트 템플릿 분류 ──▶ ② 이상 여부 + 긴급도 분류 ──┬─(정상)─▶ 정상 근거 산출 LLM (FastAPI 라우팅)
   event_id 산출           is_anomaly / urgency        └─(이상)─▶ ③ 클러스터 분류 (cluster_id)
                                                       ④ Node 정보 조회 (전건 보강)
```

- **①가 선행**: `event_id`가 나와야 ②③가 판정 가능.
- **②에서 분기**: `is_anomaly`가 정상이면 ③를 건너뛴다. (라우팅 결정은 호출 측이 `is_anomaly`를 보고 수행 — Tool 자체는 분기하지 않음)
- **③(클러스터)는 이상 건만**, **④(Node 정보)는 전건** 호출 — 현재 파이프라인 테스트(`tests/pipeline_scenarios`) 기준. (설계 문서는 ③④ 모두 이상 시 수행으로 기술 → 후속 정렬 필요, 아래 리스크 참조)

---

## 3-1. Tool ① 이벤트 템플릿 분류 (`app/agents/tools/event_template.py`) ✅ 구현

raw 로그 `content`를 BGL 정식 `event_id`로 매핑한다. (drain template-match, 규칙 기반·LLM 미사용)

- [x] `extract_event_template(content: str) -> EventTemplateResult` 순수 함수 제공
- [x] 결과 모델 `EventTemplateResult(event_id, event_template, matched)` — 전 필드 `Field(description=...)` 문서화
- [x] 메타데이터 `metadata/event_template.json` 참조 (BGL_2k 기준, 120 템플릿 / alert 15종)
- [x] 매칭 규칙: regex `^...$` 앵커, `<*>` → `(.*?)` 비탐욕
- [x] tie-break(다중 매칭): **literal_len 내림차순 → wildcard_count 오름차순 → event_id 오름차순**(결정적)
- [x] 매칭 0건 → `unknown` 반환(`matched=False`)
- [x] 앞뒤 공백 strip, 빈 문자열 안전 처리
- [x] `@lru_cache`로 템플릿 1회 로드, `EventTemplateExtractor(templates=...)` 주입으로 테스트 격리
- [x] 테스트: 단위 5 + 정확도(BGL_2k 100%) + 시나리오 = **pytest 7건 통과**

## 3-2. Tool ② 이상 여부 + 긴급도 분류 (`app/agents/tools/anomaly_classifier.py`) ✅ 구현

Tool ①의 `event_id`를 받아 정상/이상 여부와 긴급도를 판정한다. (규칙 기반·LLM 미사용)

- [x] `classify_anomaly(event_id: str) -> AnomalyResult` 순수 함수 제공
- [x] 결과 모델 `AnomalyResult(event_id, is_anomaly, urgency, category, impact, action)` — 전 필드 `Field(description=...)` 문서화
- [x] 긴급도 `Urgency` Enum: `Critical` / `High` / `Mid` / `Low` (※ `None` 멤버 제거됨)
- [x] **정상 이벤트도 템플릿 기반 `urgency`를 그대로 부여** — 단발성은 정상이나 잠재 심각도를 대시보드·추세 신호로 보존
- [x] `category` 도메인 분류(정상·비정상 공통): `HARDWARE` / `KERN` / `NETWORK` / `FILESYSTEM` / `APP` / `UNKNOWN`
- [x] 메타데이터 `metadata/event_analysis_v2.json` 참조 (120 events)
- [x] `is_anomaly=False`(정상): `impact`=정상 근거, `action`=주의 조건(없으면 None) → 호출 측이 정상 근거 산출 LLM으로 라우팅
- [x] `is_anomaly=True`(이상): `impact`=장애 영향, `action`=권장 대응
- [x] `event_id="unknown"` 또는 미등록 → `is_anomaly=True`, `urgency=Mid`, `category="UNKNOWN"` (안전망)
- [x] `@lru_cache` 1회 로드, `AnomalyClassifier(events=...)` 주입으로 테스트 격리
- [ ] **자동화 pytest 미작성** — 검증은 `tests/anomaly_classifier/SCENARIO_REPORT.md`(시나리오 11건)뿐 (후속)

> **향후 고도화(코드 NOTE 반영):** 현재 ②는 단건(stateless) 판정. "단발은 정상이나 반복 시 위험"(머신 체크·RTS 등) 유형은 다건(빈도·시계열) 분석으로 `urgency`를 동적 격상할 예정이며, 격상은 집계 정보를 가진 **클러스터링/오케스트레이터 계층**에서 수행한다.

## 3-3. Tool ③ 클러스터(패턴) 분류 (`app/agents/tools/cluster.py`) ✅ 구현

Tool ①의 `event_id`를 사전 정의된 클러스터(장애 유형군)에 배정한다. (`clusters.json` 고정 매핑 역인덱스, 임베딩 없음)

- [x] `assign_cluster(event_id: str) -> ClusterResult` 순수 함수 제공
- [x] 결과 모델 `ClusterResult(cluster_id: int, matched: bool)` — `Field(description=...)` 문서화. `cluster_id`는 API `result.clusterId`로 직결
- [x] 메타데이터 `metadata/clusters.json` 참조 (9개 클러스터: `id` 0~7 + 미분류 `99`; 각 `cluster_title`·`description`·`event_template[]`·`importance`)
- [x] `event_id → cluster_id` 역인덱스 구성 (한 `event_id`가 복수 클러스터에 걸칠 수 있어 집합으로 보관)
- [x] 배정 규칙:
  - 단일 클러스터 매칭 → 해당 `cluster_id`, `matched=True`
  - 0개(미커버·unknown) → `cluster_id=99`(미분류), `matched=True`
  - 2개 이상(다중 배정 모호) → `cluster_id=99`, `matched=False`
- [x] `@lru_cache` 1회 로드, `ClusterAssigner(clusters=...)` 주입으로 테스트 격리
- [x] 테스트: `test_cluster.py` + `test_cluster_bgl_2k.py` = **pytest 8건 통과**

## 3-4. Tool ④ Node별 정보 조회 (`app/agents/tools/node_info.py`) ✅ 구현

`node_id`를 파싱해 하드웨어 계층과 과거 이상 발생 비율을 보강한다. (규칙 기반·LLM 미사용)

- [x] `get_node_info(node_id: str) -> NodeInfoResult` 순수 함수 제공 (진입 시 `.strip().upper()` 정규화)
- [x] 결과 모델 `NodeInfoResult(node_metadata, alert_stats)` — 전 필드 `Field(description=...)` 문서화
  - `NodeMetadata(rack, midplane, node_slot, node_role, socket_position, processor_unit)`
  - `AlertStats(alert_pct)` (미등록 노드는 `alert_stats=None`)
- [x] node_id 계층 파싱(정규식 `R-M-N-C/I:J-U`): 노드카드 16진수 → 10진수 변환(`NB` → `N11`), ntype `C`→Compute / `I`→I/O
- [x] 메타데이터 `metadata/node_stats.json` 참조 (84개 노드, 2k 샘플 alert_pct)
- [x] 랙/미드플레인 단위 조회 시 하위 노드 중 **최대 alert_pct** 반환 (prefix 매칭)
- [x] 파싱 불가(`NULL`·`UNKNOWN_LOCATION`·형식 불일치) → `node_metadata` 전 필드 None
- [x] `@lru_cache` 로딩/파싱
- [x] 테스트: `test_node_info_scenarios.py` (시나리오 10건) = **pytest 1건 통과**

---

## 3단계 완료 기준 (DoD)

- [x] **4개 Tool 모두 4단계 의존 없이 단독 실행**된다 (순수 함수)
- [x] 반환 타입이 Pydantic 모델로 고정되어 4단계 State에 바로 넣을 수 있다 (전 모델 `Field` 문서화 완료)
- [x] Tool ①·③·④ 자동화 테스트 통과
- [x] **①→②→③→④ 전체 파이프라인 통합 테스트** 존재 (`tests/pipeline_scenarios`)
- [ ] Tool ② **자동화 pytest** 작성 및 통과 (현재 시나리오 리포트만 존재)
- [ ] Tool 산출 명칭·정상 urgency ↔ API 계약 정렬 확정 (아래 리스크 참조)

---

## 개발 현황 요약 (2026-06-23 기준)

> 브랜치 `feat/agent-drain-clustering-tools` 기준. **4개 Tool 모두 구현 완료**, 전체 테스트 **18건 통과**.

### Tool별 상태

| Tool | 파일 | 상태 | 핵심 산출 | 메타데이터 | 테스트 |
|------|------|:---:|-----------|-----------|--------|
| ① 이벤트 템플릿 분류 | `event_template.py` | ✅ 구현 | `event_id`, `event_template`, `matched` | `event_template.json` (120 템플릿) | **pytest 7건** (단위5 + 정확도 100% + 시나리오) |
| ② 이상 여부 + 긴급도 | `anomaly_classifier.py` | ✅ 구현 | `is_anomaly`, `urgency`, `category`, `impact`, `action` | `event_analysis_v2.json` (120 events) | 시나리오 리포트 11건 — **자동화 pytest 0건** |
| ③ 클러스터 분류 | `cluster.py` | ✅ 구현 | `cluster_id`(int), `matched` | `clusters.json` (9 클러스터: 0~7+99) | **pytest 8건** |
| ④ Node 정보 조회 | `node_info.py` | ✅ 구현 | `node_metadata`, `alert_stats` | `node_stats.json` (84 노드) | **pytest 1건** (시나리오 10건) |
| (통합) 파이프라인 | `tests/pipeline_scenarios` | ✅ | ①→②→③→④ 전 경로 | `tests/integration/pipeline_{input,output}.json` | **pytest 1건** |

### 구현 특징

- **결정적 규칙 기반**: 4개 Tool 모두 LLM·벡터DB 없이 JSON 메타데이터만으로 판정 (재현성·테스트 용이).
- **순수 함수 + 주입 가능 클래스**: 각 진입 함수 단독 호출 가능, `Extractor`/`Classifier`/`Assigner`에 메타데이터 주입으로 테스트 격리.
- **Pydantic `Field` 문서화 완료**: 4개 결과 모델 전 필드에 설명 부여(API/4단계 매핑 참조용).
- **`@lru_cache` 메타데이터 로딩**: 프로세스 기동 시 1회만 읽음.
- **②의 라우팅 비결정**: Tool은 분기하지 않고 `is_anomaly`만 산출 — 정상/이상 라우팅은 호출 측(엔드포인트/오케스트레이터) 책임.

### 메타데이터 커버리지

- `event_analysis_v2.json`: 120 템플릿 중 **분류 70 / 미분류 50** (이상 59 / 정상 61). 미분류·미등록은 ②에서 `UNKNOWN`(이상·`Mid`)으로 안전 처리 → **분류 보강 시 정확도 향상 여지**.
- `clusters.json`: 9개 클러스터(0~7 + 미분류 99). 미커버 `event_id`는 99로 흡수.
- `node_stats.json`: 84개 노드. 1개만 41.96%로 집중, 나머지는 대부분 0.7%(2k 샘플 단건) — **hot 노드 외 변별력은 낮음**.

### 남은 작업 / 리스크

1. **Tool ② 자동화 pytest 부재** — 검증이 `SCENARIO_REPORT.md`(11건)뿐. 회귀 방지용 pytest 추가 필요(①③④는 모두 pytest 보유).
2. **계약 명칭·값 정렬** — Tool 산출과 API 계약([API.md])이 아직 다름. 4단계 결과 매핑 노드에서 변환 흡수 또는 명칭 통일 확정 필요:
   - `is_anomaly`(bool) ↔ API `isAbnormal`
   - `urgency`(영문 `Critical/High/Mid/Low`) ↔ API `riskLevel`(한글 `긴급/높음/보통/낮음`)
   - **정상 이벤트 urgency**: Tool ②는 정상에도 `urgency`를 부여하나, API 계약은 `정상`이면 `result.riskLevel=null` → 매핑 노드에서 정상 시 null 처리할지, 계약을 바꿀지 결정 필요.
   - `impact` → `result.analysis`, `action` → `result.action` 매핑
   - `cluster_id` → `result.clusterId` (미분류 99의 응답 표현 — `null` vs `99` — 확정 필요)
3. **③④ 실행 위치 정합성** — 파이프라인 구현은 ③=이상만 / ④=전건이나, 설계 문서([ArchitectureGuide.md]·[API.md])는 ③④ 모두 이상 시 수행으로 기술. 둘 중 하나로 정렬 필요.
4. **문서 드리프트** — `app/agents/tools/README.md`의 담당 Tool 표가 ①③만 기재(②④ 누락). `tests/integration/pipeline_*.json`의 요청 필드는 구 명칭(`logTs`·빈 `domain`) 사용 — API 계약 최신 명칭(`occurredAt`)과 정렬 필요.
