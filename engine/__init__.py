"""위험 이유 설명. USE_MOCK=1이면 문장 틀로, 0이면 Gemini로 만든다."""

from core import config

if config.USE_MOCK:
    from engine.mock import explain
else:
    from engine.explain import explain

__all__ = ["explain"]
