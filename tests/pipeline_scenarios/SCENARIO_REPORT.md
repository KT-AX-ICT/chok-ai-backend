# Tool①→②→③→④ 전체 파이프라인 시나리오 검증 리포트

- 생성: 2026-06-25
- 진입 조건: FATAL 레벨 event_id 한정
- 파이프라인: `extract_event_template` → `classify_anomaly` → `assign_cluster` → `get_node_info`
- 라우팅 기준: `is_anomaly=False` → LLM  /  `is_anomaly=True` → Tool③ 진행


## 요약

| # | 시나리오 | event_id | is_anomaly / urgency | 클러스터 | alert_pct | 결과 |
|---|---|---|---|---|---|---|
| S1 | 정상 — 명령어 캐시 패리티 자동 정정 | `E77` | False / Low | 미진행 | 41.96% | ✅ PASS |
| S2 | 정상 — job 수준 실패 (ciod 파일 없음) | `E28` | False / Mid | 미진행 | 0.7% | ✅ PASS |
| S3 | 비정상 Critical — 데이터 스토리지 인터럽트 | `E52` | True / Critical | cluster 0 | 41.96% | ✅ PASS |
| S4 | 비정상 Critical — 커널 비정상 종료 | `E111` | True / Critical | cluster 3 | 0.7% | ✅ PASS |
| S5 | 비정상 High — DDR 메모리 오류 | `E1` | True / High | cluster 99 | 0.7% | ✅ PASS |
| S6 | 비정상 Mid — ciod 미인식 메시지 | `E19` | True / Mid | cluster 99 | 0.7% | ✅ PASS |
| S7 | 비정상 Low — L3 EDRAM 정정 가능 오류 | `E5` | True / Low | cluster 99 | 0.7% | ✅ PASS |
| S8 | 미분류 — 템플릿 매칭 실패 → unknown | `unknown` | True / Mid | cluster 99 | 0.7% | ✅ PASS |
| S9 | NULL 노드 — 파싱 불가, 이상 경로 | `E52` | True / Critical | cluster 0 | None% | ✅ PASS |
| S10 | 소문자 노드 — 자동 정규화 후 정상 조회 | `E77` | False / Low | 미진행 | 41.96% | ✅ PASS |


## 상세 트레이스

### S1. 정상 — 명령어 캐시 패리티 자동 정정

- 설명: E77(정상) → LLM 라우팅. 최고위험 노드(41.96%)에서 발생.
- Content: `instruction cache parity error corrected`
- Node: `R30-M0-N9-C:J16-U01`
- Tool①: `event_id=E77`
- Tool②: `is_anomaly=False`, `urgency=Low` → **LLM 라우팅 (FastAPI)**
- Tool③: `미진행`
- Tool④: `rack=R30, slot=N9, role=Compute, alert_pct=41.96%`
- 기대: eid=`E77`, anomaly=`False`, urgency=`Low`, cluster=`None`, rack=`R30`, alert_pct=`41.96%`
- 결과: **✅ PASS**

### S2. 정상 — job 수준 실패 (ciod 파일 없음)

- 설명: E28(정상) → LLM 라우팅. 시스템 장애 아닌 job 수준 실패. I/O 노드.
- Content: `ciod: Error loading /foo: invalid or missing program image, No such file or directory`
- Node: `R04-M1-N4-I:J18-U11`
- Tool①: `event_id=E28`
- Tool②: `is_anomaly=False`, `urgency=Mid` → **LLM 라우팅 (FastAPI)**
- Tool③: `미진행`
- Tool④: `rack=R04, slot=N4, role=I/O, alert_pct=0.7%`
- 기대: eid=`E28`, anomaly=`False`, urgency=`Mid`, cluster=`None`, rack=`R04`, alert_pct=`0.7%`
- 결과: **✅ PASS**

### S3. 비정상 Critical — 데이터 스토리지 인터럽트

- 설명: E52 → cluster 0 배정. 최고위험 노드(41.96%) 연계.
- Content: `data storage interrupt`
- Node: `R30-M0-N9-C:J16-U01`
- Tool①: `event_id=E52`
- Tool②: `is_anomaly=True`, `urgency=Critical` → **Tool③ (클러스터 배정)**
- Tool③: `cluster 0`
- Tool④: `rack=R30, slot=N9, role=Compute, alert_pct=41.96%`
- 기대: eid=`E52`, anomaly=`True`, urgency=`Critical`, cluster=`0`, rack=`R30`, alert_pct=`41.96%`
- 결과: **✅ PASS**

### S4. 비정상 Critical — 커널 비정상 종료

- 설명: E111 → cluster 3 배정. hex 노드카드 NB→N11 변환 확인.
- Content: `rts: kernel terminated for reason 1001`
- Node: `R16-M0-NB-C:J07-U11`
- Tool①: `event_id=E111`
- Tool②: `is_anomaly=True`, `urgency=Critical` → **Tool③ (클러스터 배정)**
- Tool③: `cluster 3`
- Tool④: `rack=R16, slot=N11, role=Compute, alert_pct=0.7%`
- 기대: eid=`E111`, anomaly=`True`, urgency=`Critical`, cluster=`3`, rack=`R16`, alert_pct=`0.7%`
- 결과: **✅ PASS**

### S5. 비정상 High — DDR 메모리 오류

- 설명: E1 → 미분류(cluster 99) 배정.
- Content: `12 ddr error(s) detected and corrected on rank 0, symbol 4 over 1234 seconds`
- Node: `R10-M1-N5-C:J15-U11`
- Tool①: `event_id=E1`
- Tool②: `is_anomaly=True`, `urgency=High` → **Tool③ (클러스터 배정)**
- Tool③: `cluster 99`
- Tool④: `rack=R10, slot=N5, role=Compute, alert_pct=0.7%`
- 기대: eid=`E1`, anomaly=`True`, urgency=`High`, cluster=`99`, rack=`R10`, alert_pct=`0.7%`
- 결과: **✅ PASS**

### S6. 비정상 Mid — ciod 미인식 메시지

- 설명: E19 → 미분류(cluster 99) 배정.
- Content: `ciod: cpu 0 at treeaddr 1 sent unrecognized message 0x0`
- Node: `R13-M1-N2-C:J17-U01`
- Tool①: `event_id=E19`
- Tool②: `is_anomaly=True`, `urgency=Mid` → **Tool③ (클러스터 배정)**
- Tool③: `cluster 99`
- Tool④: `rack=R13, slot=N2, role=Compute, alert_pct=0.7%`
- 기대: eid=`E19`, anomaly=`True`, urgency=`Mid`, cluster=`99`, rack=`R13`, alert_pct=`0.7%`
- 결과: **✅ PASS**

### S7. 비정상 Low — L3 EDRAM 정정 가능 오류

- 설명: E5 → 미분류(cluster 99) 배정.
- Content: `5 L3 EDRAM error(s) (dcr 0x0) detected and corrected`
- Node: `R15-M0-N9-C:J05-U11`
- Tool①: `event_id=E5`
- Tool②: `is_anomaly=True`, `urgency=Low` → **Tool③ (클러스터 배정)**
- Tool③: `cluster 99`
- Tool④: `rack=R15, slot=N9, role=Compute, alert_pct=0.7%`
- 기대: eid=`E5`, anomaly=`True`, urgency=`Low`, cluster=`99`, rack=`R15`, alert_pct=`0.7%`
- 결과: **✅ PASS**

### S8. 미분류 — 템플릿 매칭 실패 → unknown

- 설명: 매칭 실패 → unknown → is_anomaly=True/Mid/cluster 99.
- Content: `this is not a real bgl log at all`
- Node: `R01-M1-NA-C:J13-U01`
- Tool①: `event_id=unknown`
- Tool②: `is_anomaly=True`, `urgency=Mid` → **Tool③ (클러스터 배정)**
- Tool③: `cluster 99`
- Tool④: `rack=R01, slot=N10, role=Compute, alert_pct=0.7%`
- 기대: eid=`unknown`, anomaly=`True`, urgency=`Mid`, cluster=`99`, rack=`R01`, alert_pct=`0.7%`
- 결과: **✅ PASS**

### S9. NULL 노드 — 파싱 불가, 이상 경로

- 설명: 노드 위치 미식별(NULL) → Tool④ 전 필드 None. 파이프라인 나머지는 정상 진행.
- Content: `data storage interrupt`
- Node: `NULL`
- Tool①: `event_id=E52`
- Tool②: `is_anomaly=True`, `urgency=Critical` → **Tool③ (클러스터 배정)**
- Tool③: `cluster 0`
- Tool④: `alert_pct=None%`
- 기대: eid=`E52`, anomaly=`True`, urgency=`Critical`, cluster=`0`, rack=`None`, alert_pct=`None%`
- 결과: **✅ PASS**

### S10. 소문자 노드 — 자동 정규화 후 정상 조회

- 설명: 소문자 node_id → .upper() 정규화 → S1과 동일 결과.
- Content: `instruction cache parity error corrected`
- Node: `r30-m0-n9-c:j16-u01`
- Tool①: `event_id=E77`
- Tool②: `is_anomaly=False`, `urgency=Low` → **LLM 라우팅 (FastAPI)**
- Tool③: `미진행`
- Tool④: `rack=R30, slot=N9, role=Compute, alert_pct=41.96%`
- 기대: eid=`E77`, anomaly=`False`, urgency=`Low`, cluster=`None`, rack=`R30`, alert_pct=`41.96%`
- 결과: **✅ PASS**

