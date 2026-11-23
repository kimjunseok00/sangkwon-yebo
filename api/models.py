"""API 응답 형식. FastAPI가 이 정의로 자동 문서(/docs)를 만든다.

금융기관 시스템이 읽는 계약서이므로, 필드를 빼거나 이름을 바꾸면 버전(/v1 → /v2)을 올린다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    close_rate: float | None = Field(description="기준 연도 폐업률")
    close_rate_3y: float | None = Field(description="최근 3년 평균 폐업률")
    stores_avg: float | None = Field(description="기준 연도 평균 점포 수")


class TrackRecord(BaseModel):
    """이 점수를 믿어도 되는지 판단할 근거: 과거 맞히기 성적."""

    test_years: list[int]
    model_auc: dict[int, float | None] = Field(description="연도별 모델 AUC")
    best_baseline_auc: dict[int, float | None] = Field(description="연도별 단순 기준선 중 나은 쪽 AUC")
    gate_passed: bool = Field(description="사전에 정한 통과 기준을 넘었는지")
    caution_hit_rate: dict[int, float | None] = Field(
        default_factory=dict, description="연도별 '주의' 예보 적중률(주의로 예보한 곳 중 실제 다음 해 상위 25% 비율)")
    caution_base_rate: dict[int, float | None] = Field(
        default_factory=dict, description="비교 기준: 아무 곳이나 골랐을 때 상위 25%였던 비율")


class RiskResponse(BaseModel):
    dataset: str
    area_code: str
    area_name: str | None
    industry_code: str
    industry_name: str | None
    base_year: int
    predict_year: int
    level: str = Field(description="예보 단계: 평이 / 관심 / 주의(같은 업종 안 상위 25%)")
    rank_in_industry: int = Field(description="같은 업종 안 위험 순위(1 = 가장 위험)")
    n_in_industry: int = Field(description="같은 업종 칸 수. 'N곳 중 k번째'")
    percentile: float = Field(description="같은 업종 안 위험 백분위(0~1)")
    score: float = Field(description="모델 점수. 확률로 해석하지 않는다")
    evidence: Evidence
    track_record: TrackRecord
    caution: str
    warning: str | None = Field(default=None, description="가상 데이터일 때 경고")


class AreaHit(BaseModel):
    area_code: str
    area_name: str | None
    area_type: str | None


class DatasetInfo(BaseModel):
    name: str
    source: str
    built_at: str
    base_year: int | None
    n_cells: int
    gate_passed: bool


class Health(BaseModel):
    status: str
    datasets: list[DatasetInfo]
