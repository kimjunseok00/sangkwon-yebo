"""서비스용 결과 만들기: 성적표 + 최신 연도 위험 점수 + 메타정보.

API 서버(api/)와 화면이 읽는 파일을 여기서 한 번에 만든다. 자동 갱신(#22)도 이 명령 하나를 돌린다.
  1) 과거 맞히기 실험(run_backtest)으로 성적표를 만든다 → scorecard.csv
  2) 정답이 있는 모든 연도로 모델을 다시 학습한다
  3) 정답이 아직 없는 최신 연도(예: 2025년 특징 → 2026년 예측)에 점수를 매긴다 → scores.csv
  4) 언제, 어떤 데이터로 만들었는지 기록한다 → meta.json

실행: python -m experiments.publish --data data/processed/dataset.csv --name seoul
      python -m experiments.publish --synthetic --name seoul   (가상 데이터로 점검)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from core import config
from core.schemas import FEATURES, KEYS, SCORE_COLUMNS, TARGET
from experiments.backtest import gate, run_backtest
from models import model as model_mod


def latest_scores(data: pd.DataFrame) -> pd.DataFrame:
    """정답이 있는 행 전부로 학습하고, 정답이 없는 가장 최근 연도에 점수를 매긴다.

    최근 연도 행은 정답이 없으므로(다음 해가 아직 안 옴) 학습에 절대 섞이지 않는다.
    """
    labeled = data[data[TARGET].notna()]
    latest_year = int(data["year"].max())
    target_rows = data[(data["year"] == latest_year) & (data["stores_avg"] >= config.MIN_STORES)].copy()
    if latest_year <= int(labeled["year"].max()):
        # 최신 연도에도 정답이 있다면 데이터가 한 해 더 있어야 '미래 예측'이 된다. 조용히 넘어가지 않는다.
        raise ValueError(f"최신 연도 {latest_year}에도 정답이 있습니다. 예측할 미래 연도가 없습니다.")
    fitted = model_mod.fit(labeled, FEATURES)
    target_rows["score"] = model_mod.predict_score(fitted, target_rows, FEATURES)
    # 업종 안 백분위: 점수 자체보다 '같은 업종에서 상위 몇 %'가 해석하기 쉽다
    target_rows["percentile"] = target_rows.groupby("industry_code")["score"].rank(pct=True)
    target_rows["level"] = pd.cut(
        target_rows["percentile"], bins=[0, 0.5, config.RISK_QUANTILE, 1.0],  # 상위 25% = 정답 정의와 같은 선
        labels=["낮은 편", "보통", "높은 편"], include_lowest=True,
    ).astype(str)
    target_rows["base_year"] = latest_year
    target_rows["predict_year"] = latest_year + 1
    return target_rows[SCORE_COLUMNS].sort_values(KEYS).reset_index(drop=True)


def publish(data: pd.DataFrame, out_dir: Path, name: str, source: str) -> dict:
    """세 파일을 out_dir/name/ 아래에 쓰고 메타정보를 돌려준다."""
    target = out_dir / name
    target.mkdir(parents=True, exist_ok=True)
    results = run_backtest(data)
    verdict = gate(results)
    scores = latest_scores(data)
    results.to_csv(target / "scorecard.csv", index=False)
    scores.to_csv(target / "scores.csv", index=False)
    meta = {
        "name": name,
        "source": source,  # "real" 또는 "synthetic". 가상 데이터면 API 응답에 경고를 붙인다
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_year": int(scores["base_year"].iloc[0]) if len(scores) else None,
        "n_cells": int(len(scores)),
        "gate_passed": bool(verdict["passed"]),
        "test_years": list(config.TEST_FEATURE_YEARS),
    }
    (target / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, help="dataset.csv (features.build 결과)")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--name", default="seoul", help="seoul 또는 national")
    parser.add_argument("--out", type=Path, default=config.PROCESSED_DIR / "published")
    opts = parser.parse_args()
    if opts.synthetic:
        from experiments.synthetic import make_panel
        from features.build import build_dataset

        data, source = build_dataset(make_panel()), "synthetic"
    elif opts.data:
        data, source = pd.read_csv(opts.data, dtype={"area_code": str, "industry_code": str}), "real"
    else:
        parser.error("--data 또는 --synthetic 중 하나가 필요합니다.")
    meta = publish(data, opts.out, opts.name, source)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
