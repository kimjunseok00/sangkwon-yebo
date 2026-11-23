"""서비스용 결과 만들기 테스트: 정답 없는 최신 연도에만 점수를 매기고, 미래 정보가 섞이지 않는다."""

import json

import pandas as pd
import pytest

from core.schemas import SCORE_COLUMNS, TARGET
from experiments.publish import latest_scores, publish
from experiments.synthetic import make_panel
from features.build import build_dataset


@pytest.fixture(scope="module")
def data():
    return build_dataset(make_panel(n_areas=30))


def test_scores_only_for_unlabeled_latest_year(data):
    scores = latest_scores(data)
    latest = data["year"].max()
    assert list(scores.columns) == SCORE_COLUMNS
    assert (scores["base_year"] == latest).all()
    assert data.loc[data["year"] == latest, TARGET].isna().all()  # 최신 연도는 정답이 없어야 한다
    assert scores["percentile"].between(0, 1).all()


def test_refuses_when_no_future_year(data):
    labeled_only = data[data[TARGET].notna()]
    with pytest.raises(ValueError):
        latest_scores(labeled_only)


def test_publish_writes_result_files(data, tmp_path):
    meta = publish(data, tmp_path, "seoul", "synthetic")
    folder = tmp_path / "seoul"
    assert {p.name for p in folder.iterdir()} == {"scores.csv", "scorecard.csv", "history.csv", "meta.json"}
    assert json.loads((folder / "meta.json").read_text(encoding="utf-8"))["source"] == "synthetic"
    assert meta["n_cells"] == len(pd.read_csv(folder / "scores.csv"))


def test_forecast_levels_and_rank(data):
    scores = latest_scores(data)
    assert set(scores["level"]) <= {"평이", "관심", "주의"}
    for _, g in scores.groupby("industry_code"):
        assert sorted(g["rank_in_industry"]) == list(range(1, len(g) + 1))  # 1부터 빠짐없이
        top = g.sort_values("rank_in_industry").iloc[0]
        assert top["level"] == "주의" and (g["n_in_industry"] == len(g)).all()


def test_history_uses_only_past_and_matches_truth(data):
    """타임머신 예보는 시험 연도별 분할과 같고, 실제 결과는 정답(risk_next)과 같다."""
    from core import config
    from experiments.publish import caution_hit_rate, history

    hist = history(data)
    assert set(hist["base_year"]) == set(config.TEST_FEATURE_YEARS)
    assert (hist["target_year"] == hist["base_year"] + 1).all()
    merged = hist.merge(data[["area_code", "industry_code", "year", TARGET]],
                        left_on=["area_code", "industry_code", "base_year"],
                        right_on=["area_code", "industry_code", "year"])
    assert (merged["actual_caution"] == merged[TARGET]).all()
    rates = caution_hit_rate(hist)
    assert all(0 <= r["base_rate"] <= 1 for r in rates.values())
