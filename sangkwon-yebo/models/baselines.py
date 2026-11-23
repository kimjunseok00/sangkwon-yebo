"""모델이 이겨야 하는 기준선 2개. 학습이 필요 없는 규칙이다.

기준선이 강할수록 '모델이 더 낫다'는 주장이 의미 있어진다. 일부러 약하게 만들지 않는다.
"""

import pandas as pd


def _z_within(df: pd.DataFrame, col: str) -> pd.Series:
    """같은 업종·연도 안에서의 z점수. 정답이 '업종 내 상위 25%'이므로 비교도 업종 안에서 한다."""
    grp = df.groupby(["industry_code", "year"])[col]
    std = grp.transform("std").where(lambda s: s > 0)
    return (df[col] - grp.transform("mean")) / std


def score_last_year(df: pd.DataFrame) -> pd.Series:
    """기준선 1: 올해 폐업률이 높으면 내년에도 높다."""
    return _z_within(df, "close_rate").fillna(0.0)


def score_3y_avg(df: pd.DataFrame) -> pd.Series:
    """기준선 2: 최근 3년 평균 폐업률. 서울시 창업위험도(과거 폐업률·생존율 요약)에 가까운 방식.

    서울시 지표는 1~3년 생존율도 쓰지만 공개 CSV에서 칸 단위 생존율을 구할 수 있는지 확인되지 않아
    폐업률 부분만 따라 했다. 생존율을 구하면 docs/EXPERIMENTS.md에 기록하고 추가한다.
    """
    return _z_within(df, "close_rate_3y").fillna(0.0)


BASELINES = {
    "baseline_last_year": score_last_year,
    "baseline_3y_avg": score_3y_avg,
}
