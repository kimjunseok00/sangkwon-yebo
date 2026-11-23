"""명령 하나로 서울판·전국판의 dataset과 서비스용 결과(published/)를 모두 만든다.

  python -m experiments.make_all
  python -m experiments.make_all --only national      # 한쪽만

흐름 (원본 파일이 있는 쪽만 돈다. 없는 쪽은 건너뛰고 이유를 알려 준다)
  서울판: data/raw/store_*.csv (+ sales_*.csv) → dataset.csv          → published/seoul/
  전국판: data/raw/localdata_food.csv          → national_dataset.csv → published/national/

화면(app.py)과 API(api/)는 published/만 읽는다. 자동 갱신(#24)도 이 명령만 부르면 된다.
각 단계는 기존 모듈(ingest, features, experiments.publish)을 그대로 부른다. 새 계산은 없다.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from core import config
from experiments.publish import publish
from features.build import build_dataset


@dataclass
class Source:
    """원본 하나(서울판 또는 전국판)를 dataset으로 만드는 방법."""

    name: str
    dataset_file: str

    def find_inputs(self, raw_dir: Path) -> list[Path]:
        raise NotImplementedError

    def build(self, inputs: list[Path]) -> pd.DataFrame:
        raise NotImplementedError

    def areas(self) -> pd.DataFrame | None:
        """지도용 지역 좌표. build() 뒤에 부른다. 없으면 None."""
        return None


class SeoulSource(Source):
    def find_inputs(self, raw_dir: Path) -> list[Path]:
        return sorted(raw_dir.glob("store_*.csv"))

    def build(self, inputs: list[Path]) -> pd.DataFrame:
        from ingest.seoul import attach_sales, load_store_files

        panel = load_store_files(inputs)
        sales = sorted(inputs[0].parent.glob("sales_*.csv"))
        if sales:
            panel = attach_sales(panel, sales)
        return build_dataset(panel)


class NationalSource(Source):
    def find_inputs(self, raw_dir: Path) -> list[Path]:
        f = raw_dir / "localdata_food.csv"
        return [f] if f.exists() else []

    def build(self, inputs: list[Path]) -> pd.DataFrame:
        from ingest.localdata import clean_records, read_localdata, to_quarterly_panel

        from ingest.localdata import area_centroids

        records, report = clean_records(read_localdata(inputs[0]))
        print(f"  정리 보고: {report}")
        self._areas = area_centroids(records)
        return build_dataset(to_quarterly_panel(records))

    def areas(self) -> pd.DataFrame | None:
        return getattr(self, "_areas", None)


SOURCES: dict[str, Source] = {
    "seoul": SeoulSource("seoul", "dataset.csv"),
    "national": NationalSource("national", "national_dataset.csv"),
}


def make_all(raw_dir: Path = config.RAW_DIR, processed_dir: Path = config.PROCESSED_DIR,
             only: list[str] | None = None) -> dict[str, dict]:
    """원본이 있는 데이터셋마다 dataset → published 를 만든다. 데이터셋 이름 → meta(또는 건너뛴 이유)."""
    summary: dict[str, dict] = {}
    for name, src in SOURCES.items():
        if only and name not in only:
            continue
        inputs = src.find_inputs(raw_dir)
        if not inputs:
            summary[name] = {"skipped": f"{raw_dir}에 원본 파일이 없음"}
            print(f"[{name}] 건너뜀: 원본 파일 없음")
            continue
        print(f"[{name}] 원본 {len(inputs)}개 → dataset")
        data = src.build(inputs)
        processed_dir.mkdir(parents=True, exist_ok=True)
        data.to_csv(processed_dir / src.dataset_file, index=False)
        meta = publish(data, processed_dir / "published", name, "real", areas=src.areas())
        print(f"[{name}] 완료: 칸 {meta['n_cells']:,}개, {meta['gate_detail']}")
        summary[name] = meta
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+", choices=sorted(SOURCES))
    opts = parser.parse_args()
    summary = make_all(only=opts.only)
    if all("skipped" in v for v in summary.values()):
        raise SystemExit("만든 데이터셋이 없습니다. docs/DATA_SOURCES.md의 파일을 data/raw/에 넣으세요.")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
