"""금융기관용 상권 위험 예측 API (FastAPI).

구조
  요청 → [호출 기록 미들웨어] → [API 키 확인] → [store에서 미리 계산된 점수 조회] → 응답
  - 점수는 experiments.publish가 미리 만든 파일만 읽는다. 요청마다 모델을 돌리지 않는다.
  - 모든 응답에 과거 성적(track_record)과 주의 문구를 같이 싣는다. '점수만 주는 API'가 되지 않게.

실행(개발): uvicorn api.main:app --reload    → http://127.0.0.1:8000/docs 에서 직접 호출해 볼 수 있다
키: .env의 API_KEYS (쉼표 구분). 요청 헤더 `X-API-Key: <키>`
"""

# 주의: 'from __future__ import annotations'를 넣지 않는다. create_app 안에서 정의한 의존성
# (get_dataset, require_key)을 FastAPI가 문자열 타입 표기로는 찾지 못해 422 오류가 난다.

import hashlib
import json
import math
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security, status
from fastapi.security import APIKeyHeader

from api.models import AreaHit, DatasetInfo, Evidence, Health, RiskResponse, TrackRecord
from api.store import Dataset, load_all
from core import config

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
SYNTHETIC_WARNING = "가상 데이터로 만든 결과입니다. 실제 상권 판단에 쓰지 마세요."


def _key_id(key: str | None) -> str | None:
    """호출 기록에는 키 원문 대신 해시 앞 8자리만 남긴다(기록 파일이 새도 키가 새지 않게)."""
    return hashlib.sha256(key.encode()).hexdigest()[:8] if key else None


def _nan_to_none(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def _track_record(ds: Dataset) -> TrackRecord:
    """성적표에서 연도별 모델 AUC와 '더 나은 기준선' AUC를 뽑는다."""
    sc = ds.scorecard
    pivot = sc.pivot(index="test_year", columns="method", values="auc")
    baselines = [c for c in pivot.columns if c != "model"]
    return TrackRecord(
        test_years=[int(y) for y in pivot.index],
        model_auc={int(y): _nan_to_none(round(float(v), 4)) for y, v in pivot["model"].items()},
        best_baseline_auc={int(y): _nan_to_none(round(float(v), 4)) for y, v in pivot[baselines].max(axis=1).items()},
        gate_passed=bool(ds.meta.get("gate_passed", False)),
        caution_hit_rate={int(y): v.get("hit_rate") for y, v in ds.meta.get("caution_hit_rate", {}).items()},
        caution_base_rate={int(y): v.get("base_rate") for y, v in ds.meta.get("caution_hit_rate", {}).items()},
    )


def create_app(published_dir: Path | None = None, api_keys: tuple[str, ...] | None = None,
               log_path: Path | None = None) -> FastAPI:
    """앱 공장. 테스트에서 폴더·키·기록 경로를 바꿔 끼울 수 있게 함수로 만든다."""
    published_dir = published_dir or config.PUBLISHED_DIR
    keys = api_keys if api_keys is not None else config.API_KEYS
    log_path = log_path or config.API_LOG_PATH
    log_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 서버가 켜질 때 한 번만 파일을 읽는다
        app.state.datasets = load_all(published_dir)
        yield

    app = FastAPI(
        title="상권예보 API",
        version="1.0.0",
        description=(
            "지역 × 업종별 다음 해 폐업 위험(같은 업종 안 상대 순위)을 돌려준다. "
            "모든 응답에 과거 맞히기 성적과 주의 문구가 함께 들어 있다. " + config.CAUTION_TEXT
        ),
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def log_calls(request: Request, call_next):
        """모든 호출을 JSON 한 줄씩 기록한다. 금융기관별 사용량 집계·과금의 근거가 된다."""
        start = time.perf_counter()
        response = await call_next(request)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "key_id": _key_id(request.headers.get("X-API-Key")),
            "method": request.method,
            "path": request.url.path,
            "query": dict(request.query_params),
            "status": response.status_code,
            "ms": round((time.perf_counter() - start) * 1000, 1),
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_lock, log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return response

    def require_key(key: Annotated[str | None, Security(API_KEY_HEADER)]) -> str:
        """키가 없거나 틀리면 401. 비교는 시간 차이로 키를 추측하지 못하게 compare_digest로."""
        if not keys:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "서버에 API 키가 설정되지 않았습니다.")
        if key is None or not any(secrets.compare_digest(key, k) for k in keys):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API 키가 없거나 올바르지 않습니다.")
        return key

    def get_dataset(request: Request, dataset: str = Query("seoul", description="seoul 또는 national")) -> Dataset:
        datasets: dict[str, Dataset] = request.app.state.datasets
        if dataset not in datasets:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"데이터셋 '{dataset}'이 없습니다. 있는 것: {sorted(datasets)}")
        return datasets[dataset]

    @app.get("/health", response_model=Health, tags=["상태"])
    def health(request: Request) -> Health:
        """키 없이 호출 가능. 어떤 데이터셋이 언제 만들어졌는지 보여준다."""
        datasets: dict[str, Dataset] = request.app.state.datasets
        return Health(
            status="ok" if datasets else "no_data",
            datasets=[DatasetInfo(**{k: d.meta.get(k) for k in DatasetInfo.model_fields}) for d in datasets.values()],
        )

    @app.get("/v1/scorecard", tags=["성적표"])
    def scorecard(ds: Annotated[Dataset, Depends(get_dataset)]) -> dict:
        """과거 맞히기 성적 전체. 키 없이 공개한다(성적을 숨기지 않는다는 원칙)."""
        records = ds.scorecard.astype(object).where(ds.scorecard.notna(), None).to_dict(orient="records")
        return {"dataset": ds.name, "source": ds.meta.get("source"), "gate_passed": ds.meta.get("gate_passed"),
                "results": records}

    @app.get("/v1/areas", response_model=list[AreaHit], tags=["조회"])
    def areas(ds: Annotated[Dataset, Depends(get_dataset)], _: Annotated[str, Depends(require_key)],
              q: str = Query(..., min_length=1, description="지역 이름 일부. 예: 마포, 망원")) -> list[AreaHit]:
        return [AreaHit(**h) for h in ds.search_areas(q)]

    @app.get("/v1/risk", response_model=RiskResponse, tags=["조회"])
    def risk(ds: Annotated[Dataset, Depends(get_dataset)], _: Annotated[str, Depends(require_key)],
             area_code: str = Query(..., description="지역 코드(/v1/areas로 찾기)"),
             industry_code: str = Query(..., description="업종 코드")) -> RiskResponse:
        row = ds.get(area_code, industry_code)
        if row is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "해당 지역·업종 점수가 없습니다(점포가 너무 적어 계산하지 않은 칸일 수 있습니다).",
            )
        return RiskResponse(
            dataset=ds.name,
            area_code=area_code,
            area_name=row.get("area_name"),
            industry_code=industry_code,
            industry_name=row.get("industry_name"),
            base_year=int(row["base_year"]),
            predict_year=int(row["predict_year"]),
            level=row["level"],
            rank_in_industry=int(row["rank_in_industry"]),
            n_in_industry=int(row["n_in_industry"]),
            percentile=round(float(row["percentile"]), 4),
            score=round(float(row["score"]), 4),
            evidence=Evidence(**{k: _nan_to_none(row.get(k)) for k in Evidence.model_fields}),
            track_record=_track_record(ds),
            caution=config.CAUTION_TEXT,
            warning=SYNTHETIC_WARNING if ds.meta.get("source") == "synthetic" else None,
        )

    return app


app = create_app()
