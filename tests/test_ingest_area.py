"""영역-상권 좌표 변환 테스트 (이슈 #6, 주초현)."""

import pandas as pd

from ingest.seoul import load_area_coords


def _write_area_csv(path, rows):
    pd.DataFrame(rows, columns=["상권_코드", "상권_코드_명", "엑스좌표_값", "와이좌표_값"]).to_csv(
        path, index=False, encoding="utf-8-sig"
    )


def test_gangnam_station_lands_near_real_place(tmp_path):
    f = tmp_path / "area.csv"
    _write_area_csv(f, [["1314", "강남역", 202454, 444235]])
    out = load_area_coords(f)
    row = out.iloc[0]
    assert row["area_code"] == "1314"
    assert abs(row["lon"] - 127.0285) < 0.001
    assert abs(row["lat"] - 37.5003) < 0.001


def test_missing_coordinates_are_dropped_not_zeroed(tmp_path):
    f = tmp_path / "area.csv"
    _write_area_csv(f, [["1", "A", 202454, 444235], ["2", "B", None, 444235]])
    out = load_area_coords(f)
    assert list(out["area_code"]) == ["1"]
    assert out["lat"].notna().all() and (out["lat"] > 30).all()
