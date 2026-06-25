# 이벤트 템플릿 추출 Tool — 시나리오 검증 리포트

- 생성: 2026-06-25
- 대상 함수: `extract_event_template(content)`
- tie-break 규칙: **literal_len 내림차순 → wildcard_count 오름차순 → event_id 오름차순**


## 요약

| # | 시나리오 | 입력(요약) | 기대 | 실제 | 결과 |
|---|---|---|---|---|---|
| S1 | 정상 단일 매칭 | `instruction cache parity error corrected` | E77 | E77 | ✅ PASS |
| S2a | wildcard 정규화 #1 | `12 ddr error(s) detected and corrected on rank 0, symbol 4 over 1234 seconds` | E1 | E1 | ✅ PASS |
| S2b | wildcard 정규화 #2 | `99 ddr error(s) detected and corrected on rank 7, symbol 1 over 5 seconds` | E1 | E1 | ✅ PASS |
| S4 | tie-break 정상(실제 2k 케이스) | `rts: kernel terminated for reason 1001: bad message header: invalid cpu, type=0x5, cpu=3, …` | E112 | E112 | ✅ PASS |
| S5 | tie-break 비교군 | `rts: kernel terminated for reason 1001` | E111 | E111 | ✅ PASS |
| S6a | unknown — 무관 텍스트 | `this is not a real bgl log at all` | unknown | unknown | ✅ PASS |
| S6b | unknown — near-miss | `instruction cache parity error CORRECTED` | unknown | unknown | ✅ PASS |
| S7a | 엣지 — 앞뒤 공백 | `   instruction cache parity error corrected   ` | E77 | E77 | ✅ PASS |
| S7b | 엣지 — 빈 문자열 | `` | unknown | unknown | ✅ PASS |
| S8 | 합성 — literal_len 동률 | `a 1 b x c` | FEWWILD | FEWWILD | ✅ PASS |
| S9 | 합성 — catch-all 삼킴 | `svc done: detail alpha beta` | SPECIFIC | SPECIFIC | ✅ PASS |
| S10 | 합성 — 완전 동률 | `x foo` | E_AAA | E_AAA | ✅ PASS |


## 상세 트레이스

### S1. 정상 단일 매칭

- 설명: 단일 후보 happy path
- 입력: `instruction cache parity error corrected`
- 후보(매칭 템플릿): E77(ll=40,wc=0)
- 판정: 단일 매칭
- 출력: `event_id=E77`, `matched=True`
- 기대: `E77` → **✅ PASS**

### S2a. wildcard 정규화 #1

- 설명: <*> 가 값을 흡수 → 같은 유형
- 입력: `12 ddr error(s) detected and corrected on rank 0, symbol 4 over 1234 seconds`
- 후보(매칭 템플릿): E1(ll=68,wc=4)
- 판정: 단일 매칭
- 출력: `event_id=E1`, `matched=True`
- 기대: `E1` → **✅ PASS**

### S2b. wildcard 정규화 #2

- 설명: 다른 값이어도 S2a 와 같은 E1 로 정규화
- 입력: `99 ddr error(s) detected and corrected on rank 7, symbol 1 over 5 seconds`
- 후보(매칭 템플릿): E1(ll=68,wc=4)
- 판정: 단일 매칭
- 출력: `event_id=E1`, `matched=True`
- 기대: `E1` → **✅ PASS**

### S4. tie-break 정상(실제 2k 케이스)

- 설명: E111(catch-all) 과 E112 동시 매칭 → literal_len 으로 E112
- 입력: `rts: kernel terminated for reason 1001: bad message header: invalid cpu, type=0x5, cpu=3, index=2, total=4`
- 후보(매칭 템플릿): E112(ll=96,wc=5), E111(ll=34,wc=1)
- 판정: 다중 매칭 2개 → tie-break(literal_len↓, wildcard_count↑, event_id↑)
- 출력: `event_id=E112`, `matched=True`
- 기대: `E112` → **✅ PASS**

### S5. tie-break 비교군

- 설명: 짧은 로그는 E111 단독 매칭(tie 없음) — '언제 애매한가' 대조
- 입력: `rts: kernel terminated for reason 1001`
- 후보(매칭 템플릿): E111(ll=34,wc=1)
- 판정: 단일 매칭
- 출력: `event_id=E111`, `matched=True`
- 기대: `E111` → **✅ PASS**

### S6a. unknown — 무관 텍스트

- 설명: 매칭 0건
- 입력: `this is not a real bgl log at all`
- 후보(매칭 템플릿): 없음
- 판정: 매칭 0건 → unknown
- 출력: `event_id=unknown`, `matched=False`
- 기대: `unknown` → **✅ PASS**

### S6b. unknown — near-miss

- 설명: 대소문자 1글자 차이도 ^...$ 엄격 매칭으로 불일치 (fuzzy 안 함)
- 입력: `instruction cache parity error CORRECTED`
- 후보(매칭 템플릿): 없음
- 판정: 매칭 0건 → unknown
- 출력: `event_id=unknown`, `matched=False`
- 기대: `unknown` → **✅ PASS**

### S7a. 엣지 — 앞뒤 공백

- 설명: strip 후 정상 매칭
- 입력: `   instruction cache parity error corrected   `
- 후보(매칭 템플릿): E77(ll=40,wc=0)
- 판정: 단일 매칭
- 출력: `event_id=E77`, `matched=True`
- 기대: `E77` → **✅ PASS**

### S7b. 엣지 — 빈 문자열

- 설명: 빈 입력 → unknown
- 입력: ``
- 후보(매칭 템플릿): 없음
- 판정: 매칭 0건 → unknown
- 출력: `event_id=unknown`, `matched=False`
- 기대: `unknown` → **✅ PASS**

### S8. 합성 — literal_len 동률

- 설명: ll 동률(6) → wildcard_count 적은 FEWWILD 선택 (2번 키)
- 입력: `a 1 b x c`
- 후보(매칭 템플릿): FEWWILD(ll=6,wc=1), MANYWILD(ll=6,wc=2)
- 판정: 다중 매칭 2개 → tie-break(literal_len↓, wildcard_count↑, event_id↑)
- 출력: `event_id=FEWWILD`, `matched=True`
- 기대: `FEWWILD` → **✅ PASS**

### S9. 합성 — catch-all 삼킴

- 설명: catch-all 이 다 삼켜도 literal_len 으로 구체 SPECIFIC 선택 (1번 키)
- 입력: `svc done: detail alpha beta`
- 후보(매칭 템플릿): SPECIFIC(ll=16,wc=2), CATCHALL(ll=9,wc=1)
- 판정: 다중 매칭 2개 → tie-break(literal_len↓, wildcard_count↑, event_id↑)
- 출력: `event_id=SPECIFIC`, `matched=True`
- 기대: `SPECIFIC` → **✅ PASS**

### S10. 합성 — 완전 동률

- 설명: 모든 키 동률 → event_id 오름차순으로 결정적 선택 (3번 키, 리스트순서 무관)
- 입력: `x foo`
- 후보(매칭 템플릿): E_AAA(ll=4,wc=1), E_ZZZ(ll=4,wc=1)
- 판정: 다중 매칭 2개 → tie-break(literal_len↓, wildcard_count↑, event_id↑)
- 출력: `event_id=E_AAA`, `matched=True`
- 기대: `E_AAA` → **✅ PASS**

