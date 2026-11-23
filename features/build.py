"""분기 패널 → 연 단위 표 → 특징 + 정답.

가장 조심할 점은 미래 정보 누설이다. 예측 기준 연도 t의 특징은 t년 말까지 알 수 있는 값만 쓰고,
정답은 t+1년 값으로 만든다. 정답을 만든 재료(next_*)는 모델 입력에 넣지 않는다.
"""

import numpy as np
import pandas as pd

from core import config
from core.schemas import ANNUAL_BASE, KEYS, PANEL_REQUIRED, TARGET, require_columns


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    """분모가 0이거나 결측이면 결측으로 둔다(0으로 채우면 '폐업 없음'으로 오해된다)."""
    out = a / b.where(b > 0)
    return out.replace([np.inf, -np.inf], np.nan)


def to_annual(panel: pd.DataFrame) -> pd.DataFrame:
    """분기 패널을 칸 × 연도로 묶는다. 4개 분기가 다 있는 해만 남긴다."""
    require_columns(panel, PANEL_REQUIRED, "to_annual 입력")
    agg_spec = {
        "area_name": ("area_name", "first"),
        "area_type": ("area_type", "first"),
        "industry_name": ("industry_name", "first"),
        "n_quarters": ("quarter", "nunique"),
        "stores_avg": ("stores", "mean"),
        "open_sum": ("open_stores", "sum"),
        "close_sum": ("close_stores", "sum"),
        "franchise_avg": ("franchise_stores", "mean"),
    }
    has_sales = "sales_amount" in panel.columns
    if has_sales:
        # min_count=1: 매출이 전부 결측이면 합을 0이 아니라 결측으로 둔다
        agg_spec["sales_sum"] = ("sales_amount", lambda s: s.sum(min_count=1))
    annual = panel.groupby(KEYS + ["year"], as_index=False).agg(**agg_spec)
    # 분기가 빠진 해(예: 올해처럼 진행 중인 해)는 연간 폐업률이 낮게 나오므로 뺀다
    annual = annual[annual["n_quarters"] == 4].copy()

    annual["close_rate"] = _safe_div(annual["close_sum"], annual["stores_avg"])
    annual["open_rate"] = _safe_div(annual["open_sum"], annual["stores_avg"])
    annual["franchise_share"] = _safe_div(annual["franchise_avg"], annual["stores_avg"])
    if has_sales:
        annual["sales_per_store"] = _safe_div(annual["sales_sum"], annual["stores_avg"])
    return annual.reset_index(drop=True)


def _lag(annual: pd.DataFrame, cols: list[str], years: int, suffix: str) -> pd.DataFrame:
    """같은 칸의 years년 전 값을 붙인다. 행 순서가 아니라 연도로 맞춰서 빠진 해가 있어도 틀리지 않게 한다."""
    prev = annual[KEYS + ["year"] + cols].copy()
    prev["year"] = prev["year"] + years
    prev = prev.rename(columns={c: f"{c}{suffix}" for c in cols})
    return annual.merge(prev, on=KEYS + ["year"], how="left")


def add_features(annual: pd.DataFrame) -> pd.DataFrame:
    """연 단위 표에 모델 특징을 붙인다. 모두 그 해 말까지 알 수 있는 값이다."""
    require_columns(annual, ANNUAL_BASE, "add_features 입력")
    df = annual.copy()
    lag_cols = ["close_rate", "stores_avg"] + (["sales_per_store"] if "sales_per_store" in df else [])
    df = _lag(df, lag_cols, 1, "_lag1")
    df = _lag(df, ["close_rate"], 2, "_lag2")

    df["close_rate_prev"] = df["close_rate_lag1"]
    df["close_rate_3y"] = df[["close_rate", "close_rate_lag1", "close_rate_lag2"]].mean(axis=1, skipna=True)
    df["store_growth"] = _safe_div(df["stores_avg"], df["stores_avg_lag1"]) - 1
    df["log_stores"] = np.log1p(df["stores_avg"])
    # 업종 평균은 '점포가 충분한 칸'만으로 계산한다. 작은 칸의 튀는 값이 평균을 흔들지 않게.
    big = df["stores_avg"] >= config.MIN_STORES
    ind_mean = (
        df[big].groupby(["industry_code", "year"])["close_rate"].mean().rename("industry_close_mean")
    )
    df = df.merge(ind_mean, on=["industry_code", "year"], how="left")
    df["close_rate_rel"] = df["close_rate"] - df["industry_close_mean"]
    if "sales_per_store" in df:
        df["sales_per_store_growth"] = _safe_div(df["sales_per_store"], df["sales_per_store_lag1"]) - 1
    else:
        df["sales_per_store_growth"] = np.nan
    return df


def add_target(df: pd.DataFrame) -> pd.DataFrame:
    """다음 해 폐업률이 같은 업종 안에서 상위 (1-RISK_QUANTILE)인지 정답을 붙인다.

    - 올해나 다음 해 점포가 MIN_STORES 미만인 칸은 정답을 결측으로 둔다(평가에서 빠짐).
    - 다음 해 데이터가 없는 마지막 해도 정답이 결측이다. 이 행은 '실제 예측' 화면에 쓴다.
    """
    nxt = df[KEYS + ["year", "close_rate", "stores_avg"]].copy()
    nxt["year"] = nxt["year"] - 1  # t+1년 값을 t년 행에 붙이기 위해
    nxt = nxt.rename(columns={"close_rate": "next_close_rate", "stores_avg": "next_stores_avg"})
    out = df.merge(nxt, on=KEYS + ["year"], how="left")

    eligible = (
        (out["stores_avg"] >= config.MIN_STORES)
        & (out["next_stores_avg"] >= config.MIN_STORES)
        & out["next_close_rate"].notna()
    )
    # 기준선은 '맞히는 연도·업종'마다 따로 잡는다
    thresholds = (
        out[eligible]
        .groupby(["industry_code", "year"])["next_close_rate"]
        .quantile(config.RISK_QUANTILE)
        .rename("risk_threshold")
    )
    out = out.merge(thresholds, on=["industry_code", "year"], how="left")
    out[TARGET] = np.where(
        eligible, (out["next_close_rate"] >= out["risk_threshold"]).astype(float), np.nan
    )
    return out


def build_dataset(panel: pd.DataFrame) -> pd.DataFrame:
    """분기 패널 하나로 실험용 표 전체를 만든다."""
    return add_target(add_features(to_annual(panel)))
