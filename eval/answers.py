"""답변 평가: 골드 질문마다 답변을 생성하고 채점한다.

    uv run python -m eval.answers --system agent --label v1                       # 4단계 에이전트
    uv run python -m eval.answers --model haiku --label baseline --limit 5      # 시험 실행
    uv run python -m eval.answers --model haiku --label baseline                # dev 전체
    uv run python -m eval.answers --set test --model haiku --label final        # test (전체 점수만)

지표
- 정답률     : LLM 채점 correct 비율 (partial은 0.5로 따로 집계)
- 사실 포함률: key_fact가 답에 그대로 들어간 비율 (코드 채점)
- 출처 적중률: 인용한 공시 중 정답 공시가 있는 비율 (코드 채점, gold 있는 질문만)
- 환각률     : 발췌에 없는 내용을 지어낸 비율 (LLM 채점)
- 과잉 거절률: 답할 수 있는 질문(route!=refuse)에 '확인 불가'로 답한 비율
  (거절 질문을 제대로 거절했는지는 refuse 유형의 정답률로 본다. LLM 채점자의 refused 표시는
   '거절하면서 사실을 덧붙인 답'에서 일관되지 않아 거절 질문 채점에는 쓰지 않는다)
"""

import argparse
import json
import statistics
from datetime import datetime

from app.llm import MODELS, Usage
from app.rag.answer import answer_question, format_context
from eval.judge import JUDGE_MODEL, citation_hit, key_fact_hits, llm_judge
from eval.retrieval import EVAL_DIR, RESULTS, SETS, load_gold


def generate(question: str, model: str, system: str):
    """(답변 객체, 채점자에게 보여줄 근거 텍스트, 흐름 기록)"""
    if system == "agent":
        from app.agent.graph import run_agent

        r = run_agent(question, model=model, source="eval")
        return r, r.evidence_text, r.trace
    a = answer_question(question, model=model)
    return a, format_context(a.hits), []


def evaluate_one(
    q: dict, model: str, gen_usage: Usage, judge_usage: Usage, system: str = "rag"
) -> dict:
    a, context, trace = generate(q["question"], model, system)
    gen_usage.input_tokens += a.usage.input_tokens
    gen_usage.output_tokens += a.usage.output_tokens
    gen_usage.cost_usd += a.usage.cost_usd

    facts = key_fact_hits(a.answer, q["key_facts"])
    v = llm_judge(q["question"], q["answer"], q.get("note"), a.answer, context, judge_usage)
    should_refuse = q["route"] == "refuse"
    return {
        "id": q["id"],
        "type": q["type"],
        "route": q["route"],
        "question": q["question"],
        "expected": q["answer"],
        "answer": a.answer,
        "unanswerable": a.unanswerable,
        "cited": a.cited_rcept_nos,
        "trace": trace,
        "fact_hits": facts,
        "fact_rate": statistics.mean(facts) if facts else None,
        "citation_hit": citation_hit(a.cited_rcept_nos, q["gold"]),
        "correctness": v.correctness,
        "hallucination": v.hallucination,
        "refused": v.refused,
        "over_refusal": None if should_refuse else v.refused,
        "judge_reason": v.reason,
    }


def _mean(vals) -> float | None:
    vals = [v for v in vals if v is not None]
    return statistics.mean(vals) if vals else None


def summarize(rows: list[dict]) -> dict:
    def agg(rs):
        return {
            "n": len(rs),
            "correct": _mean(r["correctness"] == "correct" for r in rs),
            "correct+partial": _mean(
                {"correct": 1.0, "partial": 0.5, "wrong": 0.0}[r["correctness"]] for r in rs
            ),
            "fact_rate": _mean(r["fact_rate"] for r in rs),
            "citation_hit": _mean(r["citation_hit"] for r in rs),
            "hallucination": _mean(r["hallucination"] for r in rs),
            "over_refusal": _mean(r.get("over_refusal") for r in rs),
        }

    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r)
    return {"all": agg(rows), **{t: agg(rs) for t, rs in sorted(by_type.items())}}


def print_table(summary: dict) -> None:
    cols = [
        "correct",
        "correct+partial",
        "fact_rate",
        "citation_hit",
        "hallucination",
        "over_refusal",
    ]
    print("| 유형 | n | " + " | ".join(cols) + " |")
    print("|" + "---|" * (len(cols) + 2))
    for name, s in summary.items():
        cells = ["-" if s[c] is None else f"{s[c]:.2f}" for c in cols]
        print(f"| {name} | {s['n']} | " + " | ".join(cells) + " |")


def run(
    model_key: str,
    label: str,
    which: str,
    limit: int | None,
    ids: list[str] | None,
    system: str = "rag",
):
    model = MODELS[model_key]
    held_out = which == "test"
    items = load_gold(SETS[which])
    if ids:
        items = [q for q in items if q["id"] in ids]
    if limit:
        items = items[:limit]

    gen_usage, judge_usage = Usage(), Usage()
    rows, errors = [], []
    for i, q in enumerate(items, 1):
        try:
            rows.append(evaluate_one(q, model, gen_usage, judge_usage, system))
        except Exception as e:  # 한 문항 실패로 전체 실행을 버리지 않는다
            errors.append({"id": q["id"], "error": str(e)[:300]})
        if not held_out:
            print(f"  [{i}/{len(items)}] {q['id']} {rows[-1]['correctness'] if rows else '?'}")

    summary = summarize(rows) if rows else {}
    if held_out:
        summary = {"all": summary["all"]} if summary else {}
    record = {
        "label": label,
        "set": which,
        "system": system,
        "model": model,
        "judge_model": JUDGE_MODEL,
        "created": datetime.now().isoformat(),
        "cost_usd": {"generation": gen_usage.cost_usd, "judge": judge_usage.cost_usd},
        "tokens": {
            "generation": [gen_usage.input_tokens, gen_usage.output_tokens],
            "judge": [judge_usage.input_tokens, judge_usage.output_tokens],
        },
        "errors": errors if not held_out else len(errors),
        "summary": summary,
    }
    if not held_out:
        record["rows"] = rows
    RESULTS.mkdir(exist_ok=True)
    out = (
        RESULTS / f"{datetime.now():%Y%m%d-%H%M}_answers_{which}_{system}_{model_key}_{label}.json"
    )
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(
        f"\n[{which} / {system} / {model_key} / {label}] 채점 {len(rows)}개, 실패 {len(errors)}개"
    )
    if summary:
        print_table(summary)
    total = gen_usage.cost_usd + judge_usage.cost_usd
    print(
        f"\n비용: 생성 ${gen_usage.cost_usd:.3f} + 채점 ${judge_usage.cost_usd:.3f} = ${total:.3f}"
    )
    if errors and not held_out:
        print("실패:", errors)
    print(f"저장: {out.relative_to(EVAL_DIR.parent)}")
    from app import obs

    obs.flush()
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="답변 평가")
    p.add_argument(
        "--system", choices=["rag", "agent"], default="rag", help="기본 RAG 또는 에이전트"
    )
    p.add_argument("--model", choices=list(MODELS), default="haiku")
    p.add_argument("--label", default="run")
    p.add_argument("--set", dest="which", choices=list(SETS), default="dev")
    p.add_argument("--limit", type=int)
    p.add_argument("--ids", nargs="*", help="특정 문항만 (예: q01 q30)")
    args = p.parse_args()
    run(args.model, args.label, args.which, args.limit, args.ids, args.system)


if __name__ == "__main__":
    main()
