"""질문에서 회사명을 찾아 corp_code 필터로 바꾼다.

벡터 검색은 '삼성전자'와 '삼성SDI'를 비슷하게 보기 때문에, 질문에 회사가 나오면
의미 검색이 아니라 WHERE 조건으로 고정하는 편이 정확하다.
긴 이름부터 매칭하고 매칭된 부분은 지워서 'LG화학' 안의 'LG'가 따로 잡히지 않게 한다.
"""

# 정식명(companies.csv의 corp_name) → 사람들이 실제로 부르는 이름들
ALIASES: dict[str, list[str]] = {
    "현대자동차": ["현대차"],
    "삼성바이오로직스": ["삼성바이오", "삼바"],
    "한국전력공사": ["한국전력", "한전"],
    "POSCO홀딩스": ["포스코홀딩스", "포스코"],
    "NAVER": ["네이버"],
    "LG에너지솔루션": ["LG엔솔", "엘지에너지솔루션"],
    "삼성화재해상보험": ["삼성화재"],
    "SK하이닉스": ["하이닉스"],
    "하나금융지주": ["하나금융"],
    "우리금융지주": ["우리금융"],
    "메리츠금융지주": ["메리츠금융", "메리츠"],
    "KB금융": ["KB금융지주"],
    "신한지주": ["신한금융지주", "신한금융"],
    "한화에어로스페이스": ["한화에어로"],
    "SK텔레콤": ["SKT"],
}


def build_lookup(companies: dict[str, str]) -> list[tuple[str, str]]:
    """{corp_name: corp_code} → [(부르는 이름, corp_code)] 긴 이름 순."""
    pairs = [(name, code) for name, code in companies.items()]
    for name, aliases in ALIASES.items():
        if name in companies:
            pairs += [(a, companies[name]) for a in aliases]
    return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def find_companies(query: str, lookup: list[tuple[str, str]]) -> list[str]:
    """질문에 나온 회사들의 corp_code (등장 순서 무관, 중복 없음)."""
    text = query.upper()
    found: list[str] = []
    for name, code in lookup:
        key = name.upper()
        if key in text:
            text = text.replace(key, " ")
            if code not in found:
                found.append(code)
    return found
