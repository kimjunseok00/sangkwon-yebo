"""집계·특징·정답 규칙을 손으로 계산한 값과 대조한다. 이 테스트가 깨지면 실험 결과가 바뀐다."""

import numpy as np
import pandas as pd
import pytest

from core.schemas import FEATURES, TARGET, TARGET_HELPERS
from features.build import add_features, add_target, to_annual


def _panel(rows):
    """(area, year, quarters, stores, close_per_quarter) 목록으로 분기 패널을 만든다."""
    out = []
    for area, year, quarters, stores, close in rows:
        for q in quarters:
            out.append({
                "quarter_code": year * 10 + q, "year": year, "quarter": q,
                "area_code": area, "area_name": area, "area_type": "골목상권",
                "industry_code": "I1", "industry_name": "한식음식점",
                "stores": stores, "open_stores": 1, "close_stores": close, "franchise_stores": 2,
            })
    return pd.DataFrame(out)


Q4 = [1, 2, 3, 4]


def test_annual_close_rate_and_incomplete_year_dropped():
    panel = _panel([("A", 2020, Q4, 10, 1), ("A", 2021, [1, 2, 3], 10, 1)])
    annual = to_annual(panel)
    assert list(annual["year"]) == [2020]  # 분기 3개뿐인 2021년은 빠진다
    row = annual.iloc[0]
    assert row["close_sum"] == 4 and row["stores_avg"] == 10
    assert row["close_rate"] == pytest.approx(0.4)
    assert row["franchise_share"] == pytest.approx(0.2)


def test_lag_uses_year_not_row_order():
    # 2021년이 빠져 있으면 2022년의 '작년 폐업률'은 결측이어야 한다(2020년 값을 가져오면 안 됨)
    panel = _panel([("A", 2020, Q4, 10, 1), ("A", 2022, Q4, 10, 2)])
    feats = add_features(to_annual(panel))
    r2022 = feats[feats["year"] == 2022].iloc[0]
    assert np.isnan(r2022["close_rate_prev"])


def test_target_is_top_quartile_within_industry_next_year():
    rows = []
    for area, rate_2021 in zip("ABCD", [1, 2, 3, 4]):  # 2021년 분기당 폐업 수 = 연 폐업률 × 10 / 4
        rows.append((area, 2020, Q4, 10, 1))
        rows.append((area, 2021, Q4, 10, rate_2021))
    data = add_target(add_features(to_annual(_panel(rows))))
    y2020 = data[data["year"] == 2020].set_index("area_code")
    # 2021년 폐업률 0.4, 0.8, 1.2, 1.6 → 75% 분위수 1.3 → D만 위험
    assert y2020[TARGET].to_dict() == {"A": 0.0, "B": 0.0, "C": 0.0, "D": 1.0}
    # 마지막 해(2021)는 다음 해가 없으므로 정답이 결측
    assert data[data["year"] == 2021][TARGET].isna().all()


def test_small_cells_excluded_from_target():
    rows = [("A", 2020, Q4, 3, 0), ("A", 2021, Q4, 3, 1)]  # 점포 3개 < MIN_STORES
    data = add_target(add_features(to_annual(_panel(rows))))
    assert data[TARGET].isna().all()


def test_target_materials_not_used_as_features():
    assert not set(TARGET_HELPERS) & set(FEATURES)
    assert TARGET not in FEATURES
