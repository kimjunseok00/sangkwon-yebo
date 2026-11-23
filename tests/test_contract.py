from core.schemas import PANEL_REQUIRED
from engine import mock
from experiments.synthetic import make_panel


def test_synthetic_panel_follows_schema():
    panel = make_panel(n_areas=3, years=range(2019, 2021))
    assert set(PANEL_REQUIRED) <= set(panel.columns)
    assert (panel["stores"] >= panel["close_stores"]).all()


def test_mock_explanation_has_caution():
    e = mock.explain({"area_name": "A", "industry_name": "치킨"}, 0.8, [("close_rate", 0.3)])
    assert e.reasons and "보장하지 않습니다" in e.caution
