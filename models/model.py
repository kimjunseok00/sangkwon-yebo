"""예측 모델. 첫 버전은 결측을 그대로 받는 그래디언트 부스팅. (개선은 이슈 #4, 팀원 A)

인터페이스만 지키면 안쪽은 바꿔도 된다: fit(train) → 모델, predict_score(모델, test) → 점수.
"""

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from core import config
from core.schemas import FEATURES, TARGET


def fit(train: pd.DataFrame, features: list[str] = FEATURES) -> HistGradientBoostingClassifier:
    """정답이 있는 행으로 학습한다. 특징 결측은 모델이 알아서 처리한다.

    단, 학습 데이터에서 '전부 결측'인 특징은 뺀다. HistGradientBoosting은 값이 하나도 없는 열을 받으면
    구간을 만들지 못해 멈춘다(전국판 인허가 데이터에는 프랜차이즈·매출 정보가 없다).
    실제로 쓴 특징은 model.used_features_에 남겨, 예측 때 같은 열만 쓰게 한다.
    """
    rows = train[train[TARGET].notna()]
    used = [f for f in features if rows[f].notna().any()]
    if not used:
        raise ValueError("학습 데이터에 값이 있는 특징이 하나도 없습니다.")
    # 과적합을 줄이려고 얕은 나무와 작은 학습률을 쓴다. 칸 수가 수천 개 수준이라 큰 모델이 필요 없다.
    model = HistGradientBoostingClassifier(
        max_depth=3,
        learning_rate=0.05,
        max_iter=200,
        l2_regularization=1.0,
        random_state=config.RANDOM_SEED,
    )
    model.fit(rows[used], rows[TARGET].astype(int))
    model.used_features_ = used
    return model


def predict_score(model: HistGradientBoostingClassifier, df: pd.DataFrame,
                  features: list[str] = FEATURES) -> pd.Series:
    """위험 점수(0~1). 높을수록 위험. 학습 때 실제로 쓴 특징만 쓴다."""
    used = getattr(model, "used_features_", features)
    return pd.Series(model.predict_proba(df[used])[:, 1], index=df.index)
