"""Streamlit 진입점. (주초현)

데이터 흐름: published/<seoul|national>/ (experiments.make_all 또는 publish가 만든 파일) → 화면.
화면은 실험이나 모델 학습을 직접 돌리지 않는다. API(api/)와 같은 파일을 같은 모듈(core/published.py)로
읽으므로 화면과 API의 숫자가 항상 같다. 결과 파일이 없으면 가상 데이터로 만들어 보여 주고 경고한다.

지도(이슈 #6), 후보지 비교(#9), 설명(#8)은 이 위에 붙인다. 성적표 그래프는 ui/scorecard.py(#4, 이민준).
"""

import tempfile
from pathlib import Path

import streamlit as st

from core import config
from core.published import Dataset, load_all, synthetic_fallback
from ui.map import render_area_map

LABELS = {"seoul": "서울판 (상권 단위)", "national": "전국판 (시군구 단위)", "synthetic": "가상 데이터"}

st.set_page_config(page_title="상권예보", page_icon="🗺️", layout="wide")
st.title("상권예보 (가칭)")
st.caption("이 동네에 이 가게를 차리면, 내년에 버틸 수 있을까? 성적을 공개하는 상권 위험 예측")


@st.cache_resource
def load_datasets(published_dir: str) -> dict[str, Dataset]:
    """결과 파일을 한 번만 읽는다. 없으면 임시 폴더에 가상 결과를 만든다."""
    found = load_all(Path(published_dir))
    if found:
        return found
    return synthetic_fallback(Path(tempfile.mkdtemp(prefix="sangkwon_synthetic_")))


datasets = load_datasets(str(config.PUBLISHED_DIR))
names = sorted(datasets, key=lambda n: ["national", "seoul", "synthetic"].index(n) if n in LABELS else 9)
choice = st.radio("데이터", names, format_func=lambda n: LABELS.get(n, n), horizontal=True)
ds = datasets[choice]

if ds.meta.get("source") == "synthetic":
    st.warning("실제 데이터가 없어 **가상 데이터**로 표시 중입니다. 숫자에 의미가 없습니다. "
               "`python -m experiments.make_all`로 실제 결과를 만드세요.")
st.caption(f"결과 생성: {ds.meta.get('built_at')} · 칸 {ds.meta.get('n_cells'):,}개")

# --- 1. 성적표: 숨기지 않는다(AGENTS.md). 그래프 버전은 #4에서 ui/scorecard.py로 교체 ---
st.subheader("1. 성적표: 과거를 얼마나 맞혔나")
st.write(ds.meta.get("gate_detail", ""))
st.dataframe(ds.scorecard.round(3), hide_index=True)

# --- 1-지도. 상권 위치를 예보 단계 색으로 표시한다 ---
# render(ds)가 생기면 그 아래로 옮긴다(이민준 님 PR 대기)
if ds.areas is None:
    st.info("지도 데이터가 아직 준비되지 않았습니다. 좌표 파일(areas.csv)이 필요합니다.")
else:
    map_industry = st.selectbox(
        "지도 업종",
        sorted(ds.scores["industry_name"].dropna().unique()),
        key="map_industry",
    )
    map_scores = ds.scores[ds.scores["industry_name"] == map_industry]
    map_df = map_scores.merge(ds.areas[["area_code", "lat", "lon"]], on="area_code", how="left")
    fig, n_dropped = render_area_map(map_df, industry_name=map_industry)
    if n_dropped > 0:
        st.caption(f"좌표가 없는 상권 {n_dropped}곳은 지도에서 제외했습니다.")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("자료: 서울시 상권분석서비스 · 과거 통계 기반 참고 정보이며 개별 점포의 성패를 보장하지 않습니다.")

# --- 2. 다음 해 위험: 미리 계산된 점수만 보여 준다 ---
scores = ds.scores
base_year = int(scores["base_year"].iloc[0])
st.subheader(f"2. {base_year + 1}년 예보: 같은 업종 안에서 폐업이 몰릴 가능성이 높은 곳")
industry = st.selectbox("업종", sorted(scores["industry_name"].dropna().unique()))
view = scores[scores["industry_name"] == industry].sort_values("rank_in_industry")
view = view.assign(rank_text=view["rank_in_industry"].astype(str) + " / " + view["n_in_industry"].astype(str))
st.dataframe(
    view[["area_name", "level", "rank_text", "close_rate", "close_rate_3y", "stores_avg"]].head(15).round(3),
    hide_index=True,
    column_config={
        "area_name": "지역", "level": "예보 단계", "rank_text": "업종 내 순위",
        "close_rate": f"{base_year}년 폐업률", "close_rate_3y": "3년 평균 폐업률", "stores_avg": "평균 점포 수",
    },
)
hit = ds.meta.get("caution_hit_rate", {})
if hit:
    last = hit[max(hit, key=int)]
    if last.get("hit_rate") is not None:
        st.caption(f"지난 시험({max(hit, key=int)}년 예보)에서 '주의'로 예보한 곳 중 "
                   f"{last['hit_rate']:.0%}가 실제로 다음 해 같은 업종 상위 25%였습니다 "
                   f"(아무 곳이나 골랐다면 {last['base_rate']:.0%}).")
st.caption(f"{base_year}년 말까지의 데이터로 {base_year + 1}년을 예측한 값입니다. {config.CAUTION_TEXT}")
