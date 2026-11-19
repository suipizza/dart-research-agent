"""공시 원문(document.xml ZIP) → 검색용 텍스트.

DART 원문은 두 가지 형태로 온다.
- 주요사항보고서 등: DART 전용 XML (dart4.xsd) — TITLE, P, TABLE/TR/TD/TE 태그
- 거래소 공시(잠정실적 등): HTML

둘 다 lxml의 HTML 파서로 읽으면 같은 방식으로 다룰 수 있다(태그가 소문자로 정규화됨).
표는 행마다 'A | B | C' 한 줄로 펼친다. rowspan으로 합쳐진 셀(예: '매출액')은 아래 행에도
반복해 넣어서, 표가 청크로 잘려도 각 줄이 무엇에 대한 숫자인지 남도록 한다.
"""

import io
import re
import zipfile
from dataclasses import dataclass

from lxml import html

_WS = re.compile(r"[\s 　]+")
_CELL_TAGS = {"td", "th", "te", "tu"}
_SKIP_TAGS = {
    "style", "script", "head", "meta", "colgroup", "col",
    "formula-version", "document-name",  # 서식 버전 번호, 제목(따로 추출)
}  # fmt: skip
_BLOCK_TAGS = {"p", "div", "span", "br", "li"}


@dataclass
class ParsedDocument:
    title: str
    text: str


def clean(s: str) -> str:
    return _WS.sub(" ", s).strip()


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _cell_text(cell) -> str:
    return clean(" ".join(cell.itertext()))


def table_to_lines(table) -> list[str]:
    """rowspan을 펼친 격자를 만든 뒤, 행마다 비어 있지 않은 셀을 ' | '로 잇는다."""
    pending: dict[int, tuple[str, int]] = {}  # 열 위치 → (텍스트, 남은 행 수)
    lines: list[str] = []
    for tr in table.iter("tr"):
        row: list[str] = []
        col = 0
        cells = [c for c in tr if isinstance(c.tag, str) and c.tag.lower() in _CELL_TAGS]
        it = iter(cells)
        while True:
            if col in pending:  # 위 행에서 내려온 rowspan 셀
                text, left = pending[col]
                row.append(text)
                if left > 1:
                    pending[col] = (text, left - 1)
                else:
                    del pending[col]
                col += 1
                continue
            cell = next(it, None)
            if cell is None:
                break
            text = _cell_text(cell)
            rowspan = int(cell.get("rowspan", "1") or 1)
            colspan = int(cell.get("colspan", "1") or 1)
            row.append(text)
            if rowspan > 1:
                pending[col] = (text, rowspan - 1)
            col += colspan
        values = [v for v in row if v]
        if values and any(v != "-" for v in values):
            lines.append(" | ".join(values))
    return lines


def _walk(el, out: list[str]) -> None:
    tag = el.tag.lower() if isinstance(el.tag, str) else ""
    if tag in _SKIP_TAGS:
        return
    if tag == "table":
        rows = table_to_lines(el)
        if rows:
            out.append("\n".join(rows))
        return
    if tag in {"title", "section-title"} or tag in {"h1", "h2", "h3"}:
        text = _cell_text(el)
        if text:
            out.append(f"## {text}")
        return
    if tag in _BLOCK_TAGS and not any(
        isinstance(c.tag, str) and c.tag.lower() in {"table", "p", "div"} for c in el
    ):
        text = _cell_text(el)
        if text:
            out.append(text)
        return
    if el.text and el.text.strip() and tag not in {"html", "body", "document"}:
        out.append(clean(el.text))
    for child in el:
        _walk(child, out)


def parse_document(raw: bytes) -> ParsedDocument:
    """원문 파일 하나(XML 또는 HTML 바이트)를 텍스트로 바꾼다."""
    root = html.fromstring(decode(raw).encode("utf-8"), parser=html.HTMLParser(encoding="utf-8"))
    title_el = root.find(".//document-name")
    title = _cell_text(title_el) if title_el is not None else ""
    body = root.find(".//body")
    out: list[str] = []
    _walk(body if body is not None else root, out)
    if not title:
        title = next((b[3:] for b in out if b.startswith("## ")), out[0] if out else "")
    # 연속 중복 블록 제거 (HTML 공시에서 같은 문구가 반복되는 경우)
    blocks: list[str] = []
    for b in out:
        if not blocks or blocks[-1] != b:
            blocks.append(b)
    return ParsedDocument(title=clean(title)[:300], text="\n\n".join(blocks))


def parse_zip(zip_bytes: bytes) -> ParsedDocument:
    """document.xml ZIP 안의 파일들을 합쳐 하나의 문서로 만든다 (첨부가 있으면 여러 개)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = sorted(n for n in zf.namelist() if n.lower().endswith((".xml", ".htm", ".html")))
        parts = [parse_document(zf.read(n)) for n in names]
    if not parts:
        return ParsedDocument(title="", text="")
    return ParsedDocument(title=parts[0].title, text="\n\n".join(p.text for p in parts if p.text))
