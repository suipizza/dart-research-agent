"""DART 응답 코드 처리를 가짜 HTTP 응답(MockTransport)으로 검증한다."""

import httpx
import pytest

from app.ingest.dart_client import DartClient, DartError, _year_windows


def make_client(handler) -> DartClient:
    return DartClient(
        api_key="test",
        base_url="https://example.test/api",
        min_interval=0,
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )


def test_ok_returns_list():
    client = make_client(lambda r: httpx.Response(200, json={"status": "000", "list": [{"a": 1}]}))
    assert client.get_json("/x.json") == [{"a": 1}]


def test_no_data_returns_empty():
    client = make_client(lambda r: httpx.Response(200, json={"status": "013", "message": "없음"}))
    assert client.get_json("/x.json") == []


def test_invalid_key_raises():
    client = make_client(
        lambda r: httpx.Response(200, json={"status": "010", "message": "키 오류"})
    )
    with pytest.raises(DartError) as e:
        client.get_json("/x.json")
    assert e.value.status == "010"


def test_key_is_sent_as_param():
    seen = {}

    def handler(request: httpx.Request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"status": "000", "list": []})

    make_client(handler).get_json("/x.json", corp_code="00126380")
    assert seen["crtfc_key"] == "test"
    assert seen["corp_code"] == "00126380"


def test_list_filings_follows_pages():
    def handler(request: httpx.Request):
        page = int(request.url.params["page_no"])
        return httpx.Response(
            200, json={"status": "000", "total_page": 2, "list": [{"rcept_no": str(page)}]}
        )

    items = make_client(handler).list_filings("00126380", "20260101", "20261119")
    assert [x["rcept_no"] for x in items] == ["1", "2"]


def test_binary_error_xml_raises():
    body = "<result><status>014</status><message>파일이 존재하지 않습니다</message></result>"
    client = make_client(lambda r: httpx.Response(200, text=body))
    with pytest.raises(DartError) as e:
        client.document_zip("00000000000000")
    assert e.value.status == "014"


def test_empty_body_is_retried(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, text="")  # DART가 가끔 보내는 빈 응답
        return httpx.Response(200, json={"status": "000", "list": [{"ok": True}]})

    client = DartClient(
        api_key="test",
        base_url="https://example.test/api",
        min_interval=0,
        max_retries=2,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr("app.ingest.dart_client.time.sleep", lambda s: None)  # 대기 생략
    assert client.get_json("/x.json") == [{"ok": True}]
    assert calls["n"] == 2


def test_year_windows():
    assert _year_windows("20240315", "20261119") == [
        ("20240315", "20241231"),
        ("20250101", "20251231"),
        ("20260101", "20261119"),
    ]
    assert _year_windows("20260101", "20260630") == [("20260101", "20260630")]
