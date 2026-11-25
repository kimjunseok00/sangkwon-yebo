"""서울열린데이터광장 '서울시 상권분석서비스' CSV를 읽어 분기 패널로 만든다. (이슈 #2, 주초현)

열 이름: 2021~2024 점포 파일은 한글 열(COLUMN_MAP_STORE), 2025 점포 파일은 영문 열(COLUMN_MAP_STORE_EN)이며
둘 다 실제 파일로 확인했다(11/24). 추정매출 파일의 열 이름은 아직 확인 전이다.
새 파일을 받으면 `python -m ingest.seoul --inspect 파일경로`로 열 이름을 먼저 확인한다.
"""

# 파이썬 3.9에서도 'X | None' 표기가 오류 나지 않게 한다 (맥 기본 파이썬 대비)
from __future__ import annotations

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

# 2025년 파일부터 열 이름이 영문 코드로 바뀌었다. 점포-상권 2025 파일의 실제 헤더로 확인함(11/24, 주초현).
# 실제 헤더: stdr_yyqu_cd trdar_se_cd trdar_se_cd_nm trdar_cd trdar_cd_nm svc_induty_cd svc_induty_cd_nm
#           stor_co similr_induty_stor_co opbiz_rt opbiz_stor_co clsbiz_rt clsbiz_stor_co frc_stor_co
# 아래 10개는 모두 이 헤더에 있다. 쓰지 않는 열(trdar_se_cd, similr_induty_stor_co, opbiz_rt, clsbiz_rt)은 읽지 않는다.
COLUMN_MAP_STORE_EN: dict[str, str] = {
    "stdr_yyqu_cd": "quarter_code",
    "trdar_se_cd_nm": "area_type",
    "trdar_cd": "area_code",
    "trdar_cd_nm": "area_name",
    "svc_induty_cd": "industry_code",
    "svc_induty_cd_nm": "industry_name",
    "stor_co": "stores",
    "opbiz_stor_co": "open_stores",
    "clsbiz_stor_co": "close_stores",
    "frc_stor_co": "franchise_stores",
}
COLUMN_MAP_SALES_EN: dict[str, str] = {
    "stdr_yyqu_cd": "quarter_code",
    "trdar_cd": "area_code",
    "svc_induty_cd": "industry_code",
    "thsmon_selng_amt": "sales_amount",  # 확인 전: 추정매출 2025 파일 헤더를 받으면 맞춘다
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


def _rename(df: pd.DataFrame, mapping: dict[str, str], where: str, alt: dict[str, str] | None = None) -> pd.DataFrame:
    """파일 열 이름에 맞는 대응표(한글 mapping 또는 영문 alt)를 골라 내부 열 이름으로 바꾼다.

    둘 다 맞지 않으면 빠진 열이 더 적은 쪽 기준으로 오류를 낸다(어느 열을 고칠지 알 수 있게).
    """
    candidates = [m for m in (mapping, alt) if m]
    for m in candidates:
        if all(c in df.columns for c in m):
            return df[list(m)].rename(columns=m)
    closest = min(candidates, key=lambda m: sum(c not in df.columns for c in m))
    require_columns(df, list(closest), where)  # 항상 SchemaError를 낸다
    raise AssertionError("도달하지 않음")


def _to_number(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        df[c] = pd.to_numeric(df[c].str.replace(",", "", regex=False), errors="coerce")
    return df


def load_store_files(paths: list[Path], food_only: bool = True) -> pd.DataFrame:
    """점포-상권 CSV 여러 개(연도별로 나뉘어 있음)를 읽어 분기 패널로 합친다."""
    frames = [_rename(read_csv_any(p), COLUMN_MAP_STORE, str(p), COLUMN_MAP_STORE_EN) for p in paths]
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
    frames = [_rename(read_csv_any(p), COLUMN_MAP_SALES, str(p), COLUMN_MAP_SALES_EN) for p in paths]
    sales = pd.concat(frames, ignore_index=True)
    sales = _to_number(sales, ["quarter_code", "sales_amount"])
    sales["quarter_code"] = sales["quarter_code"].astype(int)
    sales = sales.drop_duplicates(subset=["quarter_code", "area_code", "industry_code"])
    return panel.merge(sales, on=["quarter_code", "area_code", "industry_code"], how="left")


def load_area_coords(path: Path) -> pd.DataFrame:
    """영역-상권 CSV에서 상권 중심 좌표를 읽어 위경도로 바꾼다. (이슈 #6, 주초현)

    구현 안내: 원본 좌표는 TM 좌표계로 알려져 있다(EPSG 번호는 파일 설명에서 확인).
    pyproj.Transformer.from_crs("EPSG:xxxx", "EPSG:4326", always_xy=True)로 변환한다.
    반환 열: area_code, lat, lon
    """
    raise NotImplementedError("이슈 #6에서 구현")


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
