"""API 동작 검증. DB·Redis·LLM 없이 가짜로 바꿔서 CI에서도 돈다."""

import json
from dataclasses import dataclass, field

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.api import guard
from app.api import main as api
from app.config import get_settings


@dataclass
class FakeResult:
    answer: str = "카카오의 취득 기간은 2026년 11월 06일부터 2027년 02월 05일까지입니다[1]."
    unanswerable: bool = False
    model: str = "fake-model"
    sources: list = field(
        default_factory=lambda: [
            {"rcept_no": "20261105000008", "title": "카카오 | 자기주식취득결정", "url": "https://x"}
        ]
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test")
    monkeypatch.setenv("RATE_LIMIT_PER_IP_DAILY", "2")
    get_settings.cache_clear()
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(guard, "client", lambda: fake)

    calls = {"agent": 0}

    def fake_agent(question, model):
        calls["agent"] += 1
        yield "step", {"node": "analyze", "label": "질문 분석", "detail": "analyze"}
        yield "step", {"node": "retrieve", "label": "공시 검색", "detail": "retrieve"}
        yield "result", FakeResult()

    monkeypatch.setattr(api, "run_agent_stream", fake_agent)
    monkeypatch.setattr(api, "list_companies", lambda: [{"corp_name": "카카오"}])
    monkeypatch.setattr(api, "db_ok", lambda: True)
    c = TestClient(api.app)
    c.calls = calls
    yield c
    get_settings.cache_clear()


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_health_and_companies(client):
    assert client.get("/health").json() == {"status": "ok", "db": True, "redis": True}
    assert client.get("/companies").json() == [{"corp_name": "카카오"}]


def test_ask_json(client):
    r = client.post("/ask", json={"question": "카카오 자사주 기간", "stream": False})
    body = r.json()
    assert r.status_code == 200
    assert body["sources"][0]["rcept_no"] == "20261105000008"
    assert body["steps"] == ["질문 분석", "공시 검색"]
    assert body["cached"] is False


def test_ask_stream_sends_steps_then_result(client):
    r = client.post("/ask", json={"question": "카카오 자사주 기간"})
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _events(r.text)
    assert [e for e, _ in events] == ["step", "step", "result", "done"]
    assert events[2][1]["answer"].startswith("카카오")


def test_same_question_is_served_from_cache(client):
    client.post("/ask", json={"question": "카카오 자사주 기간", "stream": False})
    # 공백·물음표가 달라도 같은 질문으로 본다
    r = client.post("/ask", json={"question": "  카카오  자사주 기간? ", "stream": False})
    assert r.json()["cached"] is True
    assert client.calls["agent"] == 1  # 에이전트(=LLM 비용)는 한 번만


def test_rate_limit_per_ip_but_cache_hits_are_free(client):
    for q in ["질문 하나", "질문 둘"]:
        assert client.post("/ask", json={"question": q, "stream": False}).status_code == 200
    r = client.post("/ask", json={"question": "질문 셋", "stream": False})
    assert r.status_code == 429
    # 이미 답한 질문은 한도와 상관없이 캐시에서 나간다
    assert client.post("/ask", json={"question": "질문 하나", "stream": False}).status_code == 200


def test_validation(client):
    assert client.post("/ask", json={"question": "a"}).status_code == 422
    assert client.post("/ask", json={"question": "가" * 301}).status_code == 422


def test_redis_down_fails_open(client, monkeypatch):
    import redis

    class Down:
        def __getattr__(self, name):
            def boom(*a, **k):
                raise redis.ConnectionError("down")

            return boom

    monkeypatch.setattr(guard, "client", lambda: Down())
    r = client.post("/ask", json={"question": "레디스 없이", "stream": False})
    assert r.status_code == 200 and r.json()["cached"] is False
