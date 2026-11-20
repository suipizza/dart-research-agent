"""LangGraph 에이전트.

    질문 → [analyze] ─┬─ refuse ──────────────────────────────────────────────→ 끝
                      ├─ search ────→ [retrieve] ─→ [generate] ─→ [verify] ─┬→ 끝
                      └─ financial ─→ [financial] ┘       ↑                  │
                                                          └── 재검색/재생성 ←─┘

재시도 규칙 (최대 MAX_RETRIES회)
- '확인 불가'인데 아직 풀 수 있는 검색 조건이 있으면 → 조건을 한 단계 풀어 다시 검색 (retrieve로)
- 근거에 없는 숫자가 있으면 → 그 숫자를 알려주고 다시 답하게 함 (generate로)
- 그래도 숫자가 확인되지 않으면 답변 끝에 경고를 붙인다

    uv run python -m app.agent.graph "삼전 3분기 영업익 얼마임?"
"""

import argparse
from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.analysis import Analysis, analyze
from app.agent.tools import (
    RELAX_STEPS,
    Evidence,
    SearchPlan,
    filing_evidence,
    financial_evidence,
    format_evidence,
    group_by_filing,
    plan_search,
    search_with_relaxation,
)
from app.agent.verify import VerifyResult, verify_numbers
from app.llm import EXPERIMENT_MODEL, MODELS, Usage, call_json
from app.rag.answer import SYSTEM_PROMPT as BASE_PROMPT
from app.rag.answer import AnswerOut

MAX_RETRIES = 2
UNVERIFIED_NOTE = "\n\n(주의: 일부 숫자를 원문에서 확인하지 못했습니다. 원문 공시를 확인해 주세요.)"

AGENT_PROMPT = (
    BASE_PROMPT
    + """

추가 규칙
7. [재무제표] 근거가 있으면 매출액·영업이익 같은 재무 수치는 그것을 우선 사용합니다. 재무제표의 '전년 동기', '직전 분기' 비교도 활용합니다.
8. 공시 제목에 '종속회사의 주요경영사항' 또는 '자회사의 주요경영사항'이 있으면, 그 결정의 주체는 질문한 회사가 아니라 그 자회사입니다.
   질문한 회사 자체의 결정인지 먼저 구분하고, 예/아니오로 답할 질문이면 결론(예/아니오)부터 정확히 말합니다.
9. 같은 사건의 원공시와 [기재정정]이 함께 있으면 숫자는 가장 최근 정정본을 기준으로 답하고, '처음 결정한 날'은 원공시 날짜로 답합니다.
   정정 전후 값이 다르면 둘 다 적습니다.
10. 표에 '단위 : 억원', '단위 : 백만원' 같은 줄이 있으면 숫자와 함께 단위를 반드시 적습니다.
11. 연결·별도 실적이 함께 있으면, 질문에 '별도'가 없는 한 연결 기준으로 답합니다.
12. 목록 질문은 질문의 조건(기간, 공시 유형, 회사 종류)에 맞는 항목만 빠짐없이 모읍니다. 조건에 맞지 않는 공시는 제외합니다."""
)


class State(TypedDict, total=False):
    question: str
    model: str
    analysis: Analysis
    plan: SearchPlan
    relax_level: int
    fin_evidence: list[Evidence]
    evidence: list[Evidence]
    feedback: str
    out: AnswerOut
    verify: VerifyResult
    retries: int
    usage: Usage
    trace: list[str]


# ── 노드 ─────────────────────────────────────────────────────────


def node_analyze(state: State) -> State:
    a = analyze(state["question"], state["model"], state["usage"])
    trace = [f"analyze: route={a.route} companies={a.companies} categories={list(a.categories)}"]
    return {"analysis": a, "retries": 0, "relax_level": 0, "fin_evidence": [], "trace": trace}


def node_refuse(state: State) -> State:
    a = state["analysis"]
    if a.out_of_scope_company:
        msg = f"{a.out_of_scope_company}은(는) 수집 대상 기업이 아니라 공시를 확인할 수 없습니다."
    else:
        msg = a.refuse_reason or "공시로 답할 수 없는 질문입니다."
    msg += " 이 서비스는 코스피 시가총액 상위 기업의 2024년 이후 공시 사실만 안내하며, 주가 전망이나 투자 판단은 하지 않습니다."
    out = AnswerOut(answer=msg, citations=[], unanswerable=True)
    return {"out": out, "evidence": [], "trace": state["trace"] + ["refuse"]}


def node_financial(state: State) -> State:
    ev = financial_evidence(state["analysis"])
    return {"fin_evidence": ev, "trace": state["trace"] + [f"financial: {len(ev)} blocks"]}


def node_retrieve(state: State) -> State:
    plan = state.get("plan") or plan_search(state["analysis"], state["question"])
    hits, level = search_with_relaxation(plan, start=state.get("relax_level", 0))
    groups = group_by_filing(hits, plan)
    evidence = state.get("fin_evidence", []) + filing_evidence(groups, plan)
    step = f"retrieve: {len(hits)} chunks → {len(groups)} filings (조건: {RELAX_STEPS[level]})"
    return {
        "plan": plan,
        "relax_level": level,
        "evidence": evidence,
        "feedback": "",
        "trace": state["trace"] + [step],
    }


def node_generate(state: State) -> State:
    user = f"[공시 발췌]\n{format_evidence(state['evidence'])}\n\n[질문]\n{state['question']}"
    if state.get("feedback"):
        user += f"\n\n[검증 결과]\n{state['feedback']}"
    out = call_json(
        model=state["model"],
        system=AGENT_PROMPT,
        user=user,
        schema=AnswerOut,
        effort="medium",
        usage=state["usage"],
    )
    return {"out": out, "trace": state["trace"] + [f"generate (unanswerable={out.unanswerable})"]}


def node_verify(state: State) -> State:
    v = verify_numbers(state["out"].answer, format_evidence(state["evidence"]))
    step = f"verify: {v.checked} checked, unverified={v.unverified}"
    return {"verify": v, "trace": state["trace"] + [step]}


def node_retry_search(state: State) -> State:
    return {
        "relax_level": state["relax_level"] + 1,
        "retries": state["retries"] + 1,
        "trace": state["trace"] + ["retry: 검색 조건 완화"],
    }


def node_retry_generate(state: State) -> State:
    nums = ", ".join(state["verify"].unverified)
    fb = f"다음 숫자는 공시 발췌에서 확인되지 않았습니다: {nums}. 발췌에 있는 숫자만 사용해 다시 답하세요."
    return {
        "feedback": fb,
        "retries": state["retries"] + 1,
        "trace": state["trace"] + ["retry: 숫자 재확인"],
    }


def node_finish(state: State) -> State:
    out = state["out"]
    if not state["verify"].ok:
        out = AnswerOut(
            answer=out.answer + UNVERIFIED_NOTE,
            citations=out.citations,
            unanswerable=out.unanswerable,
        )
    return {"out": out}


# ── 분기 ─────────────────────────────────────────────────────────


def after_analyze(state: State) -> str:
    return state["analysis"].route


def after_verify(state: State) -> str:
    if state["retries"] >= MAX_RETRIES:
        return "finish"
    if state["out"].unanswerable and state["relax_level"] < len(RELAX_STEPS) - 1:
        return "retry_search"
    if not state["verify"].ok:
        return "retry_generate"
    return "finish"


def build_graph():
    g = StateGraph(State)
    g.add_node("analyze", node_analyze)
    g.add_node("refuse", node_refuse)
    g.add_node("financial", node_financial)
    g.add_node("retrieve", node_retrieve)
    g.add_node("generate", node_generate)
    g.add_node("verify", node_verify)
    g.add_node("retry_search", node_retry_search)
    g.add_node("retry_generate", node_retry_generate)
    g.add_node("finish", node_finish)

    g.add_edge(START, "analyze")
    g.add_conditional_edges(
        "analyze",
        after_analyze,
        {"refuse": "refuse", "search": "retrieve", "financial": "financial"},
    )
    g.add_edge("refuse", END)
    g.add_edge("financial", "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "verify")
    g.add_conditional_edges(
        "verify",
        after_verify,
        {
            "retry_search": "retry_search",
            "retry_generate": "retry_generate",
            "finish": "finish",
        },
    )
    g.add_edge("retry_search", "retrieve")
    g.add_edge("retry_generate", "generate")
    g.add_edge("finish", END)
    return g.compile()


_GRAPH = None


@dataclass
class AgentResult:
    question: str
    answer: str
    unanswerable: bool
    cited_rcept_nos: list[str]
    evidence_text: str
    model: str
    trace: list[str]
    usage: Usage = field(default_factory=Usage)


def run_agent(question: str, model: str = EXPERIMENT_MODEL) -> AgentResult:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    usage = Usage()
    final: State = _GRAPH.invoke(
        {"question": question, "model": model, "usage": usage, "trace": []}
    )
    evidence = final.get("evidence", [])
    out = final["out"]
    cited = [evidence[i - 1].rcept_no for i in out.citations if 1 <= i <= len(evidence)]
    return AgentResult(
        question=question,
        answer=out.answer,
        unanswerable=out.unanswerable,
        cited_rcept_nos=[c for c in dict.fromkeys(cited) if c],
        evidence_text=format_evidence(evidence),
        model=model,
        trace=final.get("trace", []),
        usage=usage,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="LangGraph 공시 에이전트")
    p.add_argument("question")
    p.add_argument("--model", choices=list(MODELS), default="haiku")
    args = p.parse_args()
    r = run_agent(args.question, MODELS[args.model])
    print(r.answer)
    print(
        "\n출처:",
        *[f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={c}" for c in r.cited_rcept_nos],
        sep="\n  ",
    )
    print("\n흐름:", *r.trace, sep="\n  ")
    print(f"\n[{r.model}] ${r.usage.cost_usd:.4f}")


if __name__ == "__main__":
    main()
