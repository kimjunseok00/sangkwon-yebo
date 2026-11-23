"""전국판 변환 테스트. 손으로 셀 수 있는 작은 가게 기록으로 분기 점포·개업·폐업 수를 확인한다."""

import pandas as pd
import pytest

from core.schemas import PANEL_REQUIRED
from features.build import build_dataset
from ingest.localdata import _area_name, clean_records, read_localdata, to_quarterly_panel


def _raw(rows):
    cols = ["개방자치단체코드", "업태구분명", "인허가일자", "폐업일자", "영업상태명", "소재지전체주소"]
    return pd.DataFrame(rows, columns=cols)


ADDR = "서울특별시 마포구 망원동 1-1"
RAW = _raw([
    # 2018년 개업, 계속 영업 → 2019Q1부터 점포 수에 들어가야 한다(2019년 이전 기록도 누적)
    ["3130000", "한식", "20180510", "", "영업/정상", ADDR],
    # 2019Q2 개업, 2019Q4 폐업
    ["3130000", "한식", "2019-04-02", "2019-11-30", "폐업", ADDR],
    # 2019Q1 개업, 2019Q1 폐업 (같은 분기)
    ["3130000", "한식", "20190105", "20190320", "폐업", ADDR],
    # 폐업인데 폐업일자 없음 → 계산에서 빼고 보고
    ["3130000", "한식", "20170101", "", "폐업", ADDR],
    # 미분류 업태(푸드트럭) → 빼고 보고
    ["3130000", "푸드트럭", "20190101", "", "영업/정상", ADDR],
    # 휴업은 영업 중으로 본다
    ["3130000", "중국식", "20190201", "", "휴업", ADDR],
])


def test_clean_records_reports_dropped_rows():
    records, report = clean_records(RAW.rename(columns={
        "개방자치단체코드": "authority_code", "업태구분명": "biz_type", "인허가일자": "open_date",
        "폐업일자": "close_date", "영업상태명": "status", "소재지전체주소": "address"}))
    assert report["rows"] == 6
    assert report["closed_without_date"] == 1
    assert report["unmapped_biz_type"] == 1
    assert report["kept"] == 4
    assert set(records["industry_code"]) == {"NL01", "NL02"}


@pytest.fixture()
def panel(tmp_path):
    path = tmp_path / "food.csv"
    RAW.to_csv(path, index=False, encoding="cp949")
    records, _ = clean_records(read_localdata(path))
    return to_quarterly_panel(records, first_year=2019, last_quarter=(2019, 4))


def test_panel_has_schema_columns(panel):
    assert list(panel.columns) == PANEL_REQUIRED
    assert panel["franchise_stores"].isna().all()  # 0으로 채우지 않는다
    assert (panel["area_type"] == "시군구").all()


def test_quarter_counts_by_hand(panel):
    k = panel[panel["industry_code"] == "NL01"].set_index("quarter")
    # Q1: 2018년 가게 + 같은 분기 개업·폐업 가게 = 2곳 영업, 개업 1, 폐업 1
    assert (k.loc[1, "stores"], k.loc[1, "open_stores"], k.loc[1, "close_stores"]) == (2, 1, 1)
    # Q2: 2018년 가게 + 4월 개업 가게 = 2곳, 개업 1, 폐업 0
    assert (k.loc[2, "stores"], k.loc[2, "open_stores"], k.loc[2, "close_stores"]) == (2, 1, 0)
    # Q3: 2곳, 사건 없음 → 0건(결측 아님)
    assert (k.loc[3, "stores"], k.loc[3, "open_stores"], k.loc[3, "close_stores"]) == (2, 0, 0)
    # Q4: 11월 폐업 가게도 그 분기에는 점포 수에 들어간다(서울시 정의와 같게)
    assert (k.loc[4, "stores"], k.loc[4, "open_stores"], k.loc[4, "close_stores"]) == (2, 0, 1)


def test_area_name_parsing():
    s = pd.Series(["서울특별시 마포구 망원동 1", "경기도 수원시 장안구 정자동 2", "경기도 가평군 가평읍 3", None])
    assert list(_area_name(s)) == ["서울특별시 마포구", "경기도 수원시 장안구", "경기도 가평군", ""]


def test_national_panel_runs_through_same_pipeline():
    """전국판 패널이 서울판과 같은 특징·정답 코드를 그대로 통과하는지(형식 호환 확인)."""
    rng = pd.Series(range(400))
    rows = []
    for i in rng:
        area = f"{3000000 + (i % 8) * 10000}"
        open_y = 2016 + i % 8
        closed = i % 3 == 0
        close_y = min(open_y + 1 + i % 4, 2025)
        rows.append([area, ["한식", "분식"][i % 2], f"{open_y}0{1 + i % 9}15",
                     f"{close_y}0{1 + i % 9}20" if closed else "", "폐업" if closed else "영업/정상",
                     f"서울특별시 가상{i % 8}구 어느동"])
    records, _ = clean_records(_raw(rows).rename(columns={
        "개방자치단체코드": "authority_code", "업태구분명": "biz_type", "인허가일자": "open_date",
        "폐업일자": "close_date", "영업상태명": "status", "소재지전체주소": "address"}))
    panel = to_quarterly_panel(records, last_quarter=(2025, 4))
    data = build_dataset(panel)
    assert data["year"].min() == 2019 and data["year"].max() == 2025
    assert data["risk_next"].notna().any()


def test_reads_public_data_portal_format(tmp_path):
    """공공데이터포털 파일 형식(지번주소·도로명주소, 소재지전체주소 없음)도 읽는다."""
    df = pd.DataFrame({
        "개방자치단체코드": ["3130000", "3130000"],
        "관리번호": ["a", "b"],
        "인허가일자": ["20190105", "20190210"],
        "영업상태명": ["영업/정상", "폐업"],
        "폐업일자": ["", "20200101"],
        "업태구분명": ["한식", "분식"],
        "지번주소": ["", "서울특별시 마포구 망원동 2"],
        "도로명주소": ["서울특별시 마포구 월드컵로 1", ""],
    })
    path = tmp_path / "portal.csv"
    df.to_csv(path, index=False, encoding="cp949")
    raw = read_localdata(path)
    assert list(raw["address"]) == ["서울특별시 마포구 월드컵로 1", "서울특별시 마포구 망원동 2"]
    records, report = clean_records(raw)
    assert report["kept"] == 2
