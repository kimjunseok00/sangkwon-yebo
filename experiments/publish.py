"""서비스용 결과 만들기: 성적표 + 최신 예보 + 타임머신 기록 + 지도 좌표 + 메타정보.

화면(app.py)과 API(api/)는 여기서 만든 파일만 읽는다(core/published.py). 자동 갱신(#24)도 make_all을 통해 이걸 부른다.
  1) 과거 맞히기 실험(run_backtest)으로 성적표 → scorecard.csv
  2) 시험 연도마다 '그해 말 예보'와 '다음 해 실제 결과'를 칸별로 → history.csv (타임머신 화면)
  3) 정답이 있는 모든 연도로 다시 학습해, 정답이 아직 없는 최신 연도에 예보 → scores.csv
  4) (있으면) 지역 중심 좌표 → areas.csv (지도)
  5) 언제, 어떤 데이터로 만들었는지와 적중률 요약 → meta.json

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
from core.schemas import AREA_COLUMNS, FEATURES, HISTORY_COLUMNS, KEYS, LEVELS, SCORE_COLUMNS, TARGET
from experiments.backtest import gate, predict_test_year, run_backtest
from models import model as model_mod


def add_forecast_levels(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """score로 같은 그룹(업종, 필요하면 연도) 안의 백분위·순위·예보 단계를 붙인다.

    점수 자체는 확률처럼 오해되기 쉬워 화면에 쓰지 않는다. 대신 '같은 업종 N곳 중 k번째'와 단계로 보여 준다.
    단계 경계: 하위 50% 평이, 50~75% 관심, 상위 25% 주의(= 정답 정의 RISK_QUANTILE과 같은 선).
    """
    out = df.copy()
    g = out.groupby(group_cols)["score"]
    out["percentile"] = g.rank(pct=True)
    out["rank_in_industry"] = g.rank(ascending=False, method="first").astype(int)
    out["n_in_industry"] = g.transform("size").astype(int)
    out["level"] = pd.cut(
        out["percentile"], bins=[0, 0.5, config.RISK_QUANTILE, 1.0], labels=LEVELS, include_lowest=True,
    ).astype(str)
    return out


def latest_scores(data: pd.DataFrame) -> pd.DataFrame:
    """정답이 있는 행 전부로 학습하고, 정답이 없는 가장 최근 연도에 예보한다.

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
    target_rows = add_forecast_levels(target_rows, ["industry_code"])
    target_rows["base_year"] = latest_year
    target_rows["predict_year"] = latest_year + 1
    return target_rows[SCORE_COLUMNS].sort_values(KEYS).reset_index(drop=True)


def history(data: pd.DataFrame) -> pd.DataFrame:
    """시험 연도마다 그해 말 예보(단계·순위)와 다음 해 실제 결과를 칸별로 모은다(타임머신 화면).

    예보는 run_backtest와 같은 분할로 만든다: base_year의 예보는 base_year-1년까지의 정답으로만 학습한 모델이다.
    """
    parts = []
    for year in config.TEST_FEATURE_YEARS:
        pred = predict_test_year(data, year)
        if pred.empty:
            continue
        pred = add_forecast_levels(pred, ["industry_code"])
        pred = pred.assign(base_year=year, target_year=year + 1, actual_caution=pred[TARGET].astype(int))
        parts.append(pred[HISTORY_COLUMNS])
    if not parts:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    return pd.concat(parts, ignore_index=True)


def caution_hit_rate(hist: pd.DataFrame) -> dict[int, dict]:
    """연도별 '주의' 예보 적중률: 주의로 예보한 칸 중 실제로 다음 해 상위 25%였던 비율.

    비교 기준(base_rate)은 아무 칸이나 골랐을 때의 비율(약 25%). 화면의 '이 예보의 적중률'은 이 값을 쓴다.
    """
    out = {}
    for year, g in hist.groupby("base_year"):
        caution = g[g["level"] == LEVELS[-1]]
        out[int(year)] = {
            "n_caution": int(len(caution)),
            "hit_rate": round(float(caution["actual_caution"].mean()), 4) if len(caution) else None,
            "base_rate": round(float(g["actual_caution"].mean()), 4),
        }
    return out


def publish(data: pd.DataFrame, out_dir: Path, name: str, source: str,
            areas: pd.DataFrame | None = None) -> dict:
    """결과 파일을 out_dir/name/ 아래에 쓰고 메타정보를 돌려준다."""
    target = out_dir / name
    target.mkdir(parents=True, exist_ok=True)
    results = run_backtest(data)
    verdict = gate(results)
    scores = latest_scores(data)
    hist = history(data)
    results.to_csv(target / "scorecard.csv", index=False)
    scores.to_csv(target / "scores.csv", index=False)
    hist.to_csv(target / "history.csv", index=False)
    if areas is not None:
        areas[AREA_COLUMNS].to_csv(target / "areas.csv", index=False)
    meta = {
        "name": name,
        "source": source,  # "real" 또는 "synthetic". 가상 데이터면 화면·API가 경고를 붙인다
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_year": int(scores["base_year"].iloc[0]) if len(scores) else None,
        "n_cells": int(len(scores)),
        "gate_passed": bool(verdict["passed"]),
        "gate_detail": verdict["detail"],  # 화면에 그대로 보여 줄 판정 문장
        "gate_gain_per_year": verdict["per_year"],  # 연도별 '모델 AUC - 나은 기준선 AUC'
        "caution_hit_rate": caution_hit_rate(hist),  # 연도별 '주의' 예보 적중률과 무작위 기준
        "n_labeled_by_year": {int(y): int(n) for y, n in data[data[TARGET].notna()].groupby("year").size().items()},
        "has_areas": areas is not None,
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
