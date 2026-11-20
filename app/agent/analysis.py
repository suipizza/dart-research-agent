"""① 질문 분석 노드: 질문을 검색 조건으로 바꾼다.

기본 RAG의 실패 원인(0번 실험)
- 날짜를 무시함 ("2026년 8월", "최근")         → filing_from / filing_to / latest
- 공시 종류를 혼동함 (배당 vs 실적)             → categories
- 회사명 없는 질문, 줄임말             → companies (LLM이 목록에서 고름)
- 회계연도 ≠ 공시일 ("2025년 실적"은 2026년 공시) → fiscal_year / period 는 공시일과 따로 둔다
"""

from datetime import date, timedelta
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import session_scope
from app.ingest.categories import CATEGORIES
from app.llm import Usage, call_json
from app.models import Company
from app.rag.companies import ALIASES

TODAY = date(2026, 11, 19)  # 데이터 기준일 (평가 재현성을 위해 고정)
DATA_START = date(2024, 1, 1)

Period = Literal["Q1", "Q2", "Q3", "Q4", "H1", "9M", "FY"]
CategoryKey = Literal[tuple(c.key for c in CATEGORIES)]  # type: ignore[valid-type]


class Analysis(BaseModel):
    route: Literal["search", "financial", "refuse"] = Field(
        description="search: 공시 문서 검색 / financial: 매출·영업이익 등 재무 수치 / refuse: 답하면 안 되는 질문"
    )
    refuse_reason: str | None = Field(
        description="route=refuse일 때 이유 (투자 판단, 주가, 수집 범위 밖 기업·기간)"
    )
    companies: list[str] = Field(
        description="질문에 나온 회사의 정식 이름. 반드시 [회사 목록]에 있는 이름으로. 없으면 빈 목록"
    )
    out_of_scope_company: str | None = Field(
        description="질문에 회사가 나오는데 [회사 목록]에 없으면 그 이름"
    )
    categories: list[CategoryKey] = Field(  # type: ignore[valid-type]
        description="질문이 가리키는 공시 유형 키. 특정할 수 없으면 빈 목록"
    )
    filing_from: str | None = Field(
        description="공시일 범위 시작 YYYY-MM-DD. 날짜 조건이 없으면 null"
    )
    filing_to: str | None = Field(description="공시일 범위 끝 YYYY-MM-DD. 날짜 조건이 없으면 null")
    latest: bool = Field(description="'최근', '가장 최근', '이번' 처럼 최신 공시를 원하면 true")
    is_list: bool = Field(description="여러 건을 모아 달라는 질문(목록, 전부, ~한 회사들)이면 true")
    fiscal_year: int | None = Field(
        description="재무 수치 질문의 회계연도 (예: 2025년 실적 → 2025)"
    )
    period: Period | None = Field(  # type: ignore[valid-type]
        description="재무 기간: Q1~Q4 분기(3개월), H1 상반기 누적, 9M 1~9월 누적, FY 연간"
    )
    metrics: list[str] = Field(
        description="재무 계정 (예: 매출액, 영업이익, 당기순이익). 없으면 빈 목록"
    )
    search_query: str = Field(
        description="벡터 검색에 넣을 질문. 회사명·공시 종류·핵심어를 남기고 군더더기 제거"
    )


def _category_guide() -> str:
    return "\n".join(f"- {c.key}: {c.label}" for c in CATEGORIES)


@lru_cache
def company_names() -> dict[str, str]:
    """{정식 이름: corp_code}"""
    with session_scope() as s:
        return dict(s.execute(select(Company.corp_name, Company.corp_code)).all())


def _company_guide() -> str:
    lines = []
    for name in sorted(company_names()):
        aliases = ALIASES.get(name, [])
        lines.append(f"- {name}" + (f" (별칭: {', '.join(aliases)})" if aliases else ""))
    return "\n".join(lines)


def system_prompt() -> str:
    return f"""당신은 한국 상장사 공시 검색 시스템의 질문 분석기입니다. 질문을 검색 조건(JSON)으로 바꿉니다.
오늘은 {TODAY}이고, 수집된 데이터는 {DATA_START} 이후 공시뿐입니다.

[회사 목록] (이 목록의 회사만 수집됨. 줄임말·별명도 정식 이름으로 바꿀 것. 예: 포스코 → POSCO홀딩스, 엘지화학 → LG화학, SKT → SK텔레콤)
{_company_guide()}

[공시 유형]
{_category_guide()}

규칙
1. route
   - financial: 매출액·영업이익·순이익·자산 등 재무제표 수치를 묻는 질문 (잠정실적 포함)
   - refuse: 매수·매도 추천, 주가·목표주가 전망, [회사 목록]에 없는 회사, {DATA_START} 이전 기간
   - search: 그 밖의 공시 내용 (자사주, 배당, 증자, 합병·분할, 투자, 소각 등)
2. filing_from / filing_to 는 '공시일' 범위다. "2025년 3월에 결정한" → 2025-03-01 ~ 2025-03-31,
   "2024년에" → 2024-01-01 ~ 2024-12-31, "5월 12일에 발표한" → 그날 하루. 날짜 언급이 없으면 null.
   단, 재무 수치의 회계 기간("2024년 연간 실적", "1분기 매출액")은 공시일이 아니다. fiscal_year/period에 넣고
   filing 범위는 null로 둔다. (실적은 기간이 끝난 뒤 1~3개월 후에 공시된다)
3. period: "2분기 순이익" → Q2, "상반기" → H1, "1~9월 누적" → 9M, "연간"·"2024년 매출" → FY.
   연도가 없으면 오늘 기준 가장 최근 해당 기간의 연도를 쓴다.
4. companies: 회사가 없는 질문(예: "3월에 배당 결정한 회사")이면 빈 목록. 비교 질문이면 여러 개.
5. categories: 자사주 매입=treasury_acquire, 자사주 매각=treasury_dispose, 주식 소각=stock_cancel,
   현금배당·분기배당·결산배당=dividend, 잠정실적=earnings_prelim, 시설투자=facility_investment,
   타법인 지분 취득·출자=equity_acquire 또는 equity_transfer. 애매하면 여러 개, 모르면 빈 목록."""


def analyze(question: str, model: str, usage: Usage | None = None) -> Analysis:
    return call_json(
        model=model,
        system=system_prompt(),
        user=f"[질문]\n{question}",
        schema=Analysis,
        effort="low",
        max_tokens=2000,
        usage=usage,
    )


def to_corp_codes(names: list[str]) -> list[str]:
    """LLM이 고른 이름을 corp_code로. 정식 이름이 아니면 별칭으로도 찾는다."""
    by_name = company_names()
    alias_to_name = {a: n for n, aliases in ALIASES.items() for a in aliases}
    codes = []
    for n in names:
        name = n if n in by_name else alias_to_name.get(n)
        if name in by_name and by_name[name] not in codes:
            codes.append(by_name[name])
    return codes


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


# 회계 기간 → (재무 보고서 코드, 누적 여부)와 잠정실적 공시가 나오는 시기
_PERIOD_END = {"Q1": (3, 31), "Q2": (6, 30), "H1": (6, 30), "Q3": (9, 30), "9M": (9, 30)}


def period_end(year: int, period: str) -> date:
    if period in ("FY", "Q4"):
        return date(year, 12, 31)
    m, d = _PERIOD_END[period]
    return date(year, m, d)


def earnings_filing_window(year: int, period: str) -> tuple[date, date]:
    """잠정실적 공시가 나올 법한 공시일 범위: 기간 종료 직후 ~ 약 3개월 뒤."""
    end = period_end(year, period)
    return end, end + timedelta(days=95)
