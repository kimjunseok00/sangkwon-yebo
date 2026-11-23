"""예측 모델. 첫 버전은 결측을 그대로 받는 그래디언트 부스팅. (개선은 이슈 #4, 팀원 A)

인터페이스만 지키면 안쪽은 바꿔도 된다: fit(train) → 모델, predict_score(모델, test) → 점수.
"""

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from core import config
from core.schemas import FEATURES, TARGET


def fit(train: pd.DataFrame, features: list[str] = FEATURES) -> HistGradientBoostingClassifier:
    """정답이 있는 행으로 학습한다. 특징 결측은 모델이 알아서 처리한다."""
    rows = train[train[TARGET].notna()]
    # 과적합을 줄이려고 얕은 나무와 작은 학습률을 쓴다. 칸 수가 수천 개 수준이라 큰 모델이 필요 없다.
    model = HistGradientBoostingClassifier(
        max_depth=3,
        learning_rate=0.05,
        max_iter=200,
        l2_regularization=1.0,
        random_state=config.RANDOM_SEED,
    )
    model.fit(rows[features], rows[TARGET].astype(int))
    return model


def predict_score(model: HistGradientBoostingClassifier, df: pd.DataFrame,
                  features: list[str] = FEATURES) -> pd.Series:
    """위험 확률(0~1). 높을수록 위험."""
    return pd.Series(model.predict_proba(df[features])[:, 1], index=df.index)
