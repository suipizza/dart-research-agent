"""Langfuse 추적 (LLM 호출 관측).

키(LANGFUSE_PUBLIC_KEY / SECRET_KEY)가 없으면 아무것도 하지 않는다(CI·테스트·키 없는 로컬).

구조
    dart-agent (agent)                    질문 하나 = 추적 하나. 질문·답변·흐름·비용
     ├─ analyze (span)
     │   └─ claude:Analysis (generation)  모델·입출력·토큰·비용
     ├─ retrieve (retriever)
     ├─ generate (span)
     │   └─ claude:AnswerOut (generation)
     └─ verify (span)

스트리밍 응답은 단계마다 다른 스레드에서 실행될 수 있어 "현재 추적" 컨텍스트가 끊길 수 있다.
그래서 최상위 추적의 ID(trace_context)를 에이전트 상태에 담아 노드마다 명시적으로 넘긴다.
노드 안의 Claude 호출은 같은 스레드에서 일어나므로 현재 컨텍스트로 노드 아래에 붙는다.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache, wraps
from typing import Any

from app.config import get_settings

log = logging.getLogger("obs")


class _Noop:
    """키가 없을 때 쓰는 가짜 관측 객체."""

    id = None
    trace_id = None

    def update(self, **_: Any) -> "_Noop":
        return self

    def end(self, **_: Any) -> None:
        return None


def _ours_only(span) -> bool:
    """우리 코드가 직접 남긴 관측만 보낸다.

    Anthropic SDK도 자체 OpenTelemetry 기록(anthropic.messages.create)을 남기는데, 그대로 보내면
    같은 Claude 호출이 두 번 잡히고 비용도 두 배로 표시된다(실측 $0.0027 → $0.0050).
    """
    scope = getattr(span, "instrumentation_scope", None)
    return getattr(scope, "name", "") == "langfuse-sdk"


@lru_cache
def client():
    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=s.langfuse_public_key.get_secret_value(),
            secret_key=s.langfuse_secret_key.get_secret_value(),
            base_url=s.langfuse_host,
            should_export_span=_ours_only,
        )
    except Exception as e:  # 관측 실패가 서비스를 멈추게 하지 않는다
        log.warning("langfuse disabled: %s", e)
        return None


def enabled() -> bool:
    return client() is not None


def start_trace(name: str, *, input: Any = None, metadata: Any = None):
    """최상위 추적 시작. 반드시 end_trace로 닫는다. (span, trace_context) 반환."""
    c = client()
    if c is None:
        return _Noop(), None
    span = c.start_observation(name=name, as_type="agent", input=input, metadata=metadata)
    return span, {"trace_id": span.trace_id, "parent_span_id": span.id}


def end_trace(span, *, output: Any = None, metadata: Any = None) -> None:
    span.update(output=output, metadata=metadata)
    span.end()


@contextmanager
def observation(
    name: str, *, as_type: str = "span", trace_context: dict | None = None, **kwargs: Any
) -> Iterator[Any]:
    """관측 구간. trace_context가 있으면 그 추적 아래에, 없으면 현재 컨텍스트 아래에 붙는다."""
    c = client()
    if c is None:
        yield _Noop()
        return
    extra = {"trace_context": trace_context} if trace_context else {}
    with c.start_as_current_observation(name=name, as_type=as_type, **extra, **kwargs) as obs:
        yield obs


def traced_node(name: str, as_type: str = "span", summarize: Callable[[dict], Any] | None = None):
    """LangGraph 노드 데코레이터: 노드 실행을 관측 구간으로 남긴다."""

    def deco(fn):
        @wraps(fn)
        def wrapper(state):
            with observation(name, as_type=as_type, trace_context=state.get("trace_ctx")) as obs:
                out = fn(state)
                if summarize:
                    obs.update(output=summarize(out))
                return out

        return wrapper

    return deco


def flush() -> None:
    c = client()
    if c is not None:
        try:
            c.flush()
        except Exception as e:
            log.warning("langfuse flush failed: %s", e)


def trace_url(trace_id: str | None) -> str | None:
    c = client()
    if c is None or not trace_id:
        return None
    try:
        return c.get_trace_url(trace_id=trace_id)
    except Exception:
        return None
