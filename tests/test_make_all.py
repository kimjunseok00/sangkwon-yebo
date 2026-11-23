"""명령 하나로 서울판·전국판 결과를 만들고, 화면이 그 결과만 읽어 뜨는지 확인한다."""

import json

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core import config
from core.published import load_all
from experiments.make_all import make_all
from experiments.synthetic import make_panel
from ingest.seoul import COLUMN_MAP_STORE

APP = config.ROOT / "app.py"


def _write_seoul_raw(raw_dir):
    """가상 패널을 서울시 원본 열 이름으로 되돌려 연도별 store_*.csv로 쓴다(실제 파일과 같은 길을 타게)."""
    panel = make_panel(n_areas=25)
    back = {v: k for k, v in COLUMN_MAP_STORE.items()}
    raw = panel[list(back)].rename(columns=back).astype(str)
    for year, part in raw.groupby(panel["year"]):
        part.to_csv(raw_dir / f"store_{year}.csv", index=False, encoding="cp949")


def _write_national_raw(raw_dir, n=3000, seed=0):
    rng = np.random.default_rng(seed)
    open_d = pd.Timestamp("2012-01-01") + pd.to_timedelta(rng.integers(0, 5000, n), unit="D")
    close_d = open_d + pd.to_timedelta(rng.exponential(1500, n).astype(int), unit="D")
    closed = close_d < pd.Timestamp("2026-06-30")
    area = rng.integers(0, 8, n)
    pd.DataFrame({
        "개방자치단체코드": (3000000 + area * 10000).astype(str),
        "업태구분명": rng.choice(["한식", "분식", "기타"], n),
        "인허가일자": open_d.strftime("%Y%m%d"),
        "영업상태명": np.where(closed, "폐업", "영업/정상"),
        "폐업일자": np.where(closed, close_d.strftime("%Y%m%d"), ""),
        "지번주소": [f"경기도 가상{a}군 어느읍 1" for a in area],
        "도로명주소": "",
    }).to_csv(raw_dir / "localdata_food.csv", index=False, encoding="cp949")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("work")
    raw, processed = root / "raw", root / "processed"
    raw.mkdir()
    _write_seoul_raw(raw)
    _write_national_raw(raw)
    summary = make_all(raw, processed)
    return processed, summary


def test_both_datasets_published(built):
    processed, summary = built
    assert set(summary) == {"seoul", "national"}
    assert all(m["source"] == "real" for m in summary.values())
    loaded = load_all(processed / "published")
    assert set(loaded) == {"seoul", "national"}
    meta = json.loads((processed / "published" / "national" / "meta.json").read_text(encoding="utf-8"))
    assert "gate_detail" in meta and "gate_gain_per_year" in meta


def test_missing_source_is_skipped(tmp_path):
    (tmp_path / "raw").mkdir()
    summary = make_all(tmp_path / "raw", tmp_path / "processed")
    assert all("skipped" in v for v in summary.values())


def test_app_reads_published_files(built, monkeypatch):
    """화면이 실험을 다시 돌리지 않고 published/를 읽어 서울판·전국판을 모두 띄운다."""
    processed, _ = built
    monkeypatch.setattr(config, "PUBLISHED_DIR", processed / "published")
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    assert not at.warning  # 실제 결과이므로 가상 데이터 경고가 없어야 한다
    assert set(at.radio[0].options) == {"전국판 (시군구 단위)", "서울판 (상권 단위)"}
    assert any(config.CAUTION_TEXT in c.value for c in at.caption)


def test_app_falls_back_to_synthetic(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PUBLISHED_DIR", tmp_path / "empty")
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    assert at.warning and "가상 데이터" in at.warning[0].value
