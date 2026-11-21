"""② 도구: 필터 검색(+조건 완화)과 재무 데이터 조회.

재무 데이터는 1단계에서 이미 DB(financials)에 받아 두었으므로 질문 시점에 DART API를 부르지 않는다.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app.agent.analysis import Analysis, earnings_filing_window, parse_date, to_corp_codes
from app.config import get_settings
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
    top_k: int  # v1: 근거로 넘길 청크 수 / v2: 공시를 고르기 위해 먼저 가져오는 청크 수
    latest: bool
    max_filings: int = 3  # v2: 근거로 넘길 서로 다른 공시 수
    is_list: bool = False
    want_subsidiary: bool = False  # 질문이 자회사·종속회사를 직접 묻는가


def plan_search(a: Analysis, question: str) -> SearchPlan:
    since, until = parse_date(a.filing_from), parse_date(a.filing_to)
    categories = list(a.categories) or None
    if a.route == "financial":
        categories = ["earnings_prelim"]
        if a.fiscal_year and a.period and not (since or until):
            since, until = earnings_filing_window(a.fiscal_year, a.period)
    max_filings = 10 if a.is_list else 3
    return SearchPlan(
        query=a.search_query or question,
        corp_codes=to_corp_codes(a.companies) or None,
        since=since,
        until=until,
        categories=categories,
        # 목록은 빠짐없이 모으는 게 핵심이라 후보 청크를 더 넓게 본다(공시 10건 × 8).
        # 40개일 때는 자회사 공시가 빈자리를 채우고 정작 해당 회사 공시가 후보에 없었다(dev q48).
        top_k=max_filings * (8 if a.is_list else 4),
        latest=a.latest,
        max_filings=max_filings,
        is_list=a.is_list,
        want_subsidiary=any(w in question for w in ("자회사", "종속")),
    )


def relaxed(plan: SearchPlan, step: str) -> SearchPlan:
    p = SearchPlan(**plan.__dict__)
    if step in ("no_category", "company_only"):
        p.categories = None
    if step in ("no_date", "company_only"):
        p.since = p.until = None
    return p


def run_search(plan: SearchPlan) -> list[Hit]:
    """필터 + 벡터 검색. 재순위를 켜면 후보를 넉넉히 가져와 다시 정렬한 뒤 top_k개만 쓴다.

    목록 질문은 재순위하지 않는다. 재순위는 1위를 정확히 고르는 데 강하지만, 목록은 빠짐없이 모으는 게
    중요하다. dev에서 재순위가 다른 회사의 비슷한 공시를 위로 올려 목록에서 한 회사가 빠졌다(q48).
    """
    s = get_settings()
    use_rerank = s.rerank and not plan.is_list
    pool = max(plan.top_k, s.rerank_pool) if use_rerank else plan.top_k
    hits, _ = search(
        plan.query,
        top_k=pool,
        corp_codes=plan.corp_codes,
        since=plan.since,
        until=plan.until,
        categories=plan.categories,
        detect_company=False,  # 회사는 질문 분석 노드가 이미 정했다
    )
    if use_rerank:
        from app.rag.rerank import rerank

        hits = rerank(plan.query, hits)
    return hits[: plan.top_k]


# ── v2: 청크 → 공시 단위 근거 ────────────────────────────────────
# v1은 상위 청크 5개만 넘겨서, 맞는 공시를 찾고도 금액·지분율이 든 다른 청크를 놓쳤다.
# 우리 공시는 대부분 1~5천 자로 짧으므로 공시 전체를 근거로 넘긴다.

# 근거 분량 예산: 공시 수로 나눠 공시당 상한을 정한다. 공시가 1건이면 긴 합병 공시도 거의 다 볼 수 있다.
CHAR_BUDGET = 24_000
LIST_CHAR_BUDGET = 30_000
MIN_DOC_CHARS = 2_500
CORRECTION_WINDOW_DAYS = 150  # 원공시 뒤 이 기간 안의 [기재정정]을 같은 사건으로 본다
_SUBSIDIARY_MARKS = ("종속회사의주요경영사항", "자회사의주요경영사항")


def is_subsidiary_filing(report_nm: str) -> bool:
    """'종속회사/자회사의 주요경영사항' 공시: 결정 주체가 제출 회사가 아니라 자회사다."""
    compact = report_nm.replace(" ", "")
    return any(m in compact for m in _SUBSIDIARY_MARKS)


def group_by_filing(hits: list[Hit], plan: SearchPlan) -> list[list[Hit]]:
    """청크를 공시별로 묶고 순서를 정한다.

    - 기본: 공시 안에서 가장 가까운 청크의 순위
    - latest: 최신 공시부터
    - 자회사 공시는 질문이 자회사를 묻지 않는 한 뒤로 (지우지는 않는다. 함정 질문에서 근거로 필요)
    """
    groups: dict[str, list[Hit]] = {}
    for h in hits:
        groups.setdefault(h.rcept_no, []).append(h)
    ordered = list(groups.values())  # 검색 결과가 거리순이므로 첫 등장 순서 = 관련도 순
    if plan.latest:
        ordered.sort(key=lambda g: g[0].rcept_dt, reverse=True)
    if not plan.want_subsidiary:
        ordered.sort(key=lambda g: is_subsidiary_filing(g[0].report_nm))  # 안정 정렬
    return ordered[: plan.max_filings]


def _document_texts(rcept_nos: list[str]) -> dict[str, str]:
    from app.models import Document

    with session_scope() as s:
        rows = s.execute(
            select(Document.rcept_no, Document.text).where(Document.rcept_no.in_(rcept_nos))
        ).all()
    return dict(rows)


def _clean_document(text: str) -> str:
    """표지(주소·전화번호) 섹션을 뺀 원문."""
    from app.rag.chunker import SKIP_SECTIONS, split_sections

    parts = []
    for title, body in split_sections(text):
        if any(skip in title for skip in SKIP_SECTIONS):
            continue
        parts.append(f"## {title}\n{body}" if title else body)
    return "\n\n".join(parts)


def later_corrections(rcept_nos: list[str]) -> dict[str, list[tuple[str, str, str]]]:
    """원공시마다 그 뒤에 나온 같은 회사·같은 유형의 [기재정정] (접수번호, 날짜, 제목) 목록.

    정정 공시는 원공시보다 늦게 나온다. "6월 유상증자"를 6월 공시로만 거르면
    7월의 정정(최종 금액)을 놓치므로 따로 따라간다.
    """
    from datetime import timedelta

    from app.models import Filing

    with session_scope() as s:
        originals = s.scalars(select(Filing).where(Filing.rcept_no.in_(rcept_nos))).all()
        out: dict[str, list[tuple[str, str, str]]] = {}
        for f in originals:
            if f.is_correction or not f.category:
                continue
            rows = s.execute(
                select(Filing.rcept_no, Filing.rcept_dt, Filing.report_nm)
                .where(
                    Filing.corp_code == f.corp_code,
                    Filing.category == f.category,
                    Filing.is_correction.is_(True),
                    Filing.rcept_dt > f.rcept_dt,
                    Filing.rcept_dt <= f.rcept_dt + timedelta(days=CORRECTION_WINDOW_DAYS),
                )
                .order_by(Filing.rcept_dt)
            ).all()
            if rows:
                out[f.rcept_no] = [(r, str(d), nm) for r, d, nm in rows]
    return out


def filing_evidence(groups: list[list[Hit]], plan: SearchPlan) -> list[Evidence]:
    corrections = later_corrections([g[0].rcept_no for g in groups])
    picked = {g[0].rcept_no for g in groups}
    extra = [c for cs in corrections.values() for c in cs if c[0] not in picked]
    n_docs = max(len(groups) + len(extra), 1)
    budget = LIST_CHAR_BUDGET if plan.is_list else CHAR_BUDGET
    cap = max(budget // n_docs, MIN_DOC_CHARS)

    docs = _document_texts([g[0].rcept_no for g in groups] + [c[0] for c in extra])
    out = []
    for g in groups:
        h = g[0]
        full = _clean_document(docs.get(h.rcept_no, ""))
        if full and len(full) <= cap:
            text = full
        else:
            # 긴 공시(합병·분할 등)는 검색된 청크만, 원문 순서대로
            chunks = [x.text.split("\n", 1)[-1] for x in sorted(g, key=lambda x: x.chunk_index)]
            text = "\n...\n".join(chunks)[:cap]
        out.append(
            Evidence(
                kind="filing",
                title=f"{h.corp_name} | {h.rcept_dt} | {h.report_nm} | 접수번호 {h.rcept_no}",
                rcept_no=h.rcept_no,
                text=text,
            )
        )
        for c_no, c_dt, c_nm in corrections.get(h.rcept_no, []):
            if c_no in picked:
                continue
            picked.add(c_no)
            body = _clean_document(docs.get(c_no, ""))[:cap]
            if body:
                out.append(
                    Evidence(
                        kind="filing",
                        title=f"{h.corp_name} | {c_dt} | {c_nm} | 접수번호 {c_no} (위 공시의 정정)",
                        rcept_no=c_no,
                        text=body,
                    )
                )
    return out


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
