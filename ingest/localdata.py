"""전국판: 지방행정 인허가 데이터(일반음식점)를 서울판과 같은 분기 패널로 바꾼다.

왜 이렇게 만드나
  서울판의 특징 만들기(features/build.py)·과거 맞히기 실험(experiments/backtest.py)을
  한 줄도 고치지 않고 전국에 그대로 쓰기 위해, 출력 형식을 core.schemas.PANEL_REQUIRED에 맞춘다.
  같은 시험 규칙으로 서울판과 전국판의 성적을 나란히 비교할 수 있다.

변환 규칙 (한 행 = 가게 하나의 인허가 기록)
  - 칸 = 관리 자치단체(시군구, 개방자치단체코드) × 업종(업태구분명을 묶은 것)
  - 개업 분기 = 인허가일자가 속한 분기
  - 폐업 분기 = 폐업일자가 속한 분기 (영업상태가 폐업인데 폐업일자가 없으면 계산에서 빼고 개수를 보고)
  - 분기 점포 수 = 그 분기 안에 하루라도 영업한 가게 수 (서울시 정의 '운영 + 그 분기 폐업'과 같게)
  - 휴업은 영업 중으로 본다 (인허가가 살아 있으므로)
  - 프랜차이즈 여부는 인허가 데이터에 없어서 결측(NaN)으로 둔다. 0으로 채우지 않는다.

⚠️ 열 이름은 공공데이터포털 메타데이터 기준 '예상값'이다. 실제 파일을
   `python -m ingest.localdata --inspect 파일.csv`로 확인하고 COLUMN_CANDIDATES를 맞춘다(#20).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from core.schemas import PANEL_REQUIRED

# 내부 이름 → 원본 열 이름 후보(앞에 있는 것부터 쓴다).
# 같은 데이터라도 받는 곳(LOCALDATA / 공공데이터포털)에 따라 열 이름이 조금 다르다.
# 11/23 공공데이터포털 '식품_일반음식점' 파일로 확인: 개방자치단체코드, 업태구분명, 인허가일자,
#   폐업일자, 영업상태명, 지번주소, 도로명주소 (소재지전체주소는 없음)
COLUMN_CANDIDATES: dict[str, list[str]] = {
    "authority_code": ["개방자치단체코드"],
    "biz_type": ["업태구분명"],
    "open_date": ["인허가일자"],
    "close_date": ["폐업일자"],
    "status": ["영업상태명"],
}
# 주소는 여러 열 중 있는 것을 순서대로 채운다(지번주소가 비어 있으면 도로명주소로).
ADDRESS_CANDIDATES = ["소재지전체주소", "지번주소", "도로명전체주소", "도로명주소"]
# 가게 좌표(선택). 지도용 지역 중심점 계산에만 쓴다. 좌표계는 EPSG:5174(공공데이터포털 설명 기준).
COORD_CANDIDATES = {"x": ["좌표정보(X)", "좌표정보(x)"], "y": ["좌표정보(Y)", "좌표정보(y)"]}
SOURCE_CRS = "EPSG:5174"

CLOSED_STATUS = "폐업"  # 영업상태명 값. 실제 값(예: '폐업', '취소/말소/만료/정지/중지')을 #20에서 확인

# 업태구분명 → 전국판 업종. 서울판 10개 업종과 1:1로 맞지 않으므로 코드를 따로 쓴다(NL = National).
# 값 목록은 실제 파일의 업태 빈도표를 보고 고친다. 여기 없는 업태는 '미분류'로 세고 계산에서 뺀다.
INDUSTRY_MAP: dict[str, tuple[str, str]] = {
    "한식": ("NL01", "한식"),
    "식육(숯불구이)": ("NL01", "한식"),
    "탕류(보신용)": ("NL01", "한식"),
    "냉면집": ("NL01", "한식"),
    "회집": ("NL01", "한식"),
    "횟집": ("NL01", "한식"),
    "복어취급": ("NL01", "한식"),
    "중국식": ("NL02", "중식"),
    "일식": ("NL03", "일식"),
    "경양식": ("NL04", "양식"),
    "패밀리레스트랑": ("NL04", "양식"),
    "외국음식전문점(인도,태국등)": ("NL04", "양식"),
    "분식": ("NL05", "분식"),
    "김밥(도시락)": ("NL05", "분식"),
    "통닭(치킨)": ("NL06", "치킨"),
    "호프/통닭": ("NL07", "호프·주점"),
    "정종/대포집/소주방": ("NL07", "호프·주점"),
    "감성주점": ("NL07", "호프·주점"),
    "패스트푸드": ("NL08", "패스트푸드"),
    "뷔페식": ("NL09", "뷔페"),
    # --- 11/23 빈도표 확인 후 추가 (결과를 본 뒤의 변경. docs/EXPERIMENTS.md 기준 변경 기록 참고) ---
    "까페": ("NL10", "카페"),
    "전통찻집": ("NL10", "카페"),
    "라이브카페": ("NL07", "호프·주점"),
    # '기타'는 전체의 12.6%(약 29만 건). 버리면 폐업률이 왜곡되므로 독립 업종으로 둔다.
    # 여러 업태가 섞인 묶음이라 발표의 대표 사례로는 쓰지 않는다.
    "기타": ("NL99", "기타"),
}
# 일부러 넣지 않은 업태: 출장조리, 이동조리, 푸드트럭, 키즈카페, 일반조리판매 등(합계 약 0.15%).
# 고정 점포 영업이 아니거나 외식업으로 보기 어려워 '미분류'로 세고 뺀다.

# 서울판 업종과 비교할 때 쓰는 대응표(experiments/crosscheck.py). 확실히 같은 것만 넣는다.
SEOUL_CROSSWALK = {
    "NL01": "한식음식점",
    "NL02": "중식음식점",
    "NL03": "일식음식점",
    "NL04": "양식음식점",
    "NL05": "분식전문점",
    "NL06": "치킨전문점",
    "NL08": "패스트푸드점",
}

FIRST_YEAR = 2019  # 전국판 시작 연도. (서울은 서울시 제공 중단으로 2021~이라 기간이 다르다. 값은 11/23 결과 기준이라 바꾸지 않는다)


def read_localdata(path: Path) -> pd.DataFrame:
    """인허가 CSV를 필요한 열만 읽는다. 파일이 수백만 행이라 usecols로 메모리를 줄인다."""
    wanted = ({c for cands in COLUMN_CANDIDATES.values() for c in cands} | set(ADDRESS_CANDIDATES)
              | {c for cands in COORD_CANDIDATES.values() for c in cands})
    last_error: Exception | None = None
    for enc in ("cp949", "utf-8-sig"):
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str, usecols=lambda c: c in wanted)
            break
        except UnicodeDecodeError as e:  # 인코딩이 다르면 다음 후보로
            last_error = e
    else:
        raise ValueError(f"{path}: CP949, UTF-8 둘 다 읽지 못했습니다.") from last_error

    out = pd.DataFrame(index=df.index)
    missing = []
    for internal, cands in COLUMN_CANDIDATES.items():
        found = next((c for c in cands if c in df.columns), None)
        if found is None:
            missing.append(f"{internal}(후보: {cands})")
        else:
            out[internal] = df[found]
    addr_cols = [c for c in ADDRESS_CANDIDATES if c in df.columns]
    if not addr_cols:
        missing.append(f"address(후보: {ADDRESS_CANDIDATES})")
    if missing:
        raise ValueError(
            f"{path}: 필요한 열 {missing}이 없습니다. "
            "`python -m ingest.localdata --inspect`의 '열 이름'을 보고 COLUMN_CANDIDATES에 추가하세요."
        )
    # 빈 문자열도 결측으로 보고, 앞 후보가 비면 다음 후보로 채운다
    address = pd.Series(pd.NA, index=df.index, dtype="object")
    for c in addr_cols:
        address = address.fillna(df[c].where(df[c].str.strip().ne(""), pd.NA))
    out["address"] = address
    # 좌표는 없어도 된다(지도만 못 그린다). 있으면 숫자로 바꿔 둔다.
    for internal, cands in COORD_CANDIDATES.items():
        found = next((c for c in cands if c in df.columns), None)
        if found is not None:
            out[internal] = pd.to_numeric(df[found], errors="coerce")
    return out


def _parse_date(s: pd.Series) -> pd.Series:
    """'20190305', '2019-03-05', '2019.03.05' 모두 받는다. 못 읽으면 NaT."""
    cleaned = s.astype("string").str.replace(r"[^0-9]", "", regex=True).str.slice(0, 8)
    return pd.to_datetime(cleaned, format="%Y%m%d", errors="coerce")


def _quarter_index(dates: pd.Series) -> pd.Series:
    """날짜 → 분기 번호(연*4 + 분기-1). 분기끼리 빼기·비교를 정수로 하기 위함."""
    # int64로 맞춘다: pandas가 연·분기를 int32로 줄 때가 있어 np.arange(int64)와 합칠 때 오류가 난다
    return (dates.dt.year * 4 + (dates.dt.quarter - 1)).astype("Float64").astype("float64")


def _area_name(address: pd.Series) -> pd.Series:
    """'서울특별시 마포구 망원동 ...' → '서울특별시 마포구'. 시 아래 구가 있는 곳(수원시 장안구)은 3단어까지."""
    parts = address.fillna("").str.split()
    first2 = parts.str[:2].str.join(" ")
    third = parts.str[2].fillna("")
    has_gu = parts.str[1].fillna("").str.endswith("시") & third.str.endswith("구")
    return first2.where(~has_gu, first2 + " " + third)


def clean_records(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """원본 행을 정리하고, 빠진 행이 몇 개인지 보고서(dict)를 함께 돌려준다.

    결측을 조용히 버리지 않고 report에 남겨, #20 판정에서 데이터 품질을 숫자로 볼 수 있게 한다.
    """
    df = raw.copy()
    df["open_date"] = _parse_date(df["open_date"])
    df["close_date"] = _parse_date(df["close_date"])
    is_closed = df["status"].fillna("").str.contains(CLOSED_STATUS)
    # 폐업이 아닌데 폐업일자가 있는 행은 재개업 등으로 보고 폐업일자를 무시한다
    df.loc[~is_closed, "close_date"] = pd.NaT

    mapped = df["biz_type"].map(lambda v: INDUSTRY_MAP.get(v))
    df["industry_code"] = mapped.map(lambda t: t[0] if t else None)
    df["industry_name"] = mapped.map(lambda t: t[1] if t else None)

    report = {
        "rows": len(df),
        "no_open_date": int(df["open_date"].isna().sum()),
        "closed_without_date": int((is_closed & df["close_date"].isna()).sum()),
        "unmapped_biz_type": int(df["industry_code"].isna().sum()),
        "close_before_open": int((df["close_date"] < df["open_date"]).sum()),
    }
    keep = (
        df["open_date"].notna()
        & ~(is_closed & df["close_date"].isna())
        & df["industry_code"].notna()
        & ~(df["close_date"] < df["open_date"])
        & df["authority_code"].notna()
    )
    cols = ["authority_code", "address", "industry_code", "industry_name", "open_date", "close_date"]
    cols += [c for c in ("x", "y") if c in df.columns]
    out = df.loc[keep, cols]
    report["kept"] = int(keep.sum())
    return out.reset_index(drop=True), report


def to_quarterly_panel(records: pd.DataFrame, first_year: int = FIRST_YEAR,
                       last_quarter: tuple[int, int] | None = None) -> pd.DataFrame:
    """가게 기록 → 분기 패널(PANEL_REQUIRED 형식).

    last_quarter: 마지막으로 다 끝난 분기 (연, 분기). 없으면 기록 중 가장 늦은 날짜의 '직전' 분기로 잡는다.
    진행 중인 분기를 넣으면 폐업이 덜 잡혀 폐업률이 낮게 나오기 때문이다.
    """
    rec = records.copy()
    rec["open_q"] = _quarter_index(rec["open_date"]).astype("int64")  # 개업일은 clean_records에서 결측 제거됨
    rec["close_q"] = _quarter_index(rec["close_date"])  # 영업 중이면 NaN

    if last_quarter is None:
        latest = max(rec["open_date"].max(), rec["close_date"].max())
        last_q = int(_quarter_index(pd.Series([latest])).iloc[0]) - 1
    else:
        last_q = last_quarter[0] * 4 + (last_quarter[1] - 1)
    first_q = first_year * 4
    quarters = np.arange(first_q, last_q + 1, dtype="int64")

    keys = ["authority_code", "industry_code"]
    # 분기마다 '그때까지 누적 개업 수'와 '그 전 분기까지 누적 폐업 수'를 세면,
    # 분기 점포 수 = 누적 개업(≤q) − 누적 폐업(<q) 로 가게 수백만 개를 분기마다 다시 훑지 않고 계산된다.
    opens = rec.groupby(keys + ["open_q"]).size().rename("n").reset_index()
    closes = rec.dropna(subset=["close_q"]).astype({"close_q": "int64"})
    closes = closes.groupby(keys + ["close_q"]).size().rename("n").reset_index()

    cells = rec[keys].drop_duplicates()
    grid = cells.merge(pd.DataFrame({"q": quarters}), how="cross")

    def cum_upto(events: pd.DataFrame, qcol: str, strict: bool) -> pd.Series:
        """칸별로 q 이하(strict면 q 미만) 사건 수 누적. 2019년 이전 사건도 모두 포함된다."""
        ev = events.rename(columns={qcol: "q"}).sort_values("q")
        ev = ev.assign(q=ev["q"] + (1 if strict else 0))  # '미만'은 한 분기 뒤로 밀어 '이하'로 바꾼다
        ev = ev.groupby(keys + ["q"])["n"].sum().groupby(level=keys).cumsum().reset_index()
        merged = pd.merge_asof(
            grid.sort_values("q"), ev.sort_values("q"), on="q", by=keys, direction="backward"
        )
        return merged.set_index(keys + ["q"])["n"].fillna(0)

    cum_open = cum_upto(opens, "open_q", strict=False)
    cum_close_before = cum_upto(closes, "close_q", strict=True)

    panel = grid.set_index(keys + ["q"])
    panel["stores"] = cum_open - cum_close_before
    panel["open_stores"] = opens.rename(columns={"open_q": "q"}).set_index(keys + ["q"])["n"]
    panel["close_stores"] = closes.rename(columns={"close_q": "q"}).set_index(keys + ["q"])["n"]
    panel = panel.reset_index()
    # 그 분기에 사건이 없었다는 것은 '0건'이 확실하다(전수 기록이므로). 결측과 다르다.
    panel[["open_stores", "close_stores"]] = panel[["open_stores", "close_stores"]].fillna(0)

    names = (
        rec.assign(area_name=_area_name(rec["address"]))
        .groupby("authority_code")["area_name"]
        .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "")
    )
    ind_names = rec.drop_duplicates("industry_code").set_index("industry_code")["industry_name"]

    panel["year"] = panel["q"] // 4
    panel["quarter"] = panel["q"] % 4 + 1
    panel["quarter_code"] = panel["year"] * 10 + panel["quarter"]
    panel["area_code"] = panel["authority_code"]
    panel["area_name"] = panel["authority_code"].map(names)
    panel["area_type"] = "시군구"
    panel["industry_name"] = panel["industry_code"].map(ind_names)
    panel["franchise_stores"] = np.nan  # 인허가 데이터에 없음
    panel = panel[panel["stores"] > 0]
    cols = PANEL_REQUIRED
    return panel[cols].astype({"stores": int, "open_stores": int, "close_stores": int}).reset_index(drop=True)


def area_centroids(records: pd.DataFrame) -> pd.DataFrame | None:
    """지역(관리 자치단체)별 가게 좌표의 중앙값 → 위경도. 지도에 지역을 점으로 찍는 데 쓴다.

    - 평균 대신 중앙값: 좌표가 잘못 들어간 몇몇 가게에 끌려가지 않게.
    - EPSG:5174 → WGS84 변환은 pyproj 기본 정의를 쓴다. 한국 측지계 보정값 차이로 수백 m 어긋날 수 있으나
      시군구 중심점 표시에는 영향이 없다(동 단위로 좁힐 때 다시 확인).
    - 좌표 열이 없으면 None(지도만 못 그리고 나머지는 정상 동작).
    """
    if not {"x", "y"} <= set(records.columns):
        return None
    from pyproj import Transformer

    pts = records.dropna(subset=["x", "y"])
    pts = pts[(pts["x"] > 0) & (pts["y"] > 0)]
    if pts.empty:
        return None
    med = pts.groupby("authority_code").agg(x=("x", "median"), y=("y", "median"), n_points=("x", "size"))
    lon, lat = Transformer.from_crs(SOURCE_CRS, "EPSG:4326", always_xy=True).transform(med["x"].to_numpy(),
                                                                                      med["y"].to_numpy())
    out = pd.DataFrame({"area_code": med.index, "lat": lat, "lon": lon, "n_points": med["n_points"].to_numpy()})
    # 한반도 범위를 벗어나면 좌표가 잘못된 것이므로 뺀다
    out = out[out["lat"].between(33, 39) & out["lon"].between(124, 132)]
    names = records.assign(area_name=_area_name(records["address"])).groupby("authority_code")["area_name"].agg(
        lambda s: s.mode().iloc[0] if not s.mode().empty else "")
    out["area_name"] = out["area_code"].map(names)
    return out.reset_index(drop=True)


def inspect(path: Path) -> None:
    """#20 판정용: 열 이름, 연도별 폐업 기록 수, 업태 빈도를 출력한다."""
    head = None
    for enc in ("cp949", "utf-8-sig"):
        try:
            head = pd.read_csv(path, encoding=enc, dtype=str, nrows=5)
            print(f"인코딩: {enc}")
            break
        except UnicodeDecodeError:
            continue
    if head is None:
        raise ValueError("인코딩을 알 수 없습니다.")
    print("열 이름:", list(head.columns))
    raw = read_localdata(path)
    records, report = clean_records(raw)
    print("정리 보고:", report)
    print("\n연도별 폐업 기록 수 (2019년이 최근 연도보다 지나치게 적으면 옛 기록이 지워진 것):")
    print(records["close_date"].dt.year.value_counts().sort_index().loc[lambda s: s.index >= 2015])
    print("\n연도별 개업 기록 수:")
    print(records["open_date"].dt.year.value_counts().sort_index().loc[lambda s: s.index >= 2015])
    print("\n영업상태 값:", raw["status"].value_counts().head(10).to_dict())
    print("\n업태 빈도 (미분류 포함 상위 30):")
    print(raw["biz_type"].value_counts().head(30))


def main() -> None:
    parser = argparse.ArgumentParser(description="인허가 데이터 → 전국판 분기 패널과 dataset")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--inspect", action="store_true", help="열 이름과 품질만 확인(#20)")
    parser.add_argument("--out-dir", type=Path, default=Path("data/processed"))
    opts = parser.parse_args()
    if opts.inspect:
        inspect(opts.csv)
        return
    from features.build import build_dataset  # 서울판과 같은 특징·정답 코드를 그대로 쓴다

    records, report = clean_records(read_localdata(opts.csv))
    print("정리 보고:", report)
    panel = to_quarterly_panel(records)
    opts.out_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(opts.out_dir / "national_panel.csv", index=False)
    data = build_dataset(panel)
    data.to_csv(opts.out_dir / "national_dataset.csv", index=False)
    n_cells = panel[["area_code", "industry_code"]].drop_duplicates().shape[0]
    print(f"저장: national_panel.csv {len(panel):,}행, national_dataset.csv {len(data):,}행, 칸 {n_cells:,}개")
    print("연도별 정답 있는 칸:", data.groupby("year")["risk_next"].count().to_dict())


if __name__ == "__main__":
    main()
