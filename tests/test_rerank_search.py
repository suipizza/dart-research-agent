"""run_search의 재순위 연결: 후보를 넉넉히 가져와 다시 정렬한 뒤 top_k개만 쓰는지 (모델 없이)."""

import sys
import types
from datetime import date

import pytest

from app.agent import tools
from app.config import get_settings
from app.rag.search import Hit


def _hit(i: int) -> Hit:
    return Hit(i / 100, "회사", date(2026, 1, 1), "공시", f"r{i}", f"text {i}")


def _plan(top_k: int, is_list: bool = False) -> tools.SearchPlan:
    return tools.SearchPlan(
        query="질문",
        corp_codes=None,
        since=None,
        until=None,
        categories=None,
        top_k=top_k,
        latest=False,
        is_list=is_list,
    )


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test")
    calls = {}

    def search(query, top_k, **kw):
        calls["top_k"] = top_k
        return [_hit(i) for i in range(top_k)], []

    def rerank(query, hits):
        calls["reranked"] = len(hits)
        return list(reversed(hits))  # 순서가 바뀌었는지 보이도록 뒤집는다

    monkeypatch.setattr(tools, "search", search)
    monkeypatch.setitem(sys.modules, "app.rag.rerank", types.SimpleNamespace(rerank=rerank))
    yield calls
    get_settings.cache_clear()


def test_rerank_pulls_pool_and_keeps_top_k(fake, monkeypatch):
    monkeypatch.setenv("RERANK", "true")
    monkeypatch.setenv("RERANK_POOL", "40")
    get_settings.cache_clear()
    hits = tools.run_search(_plan(top_k=12))
    assert fake["top_k"] == 40  # 후보는 40개
    assert fake["reranked"] == 40
    assert len(hits) == 12  # 근거로는 12개만
    assert hits[0].rcept_no == "r39"  # 재순위 순서를 따른다


def test_rerank_off_uses_vector_order(fake, monkeypatch):
    monkeypatch.setenv("RERANK", "false")
    get_settings.cache_clear()
    hits = tools.run_search(_plan(top_k=12))
    assert fake["top_k"] == 12
    assert "reranked" not in fake
    assert [h.rcept_no for h in hits[:2]] == ["r0", "r1"]


def test_pool_not_smaller_than_top_k(fake, monkeypatch):
    monkeypatch.setenv("RERANK", "true")
    monkeypatch.setenv("RERANK_POOL", "20")
    get_settings.cache_clear()
    hits = tools.run_search(_plan(top_k=30))
    assert fake["top_k"] == 30
    assert len(hits) == 30


def test_list_question_skips_rerank(fake, monkeypatch):
    monkeypatch.setenv("RERANK", "true")
    get_settings.cache_clear()
    hits = tools.run_search(_plan(top_k=40, is_list=True))  # 목록은 빠짐없이 모으는 게 우선
    assert fake["top_k"] == 40
    assert "reranked" not in fake
    assert hits[0].rcept_no == "r0"
