"""서울 상권 점 지도. (이슈 #6, 주초현)

render_area_map(df)을 호출하면 Plotly scatter_map Figure와 제외된 행 수를 돌려준다.
입력 df는 scores와 areas를 area_code로 합쳐 업종으로 필터링한 표여야 한다.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# 예보 단계 → 색 (AGENTS.md 화면 스타일 규칙)
LEVEL_COLORS: dict[str, str] = {
    "평이": "#9AA0A6",
    "관심": "#E0A100",
    "주의": "#D9480F",
}
# 범례가 평이 → 관심 → 주의 순서로 나오게 고정
LEVEL_ORDER = ["평이", "관심", "주의"]

# 서울 시청 근처
_CENTER_LAT = 37.5665
_CENTER_LON = 126.9780
_ZOOM = 10


def level_color(level: str) -> str:
    """예보 단계 문자열을 색 코드로 바꾼다. 알 수 없는 단계는 회색으로 처리한다."""
    return LEVEL_COLORS.get(level, "#9AA0A6")


def render_area_map(
    df: pd.DataFrame,
    industry_name: str | None = None,
) -> tuple[go.Figure, int]:
    """상권 중심 좌표를 예보 단계 색으로 점 지도에 그린다.

    입력 df는 scores와 areas를 area_code로 합친 표여야 한다.
    필수 열: area_code, area_name, lat, lon, level,
             close_rate, stores_avg, rank_in_industry, n_in_industry.

    score·percentile 같은 점수 숫자는 hover에 표시하지 않는다(AGENTS.md).
    좌표가 없는 행은 0으로 채우지 않고 제외한다(결측 ≠ 0).

    반환: (Plotly Figure, 좌표 결측으로 제외된 행 수).
    """
    # 좌표가 없는 행 제외 — 결측을 0으로 채우지 않는다
    valid = df["lat"].notna() & df["lon"].notna()
    n_dropped = int((~valid).sum())
    plot_df = df[valid].copy()

    # 단계 열을 카테고리로 고정해 색 순서를 보장한다
    plot_df["level"] = pd.Categorical(plot_df["level"], categories=LEVEL_ORDER, ordered=True)
    plot_df = plot_df.sort_values("level")

    # hover 텍스트를 미리 만든다 — 점수 숫자(score, percentile)는 넣지 않는다
    plot_df = plot_df.assign(
        _hover=(
            plot_df["area_name"]
            + "<br>예보 단계: " + plot_df["level"].astype(str)
            + "<br>업종 내 순위: " + plot_df["rank_in_industry"].astype(str)
            + " / " + plot_df["n_in_industry"].astype(str)
            + "<br>올해 폐업률: " + (plot_df["close_rate"] * 100).round(1).astype(str) + "%"
            + "<br>평균 점포 수: " + plot_df["stores_avg"].round(0).astype(int).astype(str)
        )
    )

    title = "서울 상권 예보 지도"
    if industry_name:
        title += f"  |  {industry_name}"

    fig = px.scatter_map(
        plot_df,
        lat="lat",
        lon="lon",
        color="level",
        color_discrete_map=LEVEL_COLORS,
        category_orders={"level": LEVEL_ORDER},
        hover_name="area_name",
        custom_data=["_hover"],
        zoom=_ZOOM,
        center={"lat": _CENTER_LAT, "lon": _CENTER_LON},
        title=title,
        height=550,
    )
    # hover 내용을 _hover 열로 교체한다
    fig.update_traces(hovertemplate="%{customdata[0]}<extra></extra>")
    fig.update_layout(
        margin={"r": 0, "t": 40, "l": 0, "b": 0},
        legend_title_text="예보 단계",
        font_family="Pretendard, sans-serif",
    )
    return fig, n_dropped
