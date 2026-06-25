# Node 정보 조회 Tool — 시나리오 검증 리포트

- 생성: 2026-06-25
- 대상 함수: `get_node_info(node_id)`
- 판정 기준: node_id 파싱 계층(rack/midplane/node_slot/node_role) + alert_pct 조회 경로


## 요약

| # | 시나리오 | node_id | 기대 alert_pct | 실제 alert_pct | 결과 |
|---|---|---|---|---|---|
| S1 | Compute 노드 — 최고빈도 이상 노드 | `R30-M0-N9-C:J16-U01` | 41.96% | 41.96% | ✅ PASS |
| S2 | I/O 노드 — role 파싱 확인 | `R04-M1-N4-I:J18-U11` | 0.7% | 0.7% | ✅ PASS |
| S3 | hex nodecard B — NB → node_slot N11 | `R16-M0-NB-C:J07-U11` | 0.7% | 0.7% | ✅ PASS |
| S4 | hex nodecard A — NA → node_slot N10 | `R01-M1-NA-C:J13-U01` | 0.7% | 0.7% | ✅ PASS |
| S5 | rack 단위 조회 — 하위 최대 alert_pct | `R30` | 41.96% | 41.96% | ✅ PASS |
| S6 | midplane 단위 조회 — 하위 최대 alert_pct | `R30-M0` | 41.96% | 41.96% | ✅ PASS |
| S7 | 미등록 노드 — alert_stats=None | `R99-M0-N0-C:J01-U01` | None | None | ✅ PASS |
| S8 | NULL 입력 — 전 필드 None | `NULL` | None | None | ✅ PASS |
| S9 | 빈 문자열 — 전 필드 None | `` | None | None | ✅ PASS |
| S10 | 소문자 입력 — 자동 대문자 정규화 | `r30-m0-n9-c:j16-u01` | 41.96% | 41.96% | ✅ PASS |


## 상세 트레이스

### S1. Compute 노드 — 최고빈도 이상 노드

- 설명: BGL_2k 이상 로그 143건 중 60건(41.96%)이 집중된 노드. 직접 조회 경로.
- 입력: `R30-M0-N9-C:J16-U01`
- 파싱 결과: `rack=R30, mp=R30-M0, slot=N9, role=Compute, socket=J16, unit=U01`
- 조회 경로: 직접 조회 (exact match)
- alert_pct: `41.96%`
- 기대 alert_pct: `41.96%` → **✅ PASS**

### S2. I/O 노드 — role 파싱 확인

- 설명: ntype=I → node_role=I/O 파싱 및 alert_pct 0.7% 직접 조회.
- 입력: `R04-M1-N4-I:J18-U11`
- 파싱 결과: `rack=R04, mp=R04-M1, slot=N4, role=I/O, socket=J18, unit=U11`
- 조회 경로: 직접 조회 (exact match)
- alert_pct: `0.7%`
- 기대 alert_pct: `0.7%` → **✅ PASS**

### S3. hex nodecard B — NB → node_slot N11

- 설명: hex nodecard NB(=11) → node_slot=N11 변환. alert_pct 조회는 원본 키 그대로.
- 입력: `R16-M0-NB-C:J07-U11`
- 파싱 결과: `rack=R16, mp=R16-M0, slot=N11, role=Compute, socket=J07, unit=U11`
- 조회 경로: 직접 조회 (exact match)
- alert_pct: `0.7%`
- 기대 alert_pct: `0.7%` → **✅ PASS**

### S4. hex nodecard A — NA → node_slot N10

- 설명: hex nodecard NA(=10) → node_slot=N10 변환.
- 입력: `R01-M1-NA-C:J13-U01`
- 파싱 결과: `rack=R01, mp=R01-M1, slot=N10, role=Compute, socket=J13, unit=U01`
- 조회 경로: 직접 조회 (exact match)
- alert_pct: `0.7%`
- 기대 alert_pct: `0.7%` → **✅ PASS**

### S5. rack 단위 조회 — 하위 최대 alert_pct

- 설명: rack 수준 조회: stats에 없으면 'R30-' 접두사 하위 노드 중 최대 41.96% 반환.
- 입력: `R30`
- 파싱 결과: `rack=R30`
- 조회 경로: prefix 조회 → 후보 2개 중 최대 41.96%
- alert_pct: `41.96%`
- 기대 alert_pct: `41.96%` → **✅ PASS**

### S6. midplane 단위 조회 — 하위 최대 alert_pct

- 설명: midplane 수준 조회: 'R30-M0-' 접두사 하위 노드 중 최대 41.96% 반환.
- 입력: `R30-M0`
- 파싱 결과: `rack=R30, mp=R30-M0`
- 조회 경로: prefix 조회 → 후보 2개 중 최대 41.96%
- alert_pct: `41.96%`
- 기대 alert_pct: `41.96%` → **✅ PASS**

### S7. 미등록 노드 — alert_stats=None

- 설명: node_stats.json에 없는 노드 → 파싱은 정상, alert_stats=None.
- 입력: `R99-M0-N0-C:J01-U01`
- 파싱 결과: `rack=R99, mp=R99-M0, slot=N0, role=Compute, socket=J01, unit=U01`
- 조회 경로: 미등록 → None
- alert_pct: `None`
- 기대 alert_pct: `None` → **✅ PASS**

### S8. NULL 입력 — 전 필드 None

- 설명: NULL은 누락 위치 플레이스홀더 → 파싱 불가, alert_stats=None.
- 입력: `NULL`
- 파싱 결과: `파싱 실패 → 전 필드 None`
- 조회 경로: 미등록 → None
- alert_pct: `None`
- 기대 alert_pct: `None` → **✅ PASS**

### S9. 빈 문자열 — 전 필드 None

- 설명: 빈 입력 → 파싱 불가, alert_stats=None.
- 입력: ``
- 파싱 결과: `파싱 실패 → 전 필드 None`
- 조회 경로: 미등록 → None
- alert_pct: `None`
- 기대 alert_pct: `None` → **✅ PASS**

### S10. 소문자 입력 — 자동 대문자 정규화

- 설명: get_node_info 진입 시 .upper() 적용 → S1과 동일 결과.
- 입력: `r30-m0-n9-c:j16-u01`
- 파싱 결과: `rack=R30, mp=R30-M0, slot=N9, role=Compute, socket=J16, unit=U01`
- 조회 경로: 직접 조회 (exact match)
- alert_pct: `41.96%`
- 기대 alert_pct: `41.96%` → **✅ PASS**

