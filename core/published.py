"""서비스용 결과 파일(published/)을 읽는 공통 모듈. 화면(app.py)과 API(api/)가 함께 쓴다.

왜 공통 모듈인가
  published/<seoul|national>/ 폴더(experiments.publish가 만든 scores.csv, scorecard.csv, meta.json)를
  '유일한 정답'으로 삼는다. 화면과 API가 같은 파일을 같은 코드로 읽으므로 숫자가 어긋나지 않는다.
  둘 다 요청마다 모델을 돌리지 않고 미리 계산된 값을 조회만 한다(빠르고, 같은 질문에 같은 답).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from core.schemas import SCORE_COLUMNS, require_columns


@dataclass
class Dataset:
    """데이터셋 하나(seoul 또는 national)의 점수·성적표·메타정보."""

    name: str
    meta: dict
    scores: pd.DataFrame
    scorecard: pd.DataFrame
    history: pd.DataFrame | None = None  # 타임머신: 시험 연도별 예보와 실제 결과(없을 수 있음)
    areas: pd.DataFrame | None = None  # 지도: 지역 중심 좌표(없을 수 있음)
    _index: dict[tuple[str, str], dict] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # (지역 코드, 업종 코드) → 행. 조회를 O(1)로 하기 위해 한 번만 만든다.
        self._index = {
            (str(r["area_code"]), str(r["industry_code"])): r
            for r in self.scores.to_dict(orient="records")
        }

    def get(self, area_code: str, industry_code: str) -> dict | None:
        return self._index.get((area_code, industry_code))

    def search_areas(self, query: str, limit: int = 20) -> list[dict]:
        """지역 이름 일부로 코드 찾기. 금융기관 담당자가 코드를 외우지 않아도 되게."""
        areas = self.scores[["area_code", "area_name", "area_type"]].drop_duplicates("area_code")
        hit = areas[areas["area_name"].fillna("").str.contains(query, regex=False)]
        return hit.head(limit).to_dict(orient="records")


def load_dataset(path: Path) -> Dataset:
    """published/<이름>/ 폴더 하나를 읽는다. 파일이 빠졌으면 무엇이 빠졌는지 알려 준다."""
    for f in ("meta.json", "scores.csv", "scorecard.csv"):
        if not (path / f).exists():
            raise FileNotFoundError(f"{path / f} 가 없습니다. `python -m experiments.publish`를 먼저 실행하세요.")
    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    scores = pd.read_csv(path / "scores.csv", dtype={"area_code": str, "industry_code": str})
    require_columns(scores, SCORE_COLUMNS, f"{path}/scores.csv")
    scorecard = pd.read_csv(path / "scorecard.csv")
    key_types = {"area_code": str, "industry_code": str}
    hist = pd.read_csv(path / "history.csv", dtype=key_types) if (path / "history.csv").exists() else None
    areas = pd.read_csv(path / "areas.csv", dtype={"area_code": str}) if (path / "areas.csv").exists() else None
    return Dataset(name=meta["name"], meta=meta, scores=scores, scorecard=scorecard, history=hist, areas=areas)


def load_all(published_dir: Path) -> dict[str, Dataset]:
    """published_dir 아래의 모든 데이터셋. 하나도 없으면 빈 dict."""
    if not published_dir.exists():
        return {}
    return {
        d.name: load_dataset(d)
        for d in sorted(published_dir.iterdir())
        if d.is_dir() and (d / "meta.json").exists()
    }


def synthetic_fallback(out_dir: Path) -> dict[str, Dataset]:
    """실제 결과가 하나도 없을 때 화면 개발용 가상 결과를 out_dir에 만들어 읽는다.

    meta.json의 source가 'synthetic'으로 남으므로, 화면·API는 이 값을 보고 경고를 띄운다.
    """
    from experiments.publish import publish  # 순환 import를 피하려고 함수 안에서 가져온다
    from experiments.synthetic import make_panel
    from features.build import build_dataset

    publish(build_dataset(make_panel()), out_dir, "synthetic", "synthetic")
    return load_all(out_dir)
