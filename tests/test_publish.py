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


def test_publish_writes_three_files(data, tmp_path):
    meta = publish(data, tmp_path, "seoul", "synthetic")
    folder = tmp_path / "seoul"
    assert {p.name for p in folder.iterdir()} == {"scores.csv", "scorecard.csv", "meta.json"}
    assert json.loads((folder / "meta.json").read_text(encoding="utf-8"))["source"] == "synthetic"
    assert meta["n_cells"] == len(pd.read_csv(folder / "scores.csv"))
