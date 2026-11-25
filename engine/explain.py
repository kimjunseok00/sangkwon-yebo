"""Gemini로 '이 칸이 왜 위험한가'를 쉬운 말로 설명한다. (이슈 #8, 이민준)"""

from core.schemas import LLMExplanation


def explain(row: dict, risk_score: float, top_factors: list[tuple[str, float]]) -> LLMExplanation:
    """한 칸(상권×업종)의 위험 점수와 주요 요인을 받아 설명을 만든다.

    Args:
        row: 그 칸의 특징 값(area_name, industry_name, close_rate 등).
        risk_score: 모델 위험 확률.
        top_factors: (특징 이름, 기여도) 상위 3개. 기여도 계산은 이슈 #8에서 정한다.

    구현 안내:
        - core.llm.call_llm_json(prompt, LLMExplanation)으로 호출. 프롬프트는 prompts/explain.txt.
        - 숫자는 입력으로 준 값만 인용하게 한다. 모델이 숫자를 지어내지 못하게 프롬프트에 명시한다.
        - '망한다', '반드시' 같은 단정 표현을 금지하고, caution에 '과거 통계 기반 참고 정보'임을 적게 한다.
        - 같은 칸은 결과를 저장해 다시 호출하지 않는다(무료 한도 절약).
    """
    raise NotImplementedError("이슈 #8에서 구현")
