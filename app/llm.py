"""Claude API 공통: 클라이언트, 모델 이름, 가격, JSON 응답 호출."""

import json
from dataclasses import dataclass
from functools import lru_cache

import anthropic
from pydantic import BaseModel

from app.config import get_settings

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
OPUS = "claude-opus-5-5"
MODELS = {"haiku": HAIKU, "sonnet": SONNET, "opus": OPUS}

# 실험용 답변 모델 (0번 실험, 2026-11-19): Haiku 62% vs Sonnet 68%로 차이가 작고(53문항 중 3개),
# 두 모델이 모두 틀린 문항은 전부 검색 실패였다. 비용이 절반이라 비교 실험은 Haiku로 고정한다.
EXPERIMENT_MODEL = HAIKU

# 100만 토큰당 달러 (입력, 출력). 2026-11 기준 공식 가격. 비용 추적용.
PRICES = {HAIKU: (0.10, 0.50), SONNET: (2.0, 10.0), OPUS: (4.0, 20.0)}


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, model: str, u) -> None:
        self.input_tokens += u.input_tokens
        self.output_tokens += u.output_tokens
        p_in, p_out = PRICES[model]
        self.cost_usd += (u.input_tokens * p_in + u.output_tokens * p_out) / 1_000_000


@lru_cache
def client() -> anthropic.Anthropic:
    key = get_settings().anthropic_api_key
    if key is None:
        raise LLMError("ANTHROPIC_API_KEY가 설정되지 않았습니다 (.env 확인)")
    return anthropic.Anthropic(api_key=key.get_secret_value())


def call_json[T: BaseModel](
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    effort: str = "medium",
    max_tokens: int = 4000,
    usage: Usage | None = None,
) -> T:
    """JSON 스키마를 강제한 응답을 받아 pydantic 모델로 검증해 돌려준다.

    평가의 일관성을 위해 다른 모델로 넘어가는 fallback은 쓰지 않는다. 거절·잘림은 예외로 올린다.
    """
    json_schema = schema.model_json_schema()
    json_schema["additionalProperties"] = False
    resp = client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": json_schema},
        },
    )
    if usage is not None:
        usage.add(model, resp.usage)
    if resp.stop_reason == "refusal":
        raise LLMError(f"모델이 응답을 거절함: {getattr(resp, 'stop_details', None)}")
    if resp.stop_reason == "max_tokens":
        raise LLMError("max_tokens에 걸려 응답이 잘림")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if text is None:
        raise LLMError(f"텍스트 응답 없음 (stop_reason={resp.stop_reason})")
    return schema.model_validate(json.loads(text))
