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


SK_GROUP = {
    "SK": "00181712",
    "SK하이닉스": "00164779",
    "SK스퀘어": "01596425",
    "SK이노베이션": "00631518",
    "SK텔레콤": "00159023",
    "LG": "00120021",
    "LG전자": "00401731",
    "케이티앤지": "00244455",
}
SK_LOOKUP = build_lookup(SK_GROUP)


def test_sk_family_is_not_confused():
    assert find_companies("SK스퀘어 자사주", SK_LOOKUP) == ["01596425"]
    assert find_companies("SK이노 유상증자", SK_LOOKUP) == ["00631518"]
    assert find_companies("SKT 배당", SK_LOOKUP) == ["00159023"]
    assert find_companies("SK 지주사 배당", SK_LOOKUP) == ["00181712"]
    assert find_companies("하이닉스 실적", SK_LOOKUP) == ["00164779"]


def test_lg_electronics_is_not_lg_holdings():
    assert find_companies("LG전자 3분기 영업이익", SK_LOOKUP) == ["00401731"]


def test_alias_with_symbol():
    assert find_companies("KT&G 배당", SK_LOOKUP) == ["00244455"]
