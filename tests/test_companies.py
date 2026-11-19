from app.rag.companies import build_lookup, find_companies

COMPANIES = {
    "삼성전자": "00126380",
    "삼성SDI": "00126362",
    "LG": "00120021",
    "LG화학": "00356361",
    "LG에너지솔루션": "01515323",
    "현대자동차": "00164742",
    "NAVER": "00266961",
}
LOOKUP = build_lookup(COMPANIES)


def test_exact_name():
    assert find_companies("삼성전자 최근 자사주 취득", LOOKUP) == ["00126380"]


def test_alias():
    assert find_companies("현대차 배당 알려줘", LOOKUP) == ["00164742"]
    assert find_companies("네이버 실적", LOOKUP) == ["00266961"]
    assert find_companies("naver 실적", LOOKUP) == ["00266961"]  # 대소문자 무시


def test_longest_match_wins():
    # 'LG화학' 안의 'LG'가 지주사 LG로 따로 잡히면 안 된다
    assert find_companies("LG화학 유상증자", LOOKUP) == ["00356361"]
    assert find_companies("LG엔솔 실적", LOOKUP) == ["01515323"]


def test_multiple_companies_for_comparison():
    found = find_companies("삼성전자와 삼성SDI 비교", LOOKUP)
    assert set(found) == {"00126380", "00126362"}


def test_no_company():
    assert find_companies("최근 자사주 소각한 회사", LOOKUP) == []
