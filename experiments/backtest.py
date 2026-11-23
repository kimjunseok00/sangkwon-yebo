"""연도별 과거 맞히기 실험과 11/26 통과 판정.

분할 규칙(누설 방지):
  예측 기준 연도 T를 시험할 때, 학습에는 기준 연도 ≤ T-1인 행만 쓴다.
  기준 연도 T-1 행의 정답은 T년 값이라, T년 말(=예측하는 시점)에는 이미 알 수 있다.

실행: python -m experiments.backtest --data data/processed/dataset.csv
       python -m experiments.backtest --synthetic   (가상 데이터로 코드 점검)
"""

import argparse
import math

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from core import config
from core.schemas import RESULT_COLUMNS, TARGET
from models import model as model_mod
from models.baselines import BASELINES


def split(data: pd.DataFrame, test_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """학습: 기준 연도 ≤ test_year-1 이고 정답 있음 / 시험: 기준 연도 == test_year 이고 정답 있음."""
    labeled = data[data[TARGET].notna()]
    train = labeled[labeled["year"] <= test_year - 1]
    test = labeled[labeled["year"] == test_year]
    return train, test


def evaluate(y: pd.Series, score: pd.Series, top_fraction: float = config.TOP_FRACTION) -> dict:
    """AUC와 '상위 경고' 성적. 상위 경고 = 점수 상위 top_fraction 칸."""
    y = y.astype(int).to_numpy()
    s = score.to_numpy()
    n = len(y)
    base = float(y.mean()) if n else math.nan
    auc = roc_auc_score(y, s) if 0 < y.sum() < n else math.nan
    k = max(1, math.ceil(n * top_fraction))
    top = np.argsort(-s, kind="stable")[:k]
    hits = int(y[top].sum())
    precision = hits / k
    recall = hits / y.sum() if y.sum() else math.nan
    return {
        "n": n,
        "base_rate": base,
        "auc": auc,
        "precision_at_top": precision,
        "recall_at_top": recall,
        "lift_at_top": precision / base if base else math.nan,
    }


def run_backtest(data: pd.DataFrame, test_years=config.TEST_FEATURE_YEARS) -> pd.DataFrame:
    """시험 연도마다 모델과 기준선 2개를 같은 시험 행으로 채점한다."""
    rows = []
    for year in test_years:
        train, test = split(data, year)
        if test.empty or train.empty:
            continue
        scores = {name: fn(test) for name, fn in BASELINES.items()}
        fitted = model_mod.fit(train)
        scores["model"] = model_mod.predict_score(fitted, test)
        for method, s in scores.items():
            rows.append({"test_year": year, "target_year": year + 1, "method": method,
                         **evaluate(test[TARGET], s)})
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def predict_test_year(data: pd.DataFrame, test_year: int) -> pd.DataFrame:
    """run_backtest와 같은 분할(학습 ≤ test_year-1)로 학습해, 시험 행에 모델 점수(score)를 붙여 돌려준다.

    타임머신 화면(history.csv)용. 채점 규칙은 run_backtest와 같고, 결과 표 대신 칸별 예측을 남긴다.
    """
    train, test = split(data, test_year)
    if test.empty or train.empty:
        return test.assign(score=pd.Series(dtype=float))
    fitted = model_mod.fit(train)
    return test.assign(score=model_mod.predict_score(fitted, test))


def gate(results: pd.DataFrame) -> dict:
    """11/26 통과 판정. 규칙은 core/config.py와 docs/EXPERIMENTS.md에 미리 적어 둔 것만 쓴다."""
    if results.empty:
        return {"passed": False, "years_won": 0, "detail": "결과 없음", "per_year": {}}
    pivot = results.pivot(index="test_year", columns="method", values="auc")
    best_baseline = pivot[list(BASELINES)].max(axis=1)
    gain = pivot["model"] - best_baseline
    won = int((gain >= config.GATE_MIN_AUC_GAIN).sum())
    return {
        "passed": won >= config.GATE_MIN_YEARS,
        "years_won": won,
        "per_year": {int(y): round(float(g), 4) for y, g in gain.items()},
        "detail": (
            f"모델 AUC가 더 나은 기준선보다 {config.GATE_MIN_AUC_GAIN} 이상 높은 연도: "
            f"{won}/{len(gain)} (필요 {config.GATE_MIN_YEARS})"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="build_dataset 결과 CSV")
    parser.add_argument("--synthetic", action="store_true", help="가상 데이터로 실행")
    args = parser.parse_args()
    if args.synthetic:
        from experiments.synthetic import make_panel
        from features.build import build_dataset
        data = build_dataset(make_panel())
        print("※ 가상 데이터 결과입니다. 발표나 판정에 쓰지 마세요.")
    else:
        data = pd.read_csv(args.data)
    results = run_backtest(data)
    pd.set_option("display.width", 160)
    print(results.round(3).to_string(index=False))
    print(gate(results))


if __name__ == "__main__":
    main()
