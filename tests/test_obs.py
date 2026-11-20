"""Langfuse 키가 없으면 추적은 아무것도 하지 않아야 한다 (CI·테스트 환경)."""

import pytest

from app import obs
from app.config import Settings


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.setattr(obs, "get_settings", lambda: Settings(_env_file=None, dart_api_key="x"))
    obs.client.cache_clear()
    yield
    obs.client.cache_clear()


def test_disabled_without_keys(no_keys):
    assert obs.enabled() is False
    span, ctx = obs.start_trace("t", input={"q": 1})
    assert ctx is None
    obs.end_trace(span, output="done")  # 예외 없이 지나가야 한다
    with obs.observation("x", as_type="generation", model="m") as o:
        o.update(output="y")
    obs.flush()


def test_traced_node_passes_through(no_keys):
    @obs.traced_node("n", summarize=lambda out: out)
    def node(state):
        return {"value": state["x"] + 1}

    assert node({"x": 1, "trace_ctx": None}) == {"value": 2}
