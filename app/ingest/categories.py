"""공시 제목(report_nm)으로 수집 대상 유형을 분류한다.

DART 공시 제목은 띄어쓰기·가운뎃점 표기가 섞여 있어(예: '현금ㆍ현물배당결정')
공백과 가운뎃점을 지운 뒤 키워드로 매칭한다. 순서가 중요하다: 더 구체적인 규칙이 먼저.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    keyword: str
    label: str
    structured_api: str | None = None  # 핵심 필드를 주는 DS005 API (없으면 원문만)


CATEGORIES: tuple[Category, ...] = (
    Category("treasury_acquire", "자기주식취득결정", "자기주식 취득 결정", "tsstkAqDecsn"),
    Category("treasury_dispose", "자기주식처분결정", "자기주식 처분 결정", "tsstkDpDecsn"),
    Category("rights_bonus_issue", "유무상증자결정", "유무상증자 결정", "pifricDecsn"),
    Category("rights_issue", "유상증자결정", "유상증자 결정", "piicDecsn"),
    Category("bonus_issue", "무상증자결정", "무상증자 결정", "fricDecsn"),
    Category("split_merger", "회사분할합병결정", "회사분할합병 결정", "cmpDvmgDecsn"),
    Category("merger", "회사합병결정", "회사합병 결정", "cmpMgDecsn"),
    Category("split", "회사분할결정", "회사분할 결정", "cmpDvDecsn"),
    Category(
        "equity_transfer",
        "타법인주식및출자증권양수결정",
        "타법인 주식 양수 결정",
        "otcprStkInvscrTrfDecsn",
    ),
    Category("equity_acquire", "타법인주식및출자증권취득결정", "타법인 주식 취득 결정"),
    Category("facility_investment", "신규시설투자", "신규 시설 투자"),
    Category("earnings_prelim", "영업(잠정)실적", "영업(잠정)실적"),
    Category("dividend", "현금현물배당결정", "현금·현물 배당 결정"),
    Category("stock_cancel", "주식소각결정", "주식 소각 결정"),
)

BY_KEY = {c.key: c for c in CATEGORIES}

_CORRECTION = re.compile(r"^\[(기재정정|첨부정정|첨부추가|변경등록|연장결정|발행조건확정)\]")
_STRIP = re.compile(r"[\sㆍ·]")


def normalize(report_nm: str) -> str:
    return _STRIP.sub("", report_nm)


def classify(report_nm: str) -> Category | None:
    name = normalize(report_nm)
    for cat in CATEGORIES:
        if cat.keyword in name:
            return cat
    return None


def is_correction(report_nm: str) -> bool:
    return bool(_CORRECTION.match(report_nm.strip()))
