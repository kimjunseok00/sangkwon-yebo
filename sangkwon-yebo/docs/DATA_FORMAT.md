# 데이터 형식과 함수 약속

실제 정의는 `core/schemas.py`이고, 둘이 다르면 코드가 기준이다.

## 흐름

```
서울시 CSV (data/raw)
  → ingest.seoul.load_store_files()   분기 패널: 상권 × 업종 × 분기
  → ingest.seoul.attach_sales()       (선택) 추정 매출 붙이기
  → features.build.to_annual()        연 단위: 상권 × 업종 × 연도 (4개 분기가 다 있는 해만)
  → features.build.add_features()     특징 (그 해 말까지 알 수 있는 값만)
  → features.build.add_target()       정답 risk_next (다음 해 업종 내 폐업률 상위 25%)
  → data/processed/dataset.csv
  → experiments.backtest.run_backtest()  연도별 모델 vs 기준선 2개 성적표
  → experiments.backtest.gate()          11/26 통과 판정
  → app.py                              성적표, 지도, 위험 상위 칸, 설명, 비교, 보고서
```

## 용어
- **칸**: 상권 하나 × 업종 하나 (`area_code`, `industry_code`)
- **예측 기준 연도 t**: 이 해 말까지의 정보로 예측한다. 맞히는 연도는 t+1
- **위험(risk_next=1)**: t+1년 폐업률이 같은 업종 칸들 중 상위 25% (`RISK_QUANTILE=0.75`)
- 연평균 점포 수가 `MIN_STORES`(5) 미만인 칸은 정답이 결측(평가 제외)

## 분기 패널 열 (ingest 출력)
`quarter_code`(20241), `year`, `quarter`, `area_code`, `area_name`, `area_type`, `industry_code`, `industry_name`, `stores`, `open_stores`, `close_stores`, `franchise_stores`, (선택) `sales_amount`

## 연 단위 표 열 (dataset.csv)
- 기본: `n_quarters`, `stores_avg`, `open_sum`, `close_sum`, `franchise_avg`, `close_rate`(=close_sum/stores_avg), `open_rate`, `franchise_share`, (선택) `sales_sum`, `sales_per_store`
- 특징(`FEATURES`): `close_rate`, `close_rate_prev`, `close_rate_3y`, `close_rate_rel`, `open_rate`, `store_growth`, `franchise_share`, `log_stores`, `industry_close_mean`, `sales_per_store_growth`
- 정답과 재료: `risk_next`, `next_close_rate`, `next_stores_avg`, `risk_threshold` ← **모델 입력 금지**

## 함수
| 함수 | 위치 | 입력 → 출력 |
|---|---|---|
| `load_store_files(paths, food_only=True)` | ingest.seoul | CSV 경로들 → 분기 패널 |
| `attach_sales(panel, paths)` | ingest.seoul | 패널 + 매출 CSV → 패널 |
| `load_area_coords(path)` | ingest.seoul | 영역 CSV → `area_code, lat, lon` (이슈 #5) |
| `build_dataset(panel)` | features.build | 분기 패널 → 실험용 표 |
| `fit(train)`, `predict_score(model, df)` | models.model | 학습 / 위험 확률 |
| `BASELINES` | models.baselines | 이름 → 점수 함수 (작년 폐업률, 3년 평균) |
| `run_backtest(data)` | experiments.backtest | 실험용 표 → 성적표 (`RESULT_COLUMNS`) |
| `gate(results)` | experiments.backtest | 성적표 → 통과 판정 dict |
| `explain(row, risk_score, top_factors)` | engine | → `LLMExplanation` |

## 분할 규칙 (누설 방지)
예측 기준 연도 T를 시험할 때 학습은 기준 연도 ≤ T-1 행만. T-1년 행의 정답은 T년 값이므로 T년 말에는 알 수 있다.
