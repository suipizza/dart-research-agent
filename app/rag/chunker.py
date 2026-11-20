"""공시 텍스트 → 검색용 청크.

규칙
1. `## 제목` 단위로 섹션을 나눈다.
2. 섹션이 max_chars보다 길면 '줄' 단위로 이어 붙이다가 넘치기 직전에 자른다.
   표는 한 행이 한 줄이므로 행이 중간에서 잘리지 않는다.
3. 각 청크 앞에 머리말(회사 | 날짜 | 공시명 | 섹션)을 붙인다(옵션).
   표 조각만 떼어 놓으면 어느 회사·어떤 공시의 숫자인지 알 수 없기 때문이다.
   머리말 유무는 6단계 실험 변수라서 끌 수 있게 했다.
"""

import re
from dataclasses import dataclass

DEFAULT_MAX_CHARS = 1000
MIN_CHARS = 100  # 이보다 짧은 조각은 다음 조각에 합친다 (예: 회사명 한 줄)

# 표지(주소·전화번호·대표이사)는 회사명 검색에 과하게 걸려 실제 내용을 밀어내므로 제외
SKIP_SECTIONS = ("거래소 신고의무 사항",)


@dataclass(frozen=True)
class ChunkMeta:
    corp_name: str
    rcept_dt: str  # YYYY-MM-DD
    report_nm: str


@dataclass(frozen=True)
class Chunk:
    index: int
    section: str
    body: str  # 머리말 없는 본문
    text: str  # 임베딩·검색에 쓰는 최종 텍스트 (머리말 포함 여부는 설정에 따름)


def split_sections(text: str) -> list[tuple[str, str]]:
    """'## 제목'을 기준으로 (섹션 제목, 내용) 목록을 만든다. 제목 이전 내용은 섹션명 ''."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for block in text.split("\n\n"):
        if block.startswith("## "):
            sections.append((block[3:].strip(), []))
        else:
            sections[-1][1].append(block)
    return [(title, "\n\n".join(blocks).strip()) for title, blocks in sections if blocks]


def split_long_line(line: str, max_chars: int) -> list[str]:
    """max_chars보다 긴 한 줄(긴 문단)을 문장 경계('. ', '다. ')에서 자른다."""
    if len(line) <= max_chars:
        return [line]
    out: list[str] = []
    rest = line
    while len(rest) > max_chars:
        cut = max(rest.rfind(". ", 0, max_chars), rest.rfind("다 ", 0, max_chars))
        cut = cut + 1 if cut > max_chars // 2 else max_chars  # 경계가 없으면 글자 수로
        out.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return out


def pack_lines(body: str, max_chars: int) -> list[str]:
    """줄 단위로 max_chars를 넘지 않게 묶는다. 표 행은 한 줄이라 중간에서 잘리지 않는다."""
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    lines = [part for line in body.split("\n") for part in split_long_line(line, max_chars)]
    for line in lines:
        add = len(line) + 1
        if current and size + add > max_chars:
            pieces.append("\n".join(current).strip())
            current, size = [], 0
        current.append(line)
        size += add
    if current:
        pieces.append("\n".join(current).strip())
    return [p for p in pieces if p]


_NUMERIC_CELL = re.compile(r"[-+()0-9.,%\s]*\d[-+()0-9.,%\s]*")


def table_header_lines(body: str, max_lines: int = 3) -> list[str]:
    """섹션 본문에서 표의 열 이름 행(숫자가 아닌 칸이 대부분인 ' | ' 줄)을 찾는다.

    표가 여러 조각으로 잘리면 뒤 조각에는 '구분 | 당기실적 | 전기실적' 같은 열 이름이 없어
    숫자만 남는다(예: 39,534,392가 당기인지 전기인지 알 수 없음). 실험 C에서 뒤 조각 앞에 반복한다.
    """
    out: list[str] = []
    for line in body.split("\n"):
        if " | " not in line:
            if out:
                break
            continue
        cells = [c.strip() for c in line.split(" | ") if c.strip()]
        numeric = sum(bool(_NUMERIC_CELL.fullmatch(c)) for c in cells)
        if numeric * 2 >= len(cells):  # 숫자 행이 나오면 머리는 끝
            break
        out.append(line)
        if len(out) >= max_lines:
            break
    return out


def header(meta: ChunkMeta, section: str) -> str:
    parts = [meta.corp_name, meta.rcept_dt, meta.report_nm]
    if section and section not in meta.report_nm:
        parts.append(section)
    return "[" + " | ".join(parts) + "]"


def chunk_document(
    text: str,
    meta: ChunkMeta,
    max_chars: int = DEFAULT_MAX_CHARS,
    with_header: bool = True,
    repeat_table_header: bool = False,
) -> list[Chunk]:
    pieces: list[tuple[str, str]] = []
    for section, body in split_sections(text):
        if any(skip in section for skip in SKIP_SECTIONS):
            continue
        packed = pack_lines(body, max_chars)
        if repeat_table_header and len(packed) > 1:
            head = table_header_lines(body)
            if head:
                prefix = "\n".join(head)
                packed = [packed[0]] + [
                    p if p.startswith(head[0]) else f"{prefix}\n{p}" for p in packed[1:]
                ]
        pieces.extend((section, p) for p in packed)

    # 너무 짧은 조각은 다음 조각 앞에 붙인다 (마지막 조각이면 앞 조각 뒤에 붙인다)
    merged: list[tuple[str, str]] = []
    carry = ""
    for section, piece in pieces:
        piece = f"{carry}\n{piece}".strip() if carry else piece
        carry = ""
        if len(piece) < MIN_CHARS:
            carry = piece
            continue
        merged.append((section, piece))
    if carry:
        if merged:
            section, last = merged[-1]
            merged[-1] = (section, f"{last}\n{carry}")
        else:
            merged.append(("", carry))

    chunks: list[Chunk] = []
    for section, piece in merged:
        final = f"{header(meta, section)}\n{piece}" if with_header else piece
        chunks.append(Chunk(index=len(chunks), section=section, body=piece, text=final))
    return chunks
