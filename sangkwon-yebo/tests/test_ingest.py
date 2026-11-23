"""원본 CSV 읽기. 실제 파일 열 이름이 확인되면 이 테스트의 가짜 파일도 실제 형식에 맞춘다."""

import pandas as pd

from core.schemas import PANEL_REQUIRED
from ingest.seoul import COLUMN_MAP_STORE, load_store_files


def _write_store_csv(path, encoding):
    rows = [
        ["20241", "골목상권", "3110001", "테스트골목", "CS100001", "한식음식점", "12", "1", "2", "3"],
        ["20241", "골목상권", "3110001", "테스트골목", "CS200001", "일반교습학원", "5", "0", "1", "0"],
        ["20241", "골목상권", "3110001", "테스트골목", "CS100001", "한식음식점", "12", "1", "2", "3"],  # 중복
    ]
    df = pd.DataFrame(rows, columns=list(COLUMN_MAP_STORE))
    df.to_csv(path, index=False, encoding=encoding)


def test_reads_cp949_and_filters_food(tmp_path):
    p = tmp_path / "store.csv"
    _write_store_csv(p, "cp949")
    panel = load_store_files([p])
    assert set(PANEL_REQUIRED) <= set(panel.columns)
    assert list(panel["industry_name"]) == ["한식음식점"]  # 학원은 빠지고 중복은 하나로
    row = panel.iloc[0]
    assert row["year"] == 2024 and row["quarter"] == 1 and row["close_stores"] == 2


def test_reads_utf8(tmp_path):
    p = tmp_path / "store.csv"
    _write_store_csv(p, "utf-8-sig")
    assert len(load_store_files([p])) == 1
