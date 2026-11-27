"""성적표와 타임머신 화면을 그린다."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import config
from core.published import Dataset
from core.schemas import RESULT_COLUMNS

_METHOD_LABELS = {
    "model": "모델",
    "baseline_last_year": "작년 폐업률 기준선",
    "baseline_3y_avg": "최근 3년 평균 기준선",
}
_METHOD_COLORS = {
    "model": "#404040",
    "baseline_last_year": "#9AA0A6",
    "baseline_3y_avg": "#D0D0D0",
}
_LEVEL_COLORS = {"평이": "#9AA0A6", "관심": "#E0A100", "주의": "#D9480F"}
_HISTORY_COLUMNS = {
    "base_year", "area_code", "area_name", "area_type", "industry_code",
    "industry_name", "rank_in_industry", "n_in_industry", "level",
    "close_rate", "actual_caution",
}


def _metric_chart(results: pd.DataFrame, metric: str, title: str, percent: bool) -> go.Figure:
    """성적표의 한 지표를 연도별 그룹 막대그래프로 만든다."""
    fig = go.Figure()
    present_methods = results["method"].drop_duplicates().tolist()
    methods = [method for method in _METHOD_LABELS if method in present_methods]
    methods.extend(method for method in present_methods if method not in _METHOD_LABELS)
    for method in methods:
        rows = results[results["method"] == method].sort_values("test_year")
        values = pd.to_numeric(rows[metric], errors="coerce")
        text = [
            f"{value:.1%}" if percent else f"{value:.3f}"
            for value in values
        ]
        fig.add_trace(go.Bar(
            name=_METHOD_LABELS.get(method, str(method)),
            x=rows["test_year"].astype(int).astype(str),
            y=values,
            text=text,
            textposition="outside",
            marker_color=_METHOD_COLORS.get(method, "#707070"),
            hovertemplate=(
                "예측 기준 연도 %{x}<br>" + title + ": %{y:.1%}<extra>%{fullData.name}</extra>"
                if percent else
                "예측 기준 연도 %{x}<br>" + title + ": %{y:.3f}<extra>%{fullData.name}</extra>"
            ),
        ))
    fig.update_layout(
        title=title,
        barmode="group",
        bargap=0.2,
        margin={"l": 8, "r": 8, "t": 48, "b": 8},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        xaxis_title="예측 기준 연도",
        yaxis_title=title,
        yaxis={"range": [0, 1], "tickformat": ".0%" if percent else ".2f"},
        template="plotly_white",
    )
    return fig


def _render_history(ds: Dataset) -> None:
    """타임머신에서 과거 예보를 고르고 정답을 직접 공개한다."""
    st.subheader("타임머신: 그해의 예보와 다음 해 결과")
    history = ds.history
    if history is None or history.empty:
        st.info("타임머신 기록이 없습니다.")
        return

    missing = _HISTORY_COLUMNS - set(history.columns)
    if missing:
        raise ValueError(f"타임머신 기록에 필요한 열이 없습니다: {sorted(missing)}")

    years = sorted(pd.to_numeric(history["base_year"], errors="raise").astype(int).unique())
    year = st.selectbox("예측 기준 연도", years, index=len(years) - 1, key=f"{ds.name}-history-year")
    by_year = history[pd.to_numeric(history["base_year"], errors="raise") == year]
    industries = (
        by_year[["industry_code", "industry_name"]]
        .drop_duplicates()
        .sort_values("industry_name")
    )
    industry_codes = industries["industry_code"].tolist()
    industry_names = dict(zip(industries["industry_code"], industries["industry_name"]))
    industry_code = st.selectbox(
        "업종",
        industry_codes,
        format_func=lambda code: industry_names[code],
        key=f"{ds.name}-{year}-history-industry",
    )
    by_industry = by_year[by_year["industry_code"] == industry_code]
    areas = (
        by_industry[["area_code", "area_name", "area_type"]]
        .drop_duplicates("area_code")
        .sort_values("area_name")
    )
    area_options = [
        (row.area_code, row.area_name, row.area_type)
        for row in areas.itertuples(index=False)
    ]
    area_code, area_name, _ = st.selectbox(
        "지역",
        area_options,
        format_func=lambda area: f"{area[1]} ({area[2]})",
        key=f"{ds.name}-{year}-{industry_code}-history-area",
    )
    selected = by_industry[by_industry["area_code"] == area_code]
    if selected.empty:
        st.info("선택한 조건의 예보 기록이 없습니다.")
        return
    row = selected.iloc[0]

    level = str(row["level"])
    color = _LEVEL_COLORS.get(level, "#9AA0A6")
    st.markdown(
        f'<div style="border-left: 8px solid {color}; padding: 8px 12px; '
        f'font-size: 1.25rem; font-weight: 600;">{level}</div>',
        unsafe_allow_html=True,
    )
    st.write(
        f"{year}년 말 예보 · {area_name} · {industry_names[industry_code]} · "
        f"같은 업종 {int(row['n_in_industry'])}곳 중 {int(row['rank_in_industry'])}번째"
    )
    close_rate = row["close_rate"]
    if pd.isna(close_rate):
        st.caption("예보 시점의 폐업률: 자료 없음")
    else:
        st.caption(f"예보 시점의 폐업률: {float(close_rate):.1%}")

    hit_rates = ds.meta.get("caution_hit_rate", {})
    summary = hit_rates.get(str(year), hit_rates.get(year, {}))
    if summary and summary.get("hit_rate") is not None and summary.get("base_rate") is not None:
        st.caption(
            f"그해 '주의' 예보 중 실제 적중 {summary['hit_rate']:.1%} "
            f"(아무 곳이나 골랐다면 {summary['base_rate']:.1%})"
        )
    else:
        st.caption("그해 '주의' 예보의 적중률 집계가 없습니다.")

    if st.button(
        "정답 공개",
        key=f"{ds.name}-{year}-{industry_code}-{area_code}-reveal",
    ):
        actual = row["actual_caution"]
        target_year = year + 1
        if pd.isna(actual):
            st.info(f"{target_year}년 실제 결과가 기록되어 있지 않습니다.")
        elif int(actual) == 1:
            st.write(f"{target_year}년 실제: 같은 업종 폐업률 상위 25%였음")
        else:
            st.write(f"{target_year}년 실제: 같은 업종 폐업률 상위 25%가 아니었음")


def render_scorecard(ds: Dataset) -> None:
    """연도별 성적 그래프와 타임머신을 표시한다.

    Args:
        ds: core.published.load_all()이 읽은 데이터셋.
    """
    st.subheader("성적표: 과거를 얼마나 맞혔나")
    results = ds.scorecard
    if results.empty:
        st.info("성적표 기록이 없습니다.")
    else:
        missing = set(RESULT_COLUMNS) - set(results.columns)
        if missing:
            raise ValueError(f"성적표에 필요한 열이 없습니다: {sorted(missing)}")
        results = results.copy()
        results["test_year"] = pd.to_numeric(results["test_year"], errors="raise")

        st.write(ds.meta.get("gate_detail", ""))
        auc_col, precision_col = st.columns(2)
        with auc_col:
            st.plotly_chart(
                _metric_chart(results, "auc", "AUC", percent=False),
                width="stretch",
            )
        with precision_col:
            st.plotly_chart(
                _metric_chart(results, "precision_at_top", "상위 10% 경고 정밀도", percent=True),
                width="stretch",
            )
        st.caption("모델이 기준선보다 낮은 해도 포함한 전체 시험 결과입니다.")

    _render_history(ds)
    source = {
        "seoul": "서울시 상권분석서비스",
        "national": "행정안전부 지방행정 인허가 데이터",
        "synthetic": "가상 데이터",
    }.get(ds.name, ds.name)
    st.caption(f"자료: {source} · 결과 생성: {ds.meta.get('built_at', '기준일 정보 없음')}")
    st.caption(config.CAUTION_TEXT)
