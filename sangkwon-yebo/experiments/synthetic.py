"""가상 분기 패널. 실제 데이터를 받기 전 코드 점검과 화면 개발에만 쓴다.

실제 서울 데이터와 아무 관련이 없다. 이 데이터의 실험 결과를 발표나 판정에 쓰지 않는다.
각 칸에 천천히 변하는 '숨은 위험도'를 두고, 폐업 수가 그 위험도를 따라가게 만들었다.
"""

import numpy as np
import pandas as pd

from core import config

INDUSTRIES = [
    ("CS100001", "한식음식점"), ("CS100002", "중식음식점"), ("CS100003", "일식음식점"),
    ("CS100004", "양식음식점"), ("CS100005", "제과점"), ("CS100006", "패스트푸드점"),
    ("CS100007", "치킨전문점"), ("CS100008", "분식전문점"), ("CS100009", "호프-간이주점"),
    ("CS100010", "커피-음료"),
]
AREA_TYPES = ["골목상권", "발달상권", "전통시장"]


def make_panel(n_areas: int = 80, years=range(2019, 2026), seed: int = config.RANDOM_SEED) -> pd.DataFrame:
    """PANEL_REQUIRED 열과 sales_amount를 가진 가상 분기 패널."""
    rng = np.random.default_rng(seed)
    rows = []
    ind_effect = rng.normal(0, 0.3, len(INDUSTRIES))
    for a in range(n_areas):
        area_code = f"9{a:06d}"
        area_type = AREA_TYPES[a % len(AREA_TYPES)]
        area_effect = rng.normal(0, 0.4)
        for i, (ind_code, ind_name) in enumerate(INDUSTRIES):
            base_stores = max(1, int(rng.lognormal(2.3, 0.7)))
            risk = rng.normal(0, 1)
            stores = base_stores
            for y in years:
                risk = 0.8 * risk + rng.normal(0, 0.6)  # 해마다 조금씩 변하는 숨은 위험도
                p_close = 1 / (1 + np.exp(-(-3.2 + 0.6 * risk + area_effect + ind_effect[i])))
                for q in range(1, 5):
                    close = rng.binomial(stores, p_close)
                    opened = rng.binomial(max(stores, 1), 0.05)
                    stores = max(0, stores - close + opened)
                    franchise = rng.binomial(stores, 0.2) if stores else 0
                    sales = stores * rng.lognormal(17.5 - 0.15 * risk, 0.3) if stores else np.nan
                    rows.append({
                        "quarter_code": y * 10 + q, "year": y, "quarter": q,
                        "area_code": area_code, "area_name": f"가상상권{a}", "area_type": area_type,
                        "industry_code": ind_code, "industry_name": ind_name,
                        "stores": stores + close, "open_stores": opened, "close_stores": close,
                        "franchise_stores": franchise, "sales_amount": sales,
                    })
    return pd.DataFrame(rows)
