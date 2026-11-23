"""원본 CSV → data/processed/dataset.csv 한 번에 만들기. (이슈 #2, 주초현)

실행 예:
  python scripts_build_dataset.py --stores data/raw/store_*.csv --sales data/raw/sales_*.csv
"""

import argparse
from pathlib import Path

from core import config
from features.build import build_dataset
from ingest.seoul import attach_sales, load_store_files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stores", nargs="+", type=Path, required=True)
    parser.add_argument("--sales", nargs="*", type=Path, default=[])
    args = parser.parse_args()

    panel = load_store_files(args.stores)
    if args.sales:
        panel = attach_sales(panel, args.sales)
    data = build_dataset(panel)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = config.PROCESSED_DIR / "dataset.csv"
    data.to_csv(out, index=False)
    labeled = data["risk_next"].notna()
    print(f"분기 행 {len(panel):,} → 연 단위 행 {len(data):,} (정답 있는 행 {labeled.sum():,})")
    print("연도별 정답 있는 칸 수:", data[labeled].groupby("year").size().to_dict())
    print("저장:", out)


if __name__ == "__main__":
    main()
