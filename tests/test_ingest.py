"""원본 CSV 읽기. 실제 파일 열 이름이 확인되면 이 테스트의 가짜 파일도 실제 형식에 맞춘다."""

import pandas as pd

from core.schemas import PANEL_REQUIRED
import pytest

from core.schemas import SchemaError
from ingest.seoul import COLUMN_MAP_STORE, COLUMN_MAP_STORE_EN, load_store_files


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


def test_reads_english_headers_mixed_with_korean(tmp_path):
    """2021~2024는 한글 열, 2025는 영문 열이어도 한 번에 합쳐 읽는다."""
    old = tmp_path / "store_2024.csv"
    _write_store_csv(old, "cp949")
    new = tmp_path / "store_2025.csv"
    rows = [["20251", "골목상권", "3110001", "테스트골목", "CS100001", "한식음식점", "10", "1", "3", "2"]]
    pd.DataFrame(rows, columns=list(COLUMN_MAP_STORE_EN)).to_csv(new, index=False, encoding="utf-8-sig")
    panel = load_store_files([old, new])
    assert sorted(panel["year"].unique()) == [2024, 2025]
    assert panel[panel["year"] == 2025].iloc[0]["close_stores"] == 3


def test_unknown_headers_report_missing_and_actual_columns(tmp_path):
    p = tmp_path / "store.csv"
    pd.DataFrame([["20251", "1"]], columns=["stdr_yyqu_cd", "something_else"]).to_csv(p, index=False)
    with pytest.raises(SchemaError) as e:
        load_store_files([p])
    assert "빠진 열" in str(e.value) and "something_else" in str(e.value)


def test_reads_real_2025_header_with_extra_columns(tmp_path):
    """주초현이 확인한 2025 점포-상권 파일의 실제 헤더(14열). 안 쓰는 열이 섞여 있어도 읽혀야 한다."""
    header = ["stdr_yyqu_cd", "trdar_se_cd", "trdar_se_cd_nm", "trdar_cd", "trdar_cd_nm", "svc_induty_cd",
              "svc_induty_cd_nm", "stor_co", "similr_induty_stor_co", "opbiz_rt", "opbiz_stor_co", "clsbiz_rt",
              "clsbiz_stor_co", "frc_stor_co"]
    rows = [
        ["20251", "A", "골목상권", "3110001", "이북5도청사", "CS100001", "한식음식점", "12", "13", "0", "0", "8", "1", "1"],
        ["20251", "A", "골목상권", "3110001", "이북5도청사", "CS100008", "분식전문점", "2", "2", "0", "0", "0", "0", "0"],
    ]
    p = tmp_path / "store_2025.csv"
    pd.DataFrame(rows, columns=header).to_csv(p, index=False, encoding="utf-8-sig")
    panel = load_store_files([p])
    assert len(panel) == 2
    row = panel[panel["industry_code"] == "CS100001"].iloc[0]
    assert row["stores"] == 12 and row["close_stores"] == 1 and row["open_stores"] == 0 and row["franchise_stores"] == 1
