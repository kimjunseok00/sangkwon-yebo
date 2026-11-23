"""Gemini 호출을 한 곳에 모은다.

LLM 호출은 반드시 이 파일의 call_llm_json()을 거친다.
- 모델이나 회사를 바꿀 때 이 파일만 고치면 된다.
- 한도 초과 재시도, 호출 횟수 집계를 한 곳에서 처리한다.
"""

import time
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from core import config

T = TypeVar("T", bound=BaseModel)

# 호출 횟수와 토큰 사용량. 발표용 원가 계산에 쓴다.
usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

_client: genai.Client | None = None


class LLMError(RuntimeError):
    """LLM 호출 실패. 화면에서 잡아 사용자에게 안내한다."""


def _get_client() -> genai.Client:
    """클라이언트를 처음 쓸 때 한 번만 만든다."""
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise LLMError(".env에 GEMINI_API_KEY가 없습니다. 키를 넣거나 USE_MOCK=1로 실행하세요.")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def call_llm_json(
    prompt: str,
    schema: type[T],
    *,
    system: str | None = None,
    temperature: float = 0.0,
    max_retries: int = 3,
) -> T:
    """프롬프트를 보내고 schema 형식으로 검증된 결과를 돌려준다.

    Args:
        prompt: 사용자 프롬프트 전체.
        schema: 응답 형식. core/schemas.py의 LLM으로 시작하는 모델.
        system: 역할과 규칙을 적는 시스템 지시문.
        temperature: 채점처럼 일관성이 필요하면 0.
        max_retries: 한도 초과(429)나 서버 오류일 때 다시 시도하는 횟수.

    Raises:
        LLMError: 재시도 후에도 실패했거나 응답이 형식에 맞지 않을 때.
    """
    client = _get_client()
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=schema,
    )

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=cfg,
            )
        except errors.APIError as e:
            last_error = e
            # 429(한도 초과)와 5xx(서버 문제)만 기다렸다 다시 시도한다.
            # 그 외(잘못된 키, 잘못된 요청)는 다시 해도 같으므로 바로 알린다.
            if e.code == 429 or (e.code is not None and e.code >= 500):
                time.sleep(2 ** (attempt + 1))
                continue
            raise LLMError(f"Gemini 호출 실패({e.code}): {e.message}") from e

        usage["calls"] += 1
        meta = response.usage_metadata
        if meta is not None:
            usage["input_tokens"] += meta.prompt_token_count or 0
            usage["output_tokens"] += meta.candidates_token_count or 0

        # 안전 필터 등으로 본문이 비어 올 수 있다.
        if not response.text:
            raise LLMError("Gemini가 빈 응답을 돌려줬습니다.")
        try:
            return schema.model_validate_json(response.text)
        except ValueError as e:
            raise LLMError(f"응답이 {schema.__name__} 형식과 맞지 않습니다: {e}") from e

    raise LLMError(f"Gemini 호출이 {max_retries}회 실패했습니다: {last_error}")
