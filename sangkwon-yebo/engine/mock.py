"""가짜 설명. 실제 엔진과 입출력이 같다. 화면 개발용."""

from core.schemas import LLMExplanation

_NAMES = {
    "close_rate": "올해 폐업률", "close_rate_prev": "작년 폐업률", "close_rate_3y": "3년 평균 폐업률",
    "close_rate_rel": "업종 평균 대비 폐업률", "open_rate": "개업률", "store_growth": "점포 수 증감",
    "franchise_share": "프랜차이즈 비율", "log_stores": "점포 규모",
    "industry_close_mean": "업종 전체 분위기", "sales_per_store_growth": "점포당 매출 증감",
}


def explain(row: dict, risk_score: float, top_factors: list[tuple[str, float]]) -> LLMExplanation:
    reasons = [f"{_NAMES.get(name, name)}이(가) 위험을 높이는 쪽으로 작용" for name, _ in top_factors[:3]]
    return LLMExplanation(
        headline=f"[가짜 설명] {row.get('area_name', '?')} {row.get('industry_name', '?')}: 위험 점수 {risk_score:.2f}",
        reasons=reasons or ["주요 요인 정보 없음"],
        caution="과거 통계 기반 참고 정보이며, 개별 점포의 성패를 보장하지 않습니다.",
    )
