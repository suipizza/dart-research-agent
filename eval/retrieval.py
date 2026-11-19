"""검색 평가: 골드 질문마다 정답 공시가 검색 결과 몇 위에 나오는지 잰다.

    uv run python -m eval.retrieval --label baseline              # dev 세트 (상세 결과 출력·저장)
    uv run python -m eval.retrieval --set test --label final      # test 세트 (집계 점수만)

지표 (gold가 있는 질문만 대상)
- hit@k   : 정답 공시 중 하나라도 상위 k개 공시 안에 있으면 1
- MRR     : 처음 나온 정답 공시 순위의 역수 평균 (1위=1, 2위=0.5, 10위 밖=0)
- cover@10: 목록형 질문에서 정답 공시를 몇 % 찾았는지

검색은 청크 단위라 같은 공시의 청크가 여러 개 나올 수 있다. 공시(접수번호) 기준으로
중복을 지운 순위를 쓴다. 결과는 eval/results/에 JSON으로 저장한다.
"""

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy import select

from app.db import session_scope
from app.models import Chunk

EVAL_DIR = Path(__file__).resolve().parent
GOLD = EVAL_DIR / "gold.yaml"  # dev: 개발 중 자유롭게 본다
TEST = EVAL_DIR / "test.yaml"  # test: 보지 않는 세트. 집계 점수만 본다
SETS = {"dev": GOLD, "test": TEST}
RESULTS = EVAL_DIR / "results"
KS = (1, 3, 5, 10)
CHUNK_POOL = 40  # 공시 10개를 채우려고 청크를 넉넉히 가져온다


def load_gold(path: Path = GOLD) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def ranked_filings(hits) -> list[str]:
    seen: list[str] = []
    for h in hits:
        if h.rcept_no not in seen:
            seen.append(h.rcept_no)
    return seen


def score_one(ranked: list[str], gold: list[str]) -> dict:
    gold_set = set(gold)
    first = next((i for i, r in enumerate(ranked, 1) if r in gold_set), None)
    found_10 = gold_set & set(ranked[:10])
    out = {f"hit@{k}": int(first is not None and first <= k) for k in KS}
    out["rr"] = 1 / first if first and first <= 10 else 0.0
    out["first_rank"] = first
    out["cover@10"] = len(found_10) / len(gold_set)
    return out


def check_gold_in_index(items: list[dict]) -> list[str]:
    """gold 접수번호가 chunks에 실제로 있는지. 오타·원문 없는 공시를 잡아낸다."""
    wanted = {r for q in items for r in q["gold"]}
    with session_scope() as s:
        have = set(s.scalars(select(Chunk.rcept_no).where(Chunk.rcept_no.in_(wanted)).distinct()))
    return sorted(wanted - have)


def summarize(rows: list[dict]) -> dict:
    def agg(rs):
        return {
            "n": len(rs),
            **{f"hit@{k}": statistics.mean(r[f"hit@{k}"] for r in rs) for k in KS},
            "mrr": statistics.mean(r["rr"] for r in rs),
            "cover@10": statistics.mean(r["cover@10"] for r in rs),
        }

    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r)
    return {"all": agg(rows), **{t: agg(rs) for t, rs in sorted(by_type.items())}}


def print_table(summary: dict) -> None:
    cols = ["n", "hit@1", "hit@3", "hit@5", "hit@10", "mrr", "cover@10"]
    print("| 유형 | " + " | ".join(cols) + " |")
    print("|" + "---|" * (len(cols) + 1))
    for name, s in summary.items():
        cells = [str(s["n"])] + [f"{s[c]:.2f}" for c in cols[1:]]
        print(f"| {name} | " + " | ".join(cells) + " |")


def run(label: str, detect_company: bool = True, which: str = "dev") -> Path:
    from app.rag.search import search

    held_out = which == "test"
    items = [q for q in load_gold(SETS[which]) if q["gold"]]
    missing = check_gold_in_index(items)
    if missing:
        print(f"⚠ 인덱스에 없는 gold 접수번호 {len(missing)}개: {missing}")

    rows = []
    for q in items:
        hits, codes = search(q["question"], top_k=CHUNK_POOL, detect_company=detect_company)
        ranked = ranked_filings(hits)
        rows.append(
            {
                "id": q["id"],
                "type": q["type"],
                "question": q["question"],
                "company_filter": codes,
                "top5": ranked[:5],
                **score_one(ranked, q["gold"]),
            }
        )

    summary = summarize(rows)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{datetime.now():%Y%m%d-%H%M}_{which}_{label}.json"
    if held_out:
        summary = {"all": summary["all"]}  # 유형별 점수도 남기지 않는다
    record = {
        "label": label,
        "set": which,
        "created": datetime.now().isoformat(),
        "summary": summary,
    }
    if not held_out:
        record["rows"] = (
            rows  # test 세트는 문항별 결과를 남기지 않는다 (틀린 이유를 보지 않기 위해)
        )
    out.write_text(
        json.dumps(
            record,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[{which} / {label}] 질문 {len(rows)}개\n")
    print_table(summary)
    if held_out:
        print("\n(test 세트: 전체 점수만 표시. 유형별·문항별 결과는 보지 않는다)")
        print(f"\n저장: {out.relative_to(EVAL_DIR.parent)}")
        return out
    print("\n정답을 10위 안에서 못 찾은 질문:")
    for r in rows:
        if r["first_rank"] is None or r["first_rank"] > 10:
            print(f"  {r['id']} ({r['type']}) {r['question']}")
    print(f"\n저장: {out.relative_to(EVAL_DIR.parent)}")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="검색 평가")
    p.add_argument("--label", default="run")
    p.add_argument("--set", dest="which", choices=list(SETS), default="dev")
    p.add_argument("--no-company-filter", action="store_true", help="회사명 필터 끄기 (비교 실험)")
    args = p.parse_args()
    run(args.label, detect_company=not args.no_company_filter, which=args.which)


if __name__ == "__main__":
    main()
