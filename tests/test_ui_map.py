"""ui/map.py 테스트 (이슈 #6, 주초현).

실제 Streamlit 실행 없이 Figure가 올바르게 만들어지는지 확인한다.
"""

import pandas as pd
import plotly.graph_objects as go

from ui.map import LEVEL_COLORS, LEVEL_ORDER, level_color, render_area_map


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """테스트용 최소 DataFrame을 만든다."""
    return pd.DataFrame(rows)


_BASE_ROW = {
    "area_code": "1",
    "area_name": "테스트상권",
    "lat": 37.5665,
    "lon": 126.9780,
    "level": "관심",
    "close_rate": 0.12,
    "stores_avg": 30,
    "rank_in_industry": 5,
    "n_in_industry": 20,
}


def test_render_returns_figure_and_int():
    """올바른 입력이면 Figure와 정수를 돌려준다."""
    df = _make_df([_BASE_ROW])
    result = render_area_map(df)
    fig, n_dropped = result
    assert isinstance(fig, go.Figure)
    assert isinstance(n_dropped, int)


def test_missing_coordinates_are_dropped_not_zeroed():
    """좌표가 없는 행은 0으로 채우지 않고 지도 점에서 제외한다."""
    rows = [
        {**_BASE_ROW, "area_code": "1", "lat": 37.5, "lon": 127.0},
        {**_BASE_ROW, "area_code": "2", "lat": None, "lon": 127.0},
        {**_BASE_ROW, "area_code": "3", "lat": 37.5, "lon": None},
    ]
    df = _make_df(rows)
    fig, n_dropped = render_area_map(df)
    assert n_dropped == 2
    # 지도에 찍힌 점은 1개여야 한다
    total_points = sum(len(t.lat) for t in fig.data if hasattr(t, "lat") and t.lat is not None)
    assert total_points == 1


def test_level_color_mapping():
    """예보 단계별 색이 AGENTS.md 규칙과 일치한다."""
    assert level_color("평이") == "#9AA0A6"
    assert level_color("관심") == "#E0A100"
    assert level_color("주의") == "#D9480F"
    # 알 수 없는 단계는 회색으로 처리한다
    assert level_color("미지정") == "#9AA0A6"


def test_all_levels_in_order():
    """LEVEL_ORDER가 평이→관심→주의 순서이고 LEVEL_COLORS에 모두 있다."""
    assert LEVEL_ORDER == ["평이", "관심", "주의"]
    for lv in LEVEL_ORDER:
        assert lv in LEVEL_COLORS


def test_score_not_in_hover():
    """점수 숫자(score, percentile)가 hover 텍스트에 포함되지 않는다."""
    row = {**_BASE_ROW, "score": 0.99, "percentile": 0.98}
    df = _make_df([row])
    fig, _ = render_area_map(df)
    hover_texts = []
    for trace in fig.data:
        if hasattr(trace, "customdata") and trace.customdata is not None:
            for item in trace.customdata:
                hover_texts.append(str(item))
    combined = " ".join(hover_texts)
    assert "0.99" not in combined
    assert "0.98" not in combined


def test_industry_name_appears_in_title():
    """industry_name을 넘기면 지도 제목에 포함된다."""
    df = _make_df([_BASE_ROW])
    fig, _ = render_area_map(df, industry_name="한식")
    assert "한식" in fig.layout.title.text
