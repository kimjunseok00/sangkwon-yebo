"""금융기관용 API 테스트: 키 확인, 응답 형식, 성적표 공개, 호출 기록."""

import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core import config
from experiments.publish import publish
from experiments.synthetic import make_panel
from features.build import build_dataset

KEY = "test-key-123"


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    out = tmp_path_factory.mktemp("published")
    publish(build_dataset(make_panel(n_areas=30)), out, "seoul", "synthetic")
    return out


@pytest.fixture()
def client(published, tmp_path):
    log = tmp_path / "calls.jsonl"
    app = create_app(published_dir=published, api_keys=(KEY,), log_path=log)
    with TestClient(app) as c:  # with 블록이어야 lifespan(파일 읽기)이 실행된다
        c.log_path = log
        yield c


def _any_cell(client):
    ds = client.app.state.datasets["seoul"]
    row = ds.scores.iloc[0]
    return row["area_code"], row["industry_code"]


def test_health_without_key(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["datasets"][0]["source"] == "synthetic"


def test_risk_requires_key(client):
    area, ind = _any_cell(client)
    assert client.get("/v1/risk", params={"area_code": area, "industry_code": ind}).status_code == 401
    bad = client.get("/v1/risk", params={"area_code": area, "industry_code": ind}, headers={"X-API-Key": "nope"})
    assert bad.status_code == 401


def test_risk_response_has_track_record_and_caution(client):
    area, ind = _any_cell(client)
    r = client.get("/v1/risk", params={"area_code": area, "industry_code": ind}, headers={"X-API-Key": KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["caution"] == config.CAUTION_TEXT
    assert body["warning"]  # 가상 데이터 경고
    assert body["level"] in {"평이", "관심", "주의"}
    assert 1 <= body["rank_in_industry"] <= body["n_in_industry"]
    assert set(body["track_record"]["caution_hit_rate"]) == {str(y) for y in config.TEST_FEATURE_YEARS}
    assert body["predict_year"] == body["base_year"] + 1
    assert set(body["track_record"]["model_auc"]) == {str(y) for y in config.TEST_FEATURE_YEARS}


def test_unknown_cell_and_dataset_are_404(client):
    h = {"X-API-Key": KEY}
    assert client.get("/v1/risk", params={"area_code": "x", "industry_code": "y"}, headers=h).status_code == 404
    assert client.get("/v1/risk", params={"dataset": "mars", "area_code": "x", "industry_code": "y"},
                      headers=h).status_code == 404


def test_scorecard_is_public(client):
    r = client.get("/v1/scorecard")
    assert r.status_code == 200
    methods = {row["method"] for row in r.json()["results"]}
    assert "model" in methods and len(methods) == 3


def test_area_search(client):
    r = client.get("/v1/areas", params={"q": "가상상권1"}, headers={"X-API-Key": KEY})
    assert r.status_code == 200 and len(r.json()) >= 1


def test_calls_are_logged_without_raw_key(client):
    area, ind = _any_cell(client)
    client.get("/v1/risk", params={"area_code": area, "industry_code": ind}, headers={"X-API-Key": KEY})
    lines = client.log_path.read_text(encoding="utf-8").strip().splitlines()
    last = json.loads(lines[-1])
    assert last["path"] == "/v1/risk" and last["status"] == 200
    assert last["key_id"] and KEY not in lines[-1]  # 키 원문은 기록하지 않는다


def test_no_keys_configured_is_503(published, tmp_path):
    app = create_app(published_dir=published, api_keys=(), log_path=tmp_path / "l.jsonl")
    with TestClient(app) as c:
        assert c.get("/v1/areas", params={"q": "a"}, headers={"X-API-Key": "any"}).status_code == 503
