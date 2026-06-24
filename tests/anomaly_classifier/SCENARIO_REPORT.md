# 이상 여부 + 긴급도 분류 Tool — 시나리오 검증 리포트

- 생성: 2026-06-23
- 대상 함수: `classify_anomaly(event_id)`
- 판정 기준: `is_anomaly` → 클러스터링 tool / 정상 근거 산출 LLM 라우팅


## 요약

| # | 시나리오 | event_id | 기대(anomaly/urgency) | 실제(anomaly/urgency) | 결과 |
|---|---|---|---|---|---|
| S1 | 정상 — ECC 자동 정정 | `E7` | False / None | False / None | ✅ PASS |
| S2 | 정상 — 레지스터 덤프 | `E43` | False / None | False / None | ✅ PASS |
| S3 | 정상 — 명령어 캐시 패리티 자동 정정 | `E77` | False / None | False / None | ✅ PASS |
| S4 | 정상 — job 수준 실패 (ciod 파일 없음) | `E28` | False / None | False / None | ✅ PASS |
| S5 | 비정상 Critical — 데이터 스토리지 인터럽트 | `E52` | True / Critical | True / Critical | ✅ PASS |
| S6 | 비정상 Critical — 커널 비정상 종료 | `E111` | True / Critical | True / Critical | ✅ PASS |
| S7 | 비정상 High — DDR 메모리 오류 | `E1` | True / High | True / High | ✅ PASS |
| S8 | 비정상 High — 토러스 네트워크 오류 | `E8` | True / High | True / High | ✅ PASS |
| S9 | 비정상 Mid — ciod 시스템 자원 고갈 | `E19` | True / Mid | True / Mid | ✅ PASS |
| S10 | 비정상 Low — L3 EDRAM 정정 가능 오류 | `E5` | True / Low | True / Low | ✅ PASS |
| S11 | 미분류 — 템플릿 매칭 실패 | `unknown` | True / Mid | True / Mid | ✅ PASS |


## 상세 트레이스

### S1. 정상 — ECC 자동 정정

- 설명: 하드웨어가 자동 정정 완료. 단발성 발생은 정상 범위.
- event_id: `E7`
- is_anomaly: `False` / urgency: `None`
- category: `HARDWARE`
- 라우팅: **정상 근거 산출 LLM**
- impact: `ECC 자동 정정됨. 반복 발생 시 메모리 열화 징후.`
- action: `발생 추세 모니터링, 임계치 초과 시 교체`
- 기대: is_anomaly=`False`, urgency=`None` → **✅ PASS**

### S2. 정상 — 레지스터 덤프

- 설명: 장애 발생 시 자동 출력되는 CPU 설정 레지스터 덤프. 오류 자체가 아닌 컨텍스트 정보.
- event_id: `E43`
- is_anomaly: `False` / urgency: `None`
- category: `UNKNOWN`
- 라우팅: **정상 근거 산출 LLM**
- impact: `CPU 설정 레지스터 덤프. 오류 컨텍스트 정보.`
- action: `주변 로그 참조`
- 기대: is_anomaly=`False`, urgency=`None` → **✅ PASS**

### S3. 정상 — 명령어 캐시 패리티 자동 정정

- 설명: 캐시 패리티 오류 자동 정정됨. 반복 발생 시에만 주의.
- event_id: `E77`
- is_anomaly: `False` / urgency: `None`
- category: `HARDWARE`
- 라우팅: **정상 근거 산출 LLM**
- impact: `캐시 패리티 오류이나 자동 정정됨. 반복 발생 시 메모리 이상 가능.`
- action: `추세 모니터링, 반복 시 메모리 점검`
- 기대: is_anomaly=`False`, urgency=`None` → **✅ PASS**

### S4. 정상 — job 수준 실패 (ciod 파일 없음)

- 설명: 사용자 프로그램 경로 오류로 해당 작업만 종료. 시스템은 계속 운영 가능. FATAL 레벨이지만 시스템 장애가 아닌 job 수준 실패.
- event_id: `E28`
- is_anomaly: `False` / urgency: `None`
- category: `FILESYSTEM`
- 라우팅: **정상 근거 산출 LLM**
- impact: `job 수준 ciod 오류. 프로그램 파일 없음으로 해당 작업 종료.`
- action: `경로 및 파일 존재 여부 확인`
- 기대: is_anomaly=`False`, urgency=`None` → **✅ PASS**

### S5. 비정상 Critical — 데이터 스토리지 인터럽트

- 설명: 메모리 읽기/쓰기 중 오류. 데이터 무결성 직접 위협.
- event_id: `E52`
- is_anomaly: `True` / urgency: `Critical`
- category: `KERN`
- 라우팅: **클러스터링 tool**
- impact: `메모리 읽기/쓰기 중 오류. 데이터 무결성 직접 위협.`
- action: `즉각 하드웨어 점검 (ECC 오류 로그 수집, 메모리 교체 검토)`
- 기대: is_anomaly=`True`, urgency=`Critical` → **✅ PASS**

### S6. 비정상 Critical — 커널 비정상 종료

- 설명: 커널 강제 중단. 실행 중 작업 전체 상태 소실.
- event_id: `E111`
- is_anomaly: `True` / urgency: `Critical`
- category: `KERN`
- 라우팅: **클러스터링 tool**
- impact: `커널 강제 중단. 실행 중 작업 전체 상태 소실.`
- action: `OOM 점검, 노드별 메모리 사용량 모니터링`
- 기대: is_anomaly=`True`, urgency=`Critical` → **✅ PASS**

### S7. 비정상 High — DDR 메모리 오류

- 설명: DDR 메모리 오류. 데이터 무결성 영향 가능.
- event_id: `E1`
- is_anomaly: `True` / urgency: `High`
- category: `HARDWARE`
- 라우팅: **클러스터링 tool**
- impact: `DDR 메모리 오류. 데이터 무결성 영향 가능.`
- action: `메모리 모듈 점검 및 교체`
- 기대: is_anomaly=`True`, urgency=`High` → **✅ PASS**

### S8. 비정상 High — 토러스 네트워크 오류

- 설명: 토러스 인터커넥트 오류. 노드 간 통신 이상.
- event_id: `E8`
- is_anomaly: `True` / urgency: `High`
- category: `NETWORK`
- 라우팅: **클러스터링 tool**
- impact: `토러스 인터커넥트 오류. 노드 간 통신 이상.`
- action: `토러스 링크 점검, 네트워크 재구성`
- 기대: is_anomaly=`True`, urgency=`High` → **✅ PASS**

### S9. 비정상 Mid — ciod 시스템 자원 고갈

- 설명: 파일 디스크립터 부족으로 ciod 실패. 시스템 자원 고갈 — job 수준 실패(S4)와 달리 다른 작업에도 영향 가능.
- event_id: `E19`
- is_anomaly: `True` / urgency: `Mid`
- category: `APP`
- 라우팅: **클러스터링 tool**
- impact: `컴퓨트 I/O 데몬 오류. 해당 작업 실패.`
- action: `I/O 인터페이스 안정성 점검`
- 기대: is_anomaly=`True`, urgency=`Mid` → **✅ PASS**

### S10. 비정상 Low — L3 EDRAM 정정 가능 오류

- 설명: L3 캐시 ECC 정정됨. 반복 시 메모리 열화 징후.
- event_id: `E5`
- is_anomaly: `True` / urgency: `Low`
- category: `HARDWARE`
- 라우팅: **클러스터링 tool**
- impact: `L3 캐시 ECC 정정됨. 반복 발생 시 메모리 열화 징후.`
- action: `발생 빈도 모니터링, 임계치 초과 시 하드웨어 점검`
- 기대: is_anomaly=`True`, urgency=`Low` → **✅ PASS**

### S11. 미분류 — 템플릿 매칭 실패

- 설명: event_template.py 매칭 실패. 에러로 처리 후 클러스터링 tool로 전달.
- event_id: `unknown`
- is_anomaly: `True` / urgency: `Mid`
- category: `UNKNOWN`
- 라우팅: **클러스터링 tool (미분류)**
- impact: `알 수 없는 이벤트 — 직접 판단 필요.`
- action: `로그 내용 직접 확인`
- 기대: is_anomaly=`True`, urgency=`Mid` → **✅ PASS**

