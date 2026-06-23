# anomaly_classifier 정확도 검증 리포트

- 데이터: `tests/BGL/BGL_2k.log_structured.csv` FATAL-level 347건

- 파이프라인: Content → Tool①(extract_event_template) → Tool②(classify_anomaly)

- 정답 기준: `Label != "-"` → is_anomaly=True


## 지표

| 지표 | 값 |
|---|---|
| Accuracy | **100.0%** (347/347) |
| Precision | 100.0% |
| Recall | 100.0% |
| F1 Score | 1.000 |

## 혼동 행렬

| | 예측 정상 | 예측 비정상 |
|---|---|---|
| **실제 정상** | TN=204 | FP=0 |
| **실제 비정상** | FN=0 | TP=143 |
