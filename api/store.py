"""발표된 결과 파일(experiments.publish가 만든 것)을 메모리에 올려 두고 조회한다.

API는 요청마다 모델을 돌리지 않는다. 점수는 미리 계산해 두고 조회만 한다.
  - 응답이 빠르고, 같은 질문에 항상 같은 답이 나온다.
  - 어떤 모델·데이터로 만든 점수인지 meta.json으로 추적된다.
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
    return Dataset(name=meta["name"], meta=meta, scores=scores, scorecard=scorecard)


def load_all(published_dir: Path) -> dict[str, Dataset]:
    """published_dir 아래의 모든 데이터셋. 하나도 없으면 빈 dict."""
    if not published_dir.exists():
        return {}
    return {
        d.name: load_dataset(d)
        for d in sorted(published_dir.iterdir())
        if d.is_dir() and (d / "meta.json").exists()
    }
