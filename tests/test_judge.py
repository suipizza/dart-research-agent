"""코드 채점(숫자·사실 포함, 출처 적중) 검증. LLM 호출 없음."""

from eval.judge import citation_hit, key_fact_hits


def test_numbers_match_ignoring_commas_and_surrounding_text():
    ans = "취득예정금액은 14,999,999,992,000원(약 15조원), 53,285,968주입니다 [1]."
    assert key_fact_hits(ans, ["14,999,999,992,000", "53,285,968"]) == [True, True]


def test_number_must_match_exactly():
    # 정정 전 숫자(24,070,000)로 답하면 정정 후 정답(23,693,272)과 다르다
    assert key_fact_hits("소각 주식은 24,070,000주입니다.", ["23,693,272"]) == [False]


def test_text_fact_ignores_spaces_and_case():
    ans = "이 공시는 종속회사인 LG 에너지솔루션 관련입니다."
    assert key_fact_hits(ans, ["LG에너지솔루션", "종속회사"]) == [True, True]


def test_decimal_numbers():
    assert key_fact_hits("전년 대비 783.11% 증가", ["783.11"]) == [True]


def test_citation_hit():
    assert citation_hit(["a", "b"], ["b", "c"]) is True
    assert citation_hit(["a"], ["c"]) is False
    assert citation_hit([], []) is None


def test_dates_match_across_formats():
    assert key_fact_hits("최초 제출일은 2026년 08월 28일입니다", ["2026-08-28"]) == [True]
    assert key_fact_hits("2026.8.28 결정", ["2026년 08월 28일"]) == [True]
    assert key_fact_hits("2026-08-29 결정", ["2026-08-28"]) == [False]


def test_month_day_fact():
    assert key_fact_hits("2026년 4월 22일, 10월 26일 결정", ["04-22", "10-26"]) == [True, True]
