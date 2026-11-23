"""Streamlit 진입점. (주초현)

지금은 뼈대 확인용 최소 화면이다: 데이터(없으면 가상) → 성적표 → 업종별 위험 상위 칸.
지도(이슈 #6), 후보지 비교(#9), 설명(#8), 금융기관 보고서(#10)는 이 위에 붙인다.
"""

import pandas as pd
import streamlit as st

from core import config
from core.schemas import FEATURES, TARGET
from experiments.backtest import gate, run_backtest
from features.build import build_dataset
from models import model as model_mod

DATASET = config.PROCESSED_DIR / "dataset.csv"

st.set_page_config(page_title="상권예보", page_icon="🗺️", layout="wide")
st.title("상권예보 (가칭)")
st.caption("이 동네에 이 가게를 차리면, 내년에 버틸 수 있을까? 성적을 공개하는 상권 위험 예측")


@st.cache_data
def load() -> tuple[pd.DataFrame, bool]:
    if DATASET.exists():
        return pd.read_csv(DATASET), False
    from experiments.synthetic import make_panel
    return build_dataset(make_panel()), True


data, is_synthetic = load()
if is_synthetic:
    st.warning("실제 데이터가 없어 **가상 데이터**로 표시 중입니다. 숫자에 의미가 없습니다.")

st.subheader("1. 성적표: 과거를 얼마나 맞혔나")
results = run_backtest(data)
st.dataframe(results.round(3), hide_index=True)
st.write(gate(results)["detail"])

st.subheader("2. 내년 위험 상위 칸")
latest = int(data["year"].max())
fitted = model_mod.fit(data[data[TARGET].notna()])
now = data[(data["year"] == latest) & (data["stores_avg"] >= config.MIN_STORES)].copy()
now["risk_score"] = model_mod.predict_score(fitted, now, FEATURES)
industry = st.selectbox("업종", sorted(now["industry_name"].unique()))
view = now[now["industry_name"] == industry].sort_values("risk_score", ascending=False)
st.dataframe(
    view[["area_name", "area_type", "stores_avg", "close_rate", "risk_score"]].head(15).round(3),
    hide_index=True,
)
st.caption(f"{latest}년 말 기준 특징으로 {latest + 1}년을 예측한 값입니다.")
