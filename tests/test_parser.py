"""실제 DART 원문(저장해 둔 ZIP)으로 파서를 검증한다. 네트워크를 쓰지 않는다."""

from pathlib import Path

from lxml import html

from app.ingest.parser import parse_zip, table_to_lines

FIX = Path(__file__).parent / "fixtures"


def test_dart_xml_treasury_acquire():
    doc = parse_zip((FIX / "treasury_acquire_20260821000616.zip").read_bytes())
    assert doc.title == "주요사항보고서(자기주식 취득 결정)"
    # 핵심 수치가 '항목 | 구분 | 값' 한 줄로 남아야 검색·검증에 쓸 수 있다
    assert "2. 취득예정금액(원) | 보통주식 | 14,999,999,992,000" in doc.text
    assert "3. 취득예상기간 | 시작일 | 2026년 08월 24일" in doc.text
    assert "## 자기주식 취득 결정" in doc.text
    assert "\n6.3\n" not in doc.text  # 서식 버전 번호는 제거


def test_html_earnings_prelim_keeps_rowspan_label():
    doc = parse_zip((FIX / "earnings_prelim_20261029800087.zip").read_bytes())
    assert "영업(잠정)실적" in doc.title
    assert "단위 : 억원" in doc.text  # 단위는 숫자 검증에 꼭 필요
    # '매출액'은 rowspan=2라서 아래 '누계실적' 행에도 붙어 있어야 한다
    assert "매출액 | 당해실적 | 1,952,532" in doc.text
    assert "매출액 | 누계실적 | 5,006,261" in doc.text


def test_table_rowspan_and_dash_rows():
    table = html.fromstring(
        "<table>"
        "<tr><td rowspan='2'>매출액</td><td>당해</td><td>100</td></tr>"
        "<tr><td>누계</td><td>300</td></tr>"
        "<tr><td>-</td><td>-</td></tr>"
        "</table>"
    )
    assert table_to_lines(table) == ["매출액 | 당해 | 100", "매출액 | 누계 | 300"]
