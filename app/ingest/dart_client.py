"""DART Open API 클라이언트.

- 응답의 status 코드를 해석해 '데이터 없음(013)'은 빈 결과로, 나머지 오류는 예외로 바꾼다.
- 요청 간격을 두어 호출 제한에 걸리지 않게 하고, 일시 오류는 재시도한다.
"""

import time
from typing import Any

import httpx

from app.config import get_settings

NO_DATA = "013"
RATE_LIMITED = "020"


class DartError(RuntimeError):
    def __init__(self, status: str, message: str, endpoint: str):
        super().__init__(f"[{status}] {message} ({endpoint})")
        self.status = status
        self.message = message
        self.endpoint = endpoint


class DartClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        min_interval: float = 0.3,
        max_retries: int = 4,
        transport: httpx.BaseTransport | None = None,
    ):
        settings = None if (api_key and base_url) else get_settings()
        self._key = api_key or settings.dart_api_key.get_secret_value()
        self._http = httpx.Client(
            base_url=base_url or settings.dart_base_url,
            timeout=30.0,
            transport=transport,
        )
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._last_call = 0.0

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── 내부 공통 ────────────────────────────────────────────
    def _throttle(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _get(self, endpoint: str, params: dict[str, Any]) -> httpx.Response:
        for attempt in range(1, self._max_retries + 1):
            self._throttle()
            try:
                resp = self._http.get(endpoint, params={"crtfc_key": self._key, **params})
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == self._max_retries:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def _payload(self, endpoint: str, params: dict[str, Any]) -> dict:
        """JSON 응답을 dict로. 정상(000)·데이터 없음(013)만 돌려주고 나머지는 재시도 또는 예외.

        DART는 짧은 시간에 요청이 몰리면 HTTP 200에 빈 본문을 보내는 경우가 있어,
        JSON 파싱 실패도 일시 오류로 보고 재시도한다.
        """
        for attempt in range(1, self._max_retries + 1):
            last = attempt == self._max_retries
            try:
                data = self._get(endpoint, params).json()
            except ValueError:
                if last:
                    raise DartError("EMPTY", "빈 응답 또는 JSON 아님", endpoint) from None
                time.sleep(2**attempt)
                continue
            status = data.get("status")
            if status in ("000", NO_DATA):
                return data
            if status == RATE_LIMITED and not last:
                time.sleep(60)
                continue
            raise DartError(status, data.get("message", ""), endpoint)
        raise AssertionError("unreachable")

    def get_json(self, endpoint: str, **params: Any) -> list[dict]:
        """JSON API를 호출해 list를 돌려준다. 데이터가 없으면 빈 리스트."""
        return self._payload(endpoint, params).get("list", [])

    def get_binary(self, endpoint: str, **params: Any) -> bytes:
        """ZIP을 주는 API(corpCode.xml, document.xml). 오류면 ZIP 대신 XML 오류가 온다."""
        resp = self._get(endpoint, params)
        content = resp.content
        if not content.startswith(b"PK"):
            text = content.decode("utf-8", errors="replace")
            status = _between(text, "<status>", "</status>") or "?"
            message = _between(text, "<message>", "</message>") or text[:200]
            raise DartError(status, message, endpoint)
        return content

    # ── 엔드포인트 ───────────────────────────────────────────
    def list_filings(self, corp_code: str, bgn_de: str, end_de: str) -> list[dict]:
        """기간 내 모든 공시 목록.

        기간을 연도 단위로 나눠 조회하고, 각 구간은 페이지를 끝까지 넘긴다.
        (한 번에 몇 년치를 받는 것보다 요청이 작아져 실패 시 재시도 범위가 줄어든다.)
        """
        out: list[dict] = []
        for start, end in _year_windows(bgn_de, end_de):
            page = 1
            while True:
                data = self._payload(
                    "/list.json",
                    {
                        "corp_code": corp_code,
                        "bgn_de": start,
                        "end_de": end,
                        "page_no": page,
                        "page_count": 100,
                    },
                )
                if data["status"] == NO_DATA:
                    break
                out.extend(data["list"])
                if page >= int(data.get("total_page", 1)):
                    break
                page += 1
        return out

    def document_zip(self, rcept_no: str) -> bytes:
        return self.get_binary("/document.xml", rcept_no=rcept_no)

    def structured(self, api: str, corp_code: str, bgn_de: str, end_de: str) -> list[dict]:
        return self.get_json(f"/{api}.json", corp_code=corp_code, bgn_de=bgn_de, end_de=end_de)

    def financial_accounts(self, corp_code: str, year: int, reprt_code: str) -> list[dict]:
        return self.get_json(
            "/fnlttSinglAcnt.json", corp_code=corp_code, bsns_year=year, reprt_code=reprt_code
        )


def _year_windows(bgn_de: str, end_de: str) -> list[tuple[str, str]]:
    """'20240315'~'20261119' → [(20240315, 20241231), (20250101, 20251231), (20260101, 20261119)]"""
    windows = []
    year = int(bgn_de[:4])
    while True:
        start = bgn_de if year == int(bgn_de[:4]) else f"{year}0101"
        end = f"{year}1231"
        if end >= end_de:
            windows.append((start, end_de))
            return windows
        windows.append((start, end))
        year += 1


def _between(text: str, start: str, end: str) -> str | None:
    i = text.find(start)
    j = text.find(end, i + len(start))
    if i == -1 or j == -1:
        return None
    return text[i + len(start) : j].strip()
