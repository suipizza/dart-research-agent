"""숫자 검증 노드: 근거에 있는 숫자는 통과, 없는 숫자는 잡아야 한다."""

from app.agent.verify import verify_numbers

EVIDENCE = """[1] 삼성전자 | 2026-08-21 | 주요사항보고서(자기주식취득결정) | 접수번호 20260821000616
2. 취득예정금액(원) | 보통주식 | 14,999,999,992,000
1. 취득예정주식(주) | 보통주식 | 53,285,968
[2] 삼성전자 | 2026-10-29 | 연결재무제표기준영업(잠정)실적(공정공시) | 접수번호 20261029800087
1. 연결실적내용 | 단위 : 억원, %
영업이익 | 당해실적 | 1,074,405 | 894,924 | 20.06
[3] SK하이닉스 | 2026년 3분기 | 재무제표(연결)
- 영업이익: 83,333,818,000,000원(약 83조 3,338억원)"""


def test_exact_numbers_pass():
    r = verify_numbers("취득예정금액은 14,999,999,992,000원, 53,285,968주입니다 [1].", EVIDENCE)
    assert r.ok and r.checked == 2


def test_rounded_korean_amount_passes():
    # 약 15조원 ≈ 14,999,999,992,000원 / 107조 4,405억원 = 1,074,405억원(표 단위가 억원)
    r = verify_numbers("약 15조원을 취득합니다. 영업이익은 107조 4,405억원입니다.", EVIDENCE)
    assert r.ok, r.unverified


def test_made_up_number_is_caught():
    r = verify_numbers("취득예정금액은 13,500,000,000,000원입니다.", EVIDENCE)
    assert r.unverified == ["13,500,000,000,000"]


def test_wrong_korean_amount_is_caught():
    r = verify_numbers("영업이익은 약 95조원입니다.", EVIDENCE)
    assert not r.ok


def test_percent_dates_and_small_numbers_are_ignored():
    r = verify_numbers(
        "2026년 10월 29일 공시, 전분기 대비 20.06% 증가, 1주당 4,601원, 증감률 +632.1%.", EVIDENCE
    )
    assert r.ok and r.checked == 0


def test_matches_point_to_the_evidence_line_and_filing():
    r = verify_numbers("취득예정금액은 14,999,999,992,000원, 영업이익은 107조 4,405억원.", EVIDENCE)
    by_value = {m["value"]: m for m in r.matches}
    m1 = by_value["14,999,999,992,000"]
    assert "취득예정금액" in m1["line"] and m1["title"].startswith("삼성전자")
    m2 = by_value["107조 4,405억원"]
    assert "1,074,405" in m2["line"]  # 억원 단위 표의 행
