"""데이터 형식 정의. 모듈끼리 주고받는 표(DataFrame)의 열 이름을 여기서 고정한다.

pandas 표를 주고받으므로 열 이름이 곧 약속이다. 바꾸려면 팀장과 합의한 뒤
docs/DATA_FORMAT.md, 가상 데이터(experiments/synthetic.py), 테스트를 함께 고친다.
"""

import pandas as pd
from pydantic import BaseModel

# 칸(cell)을 구분하는 열. 한 칸 = 상권 하나 × 업종 하나.
KEYS = ["area_code", "industry_code"]

# ---------------------------------------------------------------------------
# 1) 분기 패널: ingest가 서울시 원본을 읽어 만든 표. 한 행 = 상권 × 업종 × 분기
# ---------------------------------------------------------------------------
PANEL_REQUIRED = [
    "quarter_code",  # 20241 = 2024년 1분기
    "year",
    "quarter",
    "area_code",
    "area_name",
    "area_type",  # 골목상권/발달상권/전통시장/관광특구
    "industry_code",
    "industry_name",
    "stores",  # 점포 수 (서울시 정의: 당기 운영 점포 + 폐업 점포)
    "open_stores",  # 그 분기 개업 점포 수
    "close_stores",  # 그 분기 폐업 점포 수
    "franchise_stores",
]
PANEL_OPTIONAL = [
    "sales_amount",  # 그 분기 추정 매출 합(원). 추정매출 파일을 합쳤을 때만 있음
]

# ---------------------------------------------------------------------------
# 2) 연 단위 표: features.build가 만든다. 한 행 = 상권 × 업종 × 연도(예측 기준 연도)
# ---------------------------------------------------------------------------
ANNUAL_BASE = [
    "area_code", "area_name", "area_type", "industry_code", "industry_name", "year",
    "n_quarters", "stores_avg", "open_sum", "close_sum", "franchise_avg",
    "close_rate", "open_rate", "franchise_share",
]

# 모델 입력 특징. 모두 '그 해 말까지 알 수 있는 값'만 쓴다(미래 정보 누설 금지).
FEATURES = [
    "close_rate",  # 올해 폐업률
    "close_rate_prev",  # 작년 폐업률
    "close_rate_3y",  # 최근 3년 평균 폐업률
    "close_rate_rel",  # 같은 업종 서울 평균 대비 차이
    "open_rate",
    "store_growth",  # 점포 수 전년 대비 증감률
    "franchise_share",
    "log_stores",
    "industry_close_mean",  # 그 업종의 서울 평균 폐업률(업종 분위기)
    "sales_per_store_growth",  # 점포당 매출 전년 대비(매출 데이터가 있을 때만, 없으면 결측)
]

TARGET = "risk_next"  # 1 = 다음 해 업종 내 폐업률 상위 25%
TARGET_HELPERS = ["next_close_rate", "next_stores_avg"]  # 정답을 만든 재료. 모델 입력에 쓰면 안 된다

# ---------------------------------------------------------------------------
# 3) 실험 결과 표: experiments.backtest가 만든다
# ---------------------------------------------------------------------------
RESULT_COLUMNS = [
    "test_year",  # 예측 기준 연도
    "target_year",  # 맞히는 연도
    "method",  # model / baseline_last_year / baseline_3y_avg
    "n",
    "base_rate",  # 위험 칸 비율(약 0.25)
    "auc",
    "precision_at_top",  # 상위 TOP_FRACTION 경고 중 실제 위험 비율
    "recall_at_top",  # 실제 위험 중 상위 경고로 잡아낸 비율
    "lift_at_top",  # precision / base_rate
]


class SchemaError(ValueError):
    """표에 필요한 열이 없을 때. 어떤 열이 빠졌는지 메시지에 적는다."""


def require_columns(df: pd.DataFrame, columns: list[str], where: str) -> None:
    """df에 columns가 모두 있는지 확인한다. 없으면 빠진 열과 실제 열을 알려 준다."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise SchemaError(f"{where}: 빠진 열 {missing}. 실제 열: {list(df.columns)}")


# ---------------------------------------------------------------------------
# LLM 응답 형식 (위험 이유 설명)
# ---------------------------------------------------------------------------
class LLMExplanation(BaseModel):
    headline: str  # 한 줄 요약
    reasons: list[str]  # 근거 2~3개. 숫자는 입력으로 준 값만 인용
    caution: str  # 해석 주의 한 문장
