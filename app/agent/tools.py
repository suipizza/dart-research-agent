"""② 도구: 필터 검색(+조건 완화)과 재무 데이터 조회.

재무 데이터는 1단계에서 이미 DB(financials)에 받아 두었으므로 질문 시점에 DART API를 부르지 않는다.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app.agent.analysis import Analysis, earnings_filing_window, parse_date, to_corp_codes
from app.db import session_scope
from app.models import Company, Financial
from app.rag.search import Hit, search

# ── 공통: 근거(evidence) ─────────────────────────────────────────


@dataclass
class Evidence:
    """답변 생성에 넘기는 근거 한 덩어리. 공시 청크이거나 재무 데이터 요약이다."""

    kind: str  # "filing" | "financial"
    title: str
    rcept_no: str
    text: str


def hits_to_evidence(hits: list[Hit]) -> list[Evidence]:
    return [
        Evidence(
            kind="filing",
            title=f"{h.corp_name} | {h.rcept_dt} | {h.report_nm} | 접수번호 {h.rcept_no}",
            rcept_no=h.rcept_no,
            text=h.text.split("\n", 1)[-1],
        )
        for h in hits
    ]


def format_evidence(items: list[Evidence]) -> str:
    return "\n\n".join(f"[{i}] {e.title}\n{e.text}" for i, e in enumerate(items, 1))


# ── 금액 표기 ────────────────────────────────────────────────────


def format_krw(n: int | None) -> str:
    """83333818000000 → '83,333,818,000,000원(약 83조 3,338억원)'"""
    if n is None:
        return "-"
    sign = "-" if n < 0 else ""
    a = abs(n)
    jo, eok = divmod(round(a / 1e8), 10_000)
    if jo and eok:
        approx = f"{jo}조 {eok:,}억원"
    elif jo:
        approx = f"{jo}조원"
    elif eok:
        approx = f"{eok:,}억원"
    else:
        return f"{sign}{a:,}원"
    return f"{sign}{a:,}원(약 {sign}{approx})"


# ── 필터 검색 + 조건 완화 ────────────────────────────────────────

RELAX_STEPS = ("full", "no_category", "no_date", "company_only")


@dataclass
class SearchPlan:
    query: str
    corp_codes: list[str] | None
    since: date | None
    until: date | None
    categories: list[str] | None
    top_k: int
    latest: bool


def plan_search(a: Analysis, question: str) -> SearchPlan:
    since, until = parse_date(a.filing_from), parse_date(a.filing_to)
    categories = list(a.categories) or None
    if a.route == "financial":
        categories = ["earnings_prelim"]
        if a.fiscal_year and a.period and not (since or until):
            since, until = earnings_filing_window(a.fiscal_year, a.period)
    return SearchPlan(
        query=a.search_query or question,
        corp_codes=to_corp_codes(a.companies) or None,
        since=since,
        until=until,
        categories=categories,
        top_k=10 if a.is_list else 5,
        latest=a.latest,
    )


def relaxed(plan: SearchPlan, step: str) -> SearchPlan:
    p = SearchPlan(**plan.__dict__)
    if step in ("no_category", "company_only"):
        p.categories = None
    if step in ("no_date", "company_only"):
        p.since = p.until = None
    return p


def run_search(plan: SearchPlan) -> list[Hit]:
    pool = plan.top_k * 4 if plan.latest else plan.top_k
    hits, _ = search(
        plan.query,
        top_k=pool,
        corp_codes=plan.corp_codes,
        since=plan.since,
        until=plan.until,
        categories=plan.categories,
        detect_company=False,  # 회사는 질문 분석 노드가 이미 정했다
    )
    if plan.latest:
        # 의미가 비슷한 후보 중에서 최신 공시부터. 같은 공시의 청크는 함께 유지한다.
        hits = sorted(hits, key=lambda h: (h.rcept_dt, -h.distance), reverse=True)[: plan.top_k]
    return hits


def search_with_relaxation(plan: SearchPlan, start: int = 0) -> tuple[list[Hit], int]:
    """결과가 빌 때만 조건을 하나씩 푼다. (결과, 사용한 완화 단계 번호)"""
    for i in range(start, len(RELAX_STEPS)):
        hits = run_search(relaxed(plan, RELAX_STEPS[i]))
        if hits:
            return hits, i
    return [], len(RELAX_STEPS) - 1


# ── 재무 데이터 ──────────────────────────────────────────────────

# 기간 → (보고서 코드, 사용할 값). 반기·3분기 보고서는 '당기 3개월'과 '누적'을 따로 준다.
#   thstrm_amount     : 해당 분기 3개월 (1분기 보고서는 3개월=누적)
#   thstrm_add_amount : 연초부터 누적
PERIOD_SOURCE = {
    "Q1": ("11013", "thstrm_amount"),
    "Q2": ("11012", "thstrm_amount"),
    "H1": ("11012", "thstrm_add_amount"),
    "Q3": ("11014", "thstrm_amount"),
    "9M": ("11014", "thstrm_add_amount"),
    "FY": ("11011", "thstrm_amount"),
}
PERIOD_LABEL = {
    "Q1": "1분기(1~3월)",
    "Q2": "2분기(4~6월)",
    "H1": "상반기(1~6월 누적)",
    "Q3": "3분기(7~9월)",
    "9M": "1~9월 누적",
    "Q4": "4분기(10~12월)",
    "FY": "연간",
}
PREV_QUARTER = {"Q2": ("Q1", 0), "Q3": ("Q2", 0), "Q4": ("Q3", 0), "Q1": ("Q4", -1)}
DEFAULT_METRICS = ("매출액", "영업이익", "당기순이익")


def _to_int(v) -> int | None:
    if v in (None, "", "-"):
        return None
    try:
        return int(str(v).replace(",", ""))
    except ValueError:
        return None


def _rows(corp_code: str, year: int, reprt_code: str, fs_div: str) -> list[Financial]:
    with session_scope() as s:
        return list(
            s.scalars(
                select(Financial).where(
                    Financial.corp_code == corp_code,
                    Financial.bsns_year == year,
                    Financial.reprt_code == reprt_code,
                    Financial.fs_div == fs_div,
                )
            )
        )


def _match(rows: list[Financial], metric: str) -> Financial | None:
    exact = [r for r in rows if r.account_nm == metric]
    if exact:
        return exact[0]
    loose = [r for r in rows if metric in r.account_nm or r.account_nm in metric]
    return loose[0] if loose else None


def metric_value(
    corp_code: str, year: int, period: str, metric: str, fs_div: str = "CFS"
) -> tuple[int | None, str | None]:
    """(금액, 근거 접수번호). Q4는 연간 - 1~9월 누적으로 계산한다."""
    if period == "Q4":
        fy, r1 = metric_value(corp_code, year, "FY", metric, fs_div)
        nine, _ = metric_value(corp_code, year, "9M", metric, fs_div)
        return (fy - nine if fy is not None and nine is not None else None), r1
    reprt, field = PERIOD_SOURCE[period]
    row = _match(_rows(corp_code, year, reprt, fs_div), metric)
    if row is None:
        return None, None
    if row.sj_div == "BS":  # 재무상태표는 시점 값이라 누적 개념이 없다
        field = "thstrm_amount"
    return _to_int(row.payload.get(field)), row.rcept_no


def financial_evidence(a: Analysis) -> list[Evidence]:
    """질문한 회사·기간·계정의 재무 수치와 비교 기준(전년 동기, 직전 분기)을 근거로 만든다."""
    if not (a.fiscal_year and a.period):
        return []
    metrics = a.metrics or list(DEFAULT_METRICS)
    with session_scope() as s:
        names = dict(s.execute(select(Company.corp_code, Company.corp_name)).all())
    out = []
    for code in to_corp_codes(a.companies):
        lines, rcept = [], None
        for metric in metrics:
            cur, r = metric_value(code, a.fiscal_year, a.period, metric)
            if cur is None:
                continue
            rcept = rcept or r
            prev_year, _ = metric_value(code, a.fiscal_year - 1, a.period, metric)
            line = f"- {metric}: {format_krw(cur)}"
            if prev_year:
                line += f" / 전년 동기 {format_krw(prev_year)} ({(cur - prev_year) / abs(prev_year):+.1%})"
            if a.period in PREV_QUARTER:
                pq, dy = PREV_QUARTER[a.period]
                prev_q, _ = metric_value(code, a.fiscal_year + dy, pq, metric)
                if prev_q:
                    line += (
                        f" / 직전 분기 {format_krw(prev_q)} ({(cur - prev_q) / abs(prev_q):+.1%})"
                    )
            lines.append(line)
        if lines:
            label = PERIOD_LABEL[a.period]
            out.append(
                Evidence(
                    kind="financial",
                    title=f"{names[code]} | {a.fiscal_year}년 {label} | 재무제표(연결) | 접수번호 {rcept}",
                    rcept_no=rcept or "",
                    text="\n".join(lines),
                )
            )
    return out
