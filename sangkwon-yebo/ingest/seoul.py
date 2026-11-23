"""서울열린데이터광장 '서울시 상권분석서비스' CSV를 읽어 분기 패널로 만든다. (이슈 #1, 팀원 A)

주의: 아래 COLUMN_MAP의 원본 열 이름은 '예상값'이다. 실제 파일을 받으면 가장 먼저
`python -m ingest.seoul --inspect 파일경로`로 열 이름을 확인하고, 다르면 팀장에게 알려 이 표를 고친다.
"""

import argparse
from pathlib import Path

import pandas as pd

from core.schemas import PANEL_REQUIRED, require_columns

# 원본 열 이름(한국어) → 내부 열 이름. 확인 전 예상값.
COLUMN_MAP_STORE: dict[str, str] = {
    "기준_년분기_코드": "quarter_code",
    "상권_구분_코드_명": "area_type",
    "상권_코드": "area_code",
    "상권_코드_명": "area_name",
    "서비스_업종_코드": "industry_code",
    "서비스_업종_코드_명": "industry_name",
    "점포_수": "stores",
    "개업_점포_수": "open_stores",
    "폐업_점포_수": "close_stores",
    "프랜차이즈_점포_수": "franchise_stores",
}
COLUMN_MAP_SALES: dict[str, str] = {
    "기준_년분기_코드": "quarter_code",
    "상권_코드": "area_code",
    "서비스_업종_코드": "industry_code",
    "당월_매출_금액": "sales_amount",  # 이름은 '당월'이지만 분기 합계로 알려져 있다. 확인 필요
}

# 외식업 10개 업종만 쓴다. 업종 코드는 실제 파일에서 확인해 채운다(이름으로 거르는 것이 안전).
FOOD_INDUSTRY_KEYWORDS = ("음식점", "치킨", "분식", "호프", "커피", "제과", "패스트푸드")


def read_csv_any(path: Path) -> pd.DataFrame:
    """서울시 CSV는 파일마다 UTF-8 또는 CP949로 저장돼 있어 둘 다 시도한다."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path}: UTF-8, CP949 둘 다 읽지 못했습니다.")


def _rename(df: pd.DataFrame, mapping: dict[str, str], where: str) -> pd.DataFrame:
    require_columns(df, list(mapping), where)
    return df[list(mapping)].rename(columns=mapping)


def _to_number(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        df[c] = pd.to_numeric(df[c].str.replace(",", "", regex=False), errors="coerce")
    return df


def load_store_files(paths: list[Path], food_only: bool = True) -> pd.DataFrame:
    """점포-상권 CSV 여러 개(연도별로 나뉘어 있음)를 읽어 분기 패널로 합친다."""
    frames = [_rename(read_csv_any(p), COLUMN_MAP_STORE, str(p)) for p in paths]
    df = pd.concat(frames, ignore_index=True)
    df = _to_number(df, ["quarter_code", "stores", "open_stores", "close_stores", "franchise_stores"])
    df["quarter_code"] = df["quarter_code"].astype(int)
    df["year"] = df["quarter_code"] // 10
    df["quarter"] = df["quarter_code"] % 10
    if food_only:
        mask = df["industry_name"].str.contains("|".join(FOOD_INDUSTRY_KEYWORDS), na=False)
        df = df[mask]
    # 같은 칸·분기가 두 번 들어오면(파일 중복) 하나만 남긴다
    df = df.drop_duplicates(subset=["quarter_code", "area_code", "industry_code"])
    require_columns(df, PANEL_REQUIRED, "분기 패널")
    return df.reset_index(drop=True)


def attach_sales(panel: pd.DataFrame, paths: list[Path]) -> pd.DataFrame:
    """추정매출-상권 CSV를 붙인다. 매출이 없는 칸은 결측으로 남긴다."""
    frames = [_rename(read_csv_any(p), COLUMN_MAP_SALES, str(p)) for p in paths]
    sales = pd.concat(frames, ignore_index=True)
    sales = _to_number(sales, ["quarter_code", "sales_amount"])
    sales["quarter_code"] = sales["quarter_code"].astype(int)
    sales = sales.drop_duplicates(subset=["quarter_code", "area_code", "industry_code"])
    return panel.merge(sales, on=["quarter_code", "area_code", "industry_code"], how="left")


def load_area_coords(path: Path) -> pd.DataFrame:
    """영역-상권 CSV에서 상권 중심 좌표를 읽어 위경도로 바꾼다. (이슈 #5, 팀원 B)

    구현 안내: 원본 좌표는 TM 좌표계로 알려져 있다(EPSG 번호는 파일 설명에서 확인).
    pyproj.Transformer.from_crs("EPSG:xxxx", "EPSG:4326", always_xy=True)로 변환한다.
    반환 열: area_code, lat, lon
    """
    raise NotImplementedError("이슈 #5에서 구현")


def main() -> None:
    parser = argparse.ArgumentParser(description="서울시 상권 CSV 확인 도구")
    parser.add_argument("--inspect", type=Path, help="파일의 열 이름과 앞 3행을 출력")
    args = parser.parse_args()
    if args.inspect:
        df = read_csv_any(args.inspect)
        print("행 수:", len(df))
        print("열:", list(df.columns))
        print(df.head(3).to_string())


if __name__ == "__main__":
    main()
