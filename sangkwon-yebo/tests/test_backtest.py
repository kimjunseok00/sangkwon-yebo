import math

import pandas as pd
import pytest

from core import config
from core.schemas import FEATURES, RESULT_COLUMNS, TARGET
from experiments.backtest import evaluate, gate, run_backtest, split
from experiments.synthetic import make_panel
from features.build import build_dataset


@pytest.fixture(scope="module")
def synthetic_data():
    return build_dataset(make_panel(n_areas=40))


def test_split_has_no_future_rows(synthetic_data):
    for year in config.TEST_FEATURE_YEARS:
        train, test = split(synthetic_data, year)
        assert train["year"].max() <= year - 1
        assert (test["year"] == year).all()
        assert train[TARGET].notna().all() and test[TARGET].notna().all()


def test_evaluate_hand_case():
    y = pd.Series([1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
    s = pd.Series([0.9, 0.8, 0.7, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])
    r = evaluate(y, s, top_fraction=0.2)  # 상위 2칸: 1, 0
    assert r["precision_at_top"] == pytest.approx(0.5)
    assert r["recall_at_top"] == pytest.approx(0.5)
    assert r["base_rate"] == pytest.approx(0.2)
    assert r["lift_at_top"] == pytest.approx(2.5)


def test_evaluate_single_class_auc_is_nan():
    r = evaluate(pd.Series([0, 0, 0]), pd.Series([0.1, 0.2, 0.3]))
    assert math.isnan(r["auc"])


def test_run_backtest_shape(synthetic_data):
    res = run_backtest(synthetic_data)
    assert list(res.columns) == RESULT_COLUMNS
    assert set(res["method"]) == {"model", "baseline_last_year", "baseline_3y_avg"}
    assert set(res["test_year"]) == set(config.TEST_FEATURE_YEARS)


def test_gate_rule():
    rows = []
    for year, model_auc in [(2022, 0.70), (2023, 0.66), (2024, 0.64)]:
        rows += [
            {"test_year": year, "method": "model", "auc": model_auc},
            {"test_year": year, "method": "baseline_last_year", "auc": 0.65},
            {"test_year": year, "method": "baseline_3y_avg", "auc": 0.60},
        ]
    g = gate(pd.DataFrame(rows))
    # 이득 0.05, 0.01, -0.01 → 0.02 이상인 해는 1개 → 불통과
    assert g["years_won"] == 1 and g["passed"] is False


def test_features_exist_in_dataset(synthetic_data):
    assert set(FEATURES) <= set(synthetic_data.columns)
