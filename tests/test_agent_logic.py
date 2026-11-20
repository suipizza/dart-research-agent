"""에이전트의 분기·완화·기간 규칙 (DB·LLM 없이)."""

from datetime import date

from app.agent.analysis import earnings_filing_window, period_end
from app.agent.graph import MAX_RETRIES, after_verify
from app.agent.tools import PERIOD_SOURCE, RELAX_STEPS, SearchPlan, format_krw, relaxed
from app.agent.verify import VerifyResult
from app.rag.answer import AnswerOut


def _state(unanswerable=False, unverified=(), retries=0, relax=0):
    return {
        "out": AnswerOut(answer="x", citations=[], unanswerable=unanswerable),
        "verify": VerifyResult(checked=1, unverified=list(unverified)),
        "retries": retries,
        "relax_level": relax,
    }


def test_after_verify_finishes_when_ok():
    assert after_verify(_state()) == "finish"


def test_after_verify_relaxes_search_when_unanswerable():
    assert after_verify(_state(unanswerable=True)) == "retry_search"


def test_after_verify_does_not_relax_past_last_step():
    last = len(RELAX_STEPS) - 1
    assert after_verify(_state(unanswerable=True, relax=last)) == "finish"


def test_after_verify_regenerates_on_unverified_numbers():
    assert after_verify(_state(unverified=["13,500,000,000,000"])) == "retry_generate"


def test_after_verify_stops_at_max_retries():
    assert after_verify(_state(unverified=["1"], retries=MAX_RETRIES)) == "finish"


def test_relax_steps_drop_conditions_in_order():
    plan = SearchPlan("q", ["001"], date(2026, 8, 1), date(2026, 8, 31), ["dividend"], 5, False)
    assert relaxed(plan, "no_category").categories is None
    assert relaxed(plan, "no_category").since == date(2026, 8, 1)
    assert relaxed(plan, "no_date").since is None and relaxed(plan, "no_date").categories
    only = relaxed(plan, "company_only")
    assert only.since is None and only.categories is None and only.corp_codes == ["001"]
    assert plan.categories == ["dividend"]  # 원본은 그대로


def test_quarter_vs_cumulative_source():
    # 반기보고서: 2분기 = 3개월치, 상반기 = 누적
    assert PERIOD_SOURCE["Q2"] == ("11012", "thstrm_amount")
    assert PERIOD_SOURCE["H1"] == ("11012", "thstrm_add_amount")
    assert PERIOD_SOURCE["9M"] == ("11014", "thstrm_add_amount")


def test_fiscal_year_results_are_filed_next_year():
    start, end = earnings_filing_window(2025, "FY")
    assert start == date(2025, 12, 31) and end.year == 2026
    assert period_end(2026, "Q3") == date(2026, 9, 30)


def test_format_krw():
    assert format_krw(83_333_818_000_000) == "83,333,818,000,000원(약 83조 3,338억원)"
    assert format_krw(586_443_842_141) == "586,443,842,141원(약 5,864억원)"
