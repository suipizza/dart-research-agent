from pathlib import Path

from app.ingest.parser import parse_zip
from app.rag.chunker import ChunkMeta, chunk_document, split_long_line

FIX = Path(__file__).parent / "fixtures"
META = ChunkMeta("삼성전자", "2026-08-21", "주요사항보고서(자기주식취득결정)")


def _treasury_text() -> str:
    return parse_zip((FIX / "treasury_acquire_20260821000616.zip").read_bytes()).text


def test_header_is_prepended():
    chunks = chunk_document(_treasury_text(), META)
    assert chunks
    for c in chunks:
        assert c.text.startswith("[삼성전자 | 2026-08-21 | 주요사항보고서(자기주식취득결정)")
        assert c.text.endswith(c.body)


def test_no_header_option_for_experiments():
    chunks = chunk_document(_treasury_text(), META, with_header=False)
    assert all(c.text == c.body for c in chunks)


def test_cover_page_is_skipped():
    text = _treasury_text()
    assert "본 점 소 재 지" in text  # 원문에는 있지만
    joined = "\n".join(c.body for c in chunk_document(text, META))
    assert "본 점 소 재 지" not in joined  # 청크에는 없다


def test_table_rows_are_never_split():
    text = _treasury_text()
    rows = [line for line in text.split("\n") if " | " in line and len(line) < 300]
    for c in chunk_document(text, META, max_chars=200):
        for line in c.body.split("\n"):
            if " | " in line:
                assert line in rows  # 원문에 있던 행 그대로 (잘린 조각이 아님)


def test_key_number_lands_in_a_chunk_with_its_label():
    chunks = chunk_document(_treasury_text(), META, max_chars=300)
    assert any("2. 취득예정금액(원) | 보통주식 | 14,999,999,992,000" in c.body for c in chunks)


def test_small_pieces_are_merged():
    text = "## A\n\n짧음\n\n## B\n\n" + ("가" * 150)
    chunks = chunk_document(text, META)
    assert len(chunks) == 1
    assert chunks[0].body.startswith("짧음")


def test_long_paragraph_is_split_at_sentence_boundary():
    line = "이것은 문장입니다. " * 100  # 약 1,100자 한 줄
    parts = split_long_line(line.strip(), 300)
    assert len(parts) > 1
    assert all(len(p) <= 300 for p in parts)
    assert all(p.endswith(".") for p in parts[:-1])


EARNINGS = """1. 연결실적내용 | 단위 : 억원, %
구분 | 당기실적 | 전기실적 | 전기대비
구분 | ('26.3Q) | ('26.2Q) | 증감율(%)
매출액 | 당해실적 | 1,952,532 | 1,714,995 | 13.85
""" + "\n".join(f"계정{i} | 당해실적 | {i},000 | {i},100 | 1.0" for i in range(60))


def test_table_header_lines_stop_at_first_numeric_row():
    from app.rag.chunker import table_header_lines

    head = table_header_lines(EARNINGS)
    assert head[0].startswith("1. 연결실적내용")
    assert all("1,952,532" not in h for h in head)


def test_repeat_table_header_on_later_pieces():
    chunks = chunk_document(EARNINGS, META, max_chars=300, repeat_table_header=True)
    assert len(chunks) > 1
    assert all("구분 | 당기실적" in c.body for c in chunks)  # 뒤 조각에도 열 이름
    plain = chunk_document(EARNINGS, META, max_chars=300)
    assert not all("구분 | 당기실적" in c.body for c in plain)
