"""전국판 데이터를 믿어도 되는지 확인: 서울에서 두 출처의 폐업률이 같은 방향으로 움직이는가.

서울시 상권분석서비스(서울판)와 인허가 데이터(전국판)는 출처가 다르다.
서울만 떼어 '업종 × 연도'별 폐업률을 두 출처로 각각 계산하고 순위 상관을 본다.
상관이 높으면 '인허가로 계산한 폐업률이 공식 통계와 같은 것을 재고 있다'는 근거가 된다.
판정 기준은 docs/EXPERIMENTS.md의 '#18 전국판 판정'에 결과를 보기 전에 적어 둔다.

실행: python -m experiments.crosscheck --seoul data/processed/dataset.csv --national data/processed/national_dataset.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ingest.localdata import SEOUL_CROSSWALK


def citywide_close_rate(annual: pd.DataFrame, area_filter: pd.Series | None = None) -> pd.DataFrame:
    """칸별 연 단위 표 → 업종 × 연도 합계 폐업률(폐업 합 / 평균 점포 수 합)."""
    df = annual if area_filter is None else annual[area_filter]
    g = df.groupby(["industry_name", "year"], as_index=False)[["close_sum", "stores_avg"]].sum()
    g["close_rate"] = g["close_sum"] / g["stores_avg"]
    return g[["industry_name", "year", "close_rate"]]


def compare(seoul_annual: pd.DataFrame, national_annual: pd.DataFrame) -> dict:
    """서울판과 전국판(서울 부분)의 업종 × 연도 폐업률 순위 상관."""
    seoul = citywide_close_rate(seoul_annual)
    in_seoul = national_annual["area_name"].fillna("").str.startswith("서울")
    nat = national_annual[in_seoul].copy()
    # 전국판 업종 이름을 서울판 이름으로 바꾼다. 대응표에 없는 업종(호프·뷔페 등)은 비교에서 뺀다.
    code_to_seoul = nat["industry_code"].map(SEOUL_CROSSWALK)
    nat = nat[code_to_seoul.notna()].assign(industry_name=code_to_seoul[code_to_seoul.notna()])
    nat = citywide_close_rate(nat)

    both = seoul.merge(nat, on=["industry_name", "year"], suffixes=("_seoul", "_national"))
    if len(both) < 3:
        return {"n": len(both), "spearman": float("nan"), "pearson": float("nan"), "table": both}
    return {
        "n": len(both),
        "spearman": float(both["close_rate_seoul"].corr(both["close_rate_national"], method="spearman")),
        "pearson": float(both["close_rate_seoul"].corr(both["close_rate_national"])),
        "table": both,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seoul", type=Path, required=True, help="서울판 dataset.csv")
    parser.add_argument("--national", type=Path, required=True, help="전국판 national_dataset.csv")
    opts = parser.parse_args()
    r = compare(pd.read_csv(opts.seoul), pd.read_csv(opts.national))
    print(r["table"].to_string(index=False))
    print(f"\n비교한 점 {r['n']}개, 순위 상관(Spearman) {r['spearman']:.3f}, 상관(Pearson) {r['pearson']:.3f}")


if __name__ == "__main__":
    main()
