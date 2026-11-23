"""전부 결측인 특징(전국판의 프랜차이즈·매출)이 있어도 학습·예측이 된다."""

import numpy as np

from experiments.synthetic import make_panel
from features.build import build_dataset
from models.model import fit, predict_score


def test_all_missing_feature_is_skipped():
    data = build_dataset(make_panel(n_areas=20))
    data["franchise_share"] = np.nan
    data["sales_per_store_growth"] = np.nan
    model = fit(data)
    assert "franchise_share" not in model.used_features_
    score = predict_score(model, data)
    assert score.between(0, 1).all()
