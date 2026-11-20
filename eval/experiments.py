"""6단계 검색 실험: 청킹·머리말·재순위 버전을 같은 dev 질문으로 비교한다 (LLM 비용 없음).

    uv run python -m eval.experiments                        # 기본: A, B, C, A+R
    uv run python -m eval.experiments --variants A A+R --limit 5
    uv run python -m eval.experiments --fresh               # 체크포인트를 무시하고 처음부터

버전 하나가 끝날 때마다 eval/results/experiments-checkpoint.json에 저장한다.
중간에 멈춘 뒤 다시 실행하면 이미 끝난 버전은 건너뛰고 남은 버전부터 이어서 한다.

버전
- A    : 운영 인덱스(chunks). 머리말 있음, 약 1,000자.
- B    : chunks_exp 'no_header'    머리말 없음
- C    : chunks_exp 'table_header' 머리말 + 잘린 표에 열 이름 반복
- A+R  : A에서 40개를 가져와 재순위 모델(bge-reranker-v2-m3, 입력 1,024토큰)로 다시 정렬
- A+R20: 속도 절충. 상위 20개만, 입력 512토큰 (맥 GPU에서 질문당 약 10초 vs 25초)
- C+R  : C + 재순위 (C 인덱스가 있을 때)

비교 조건은 3단계 기준선과 같다: 질문 문장으로 벡터 검색 + 질문 속 회사명 필터.
지표는 eval.retrieval과 같다(공시 단위 hit@k, MRR, 목록 커버리지). 시간도 함께 잰다.
"""

import argparse
import json
import statistics
import time
from datetime import datetime
from functools import lru_cache

from sqlalchemy import select

from app.db import session_scope
from app.models import Chunk, ChunkExp, Company
from app.rag.companies import build_lookup, find_companies
from eval.retrieval import EVAL_DIR, RESULTS, load_gold, score_one, summarize

POOL = 40
CHECKPOINT = RESULTS / "experiments-checkpoint.json"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
# rerank: None 또는 (다시 정렬할 개수, 입력 최대 토큰)
VARIANTS = {
    "A": {"table": "chunks", "rerank": None},
    "B": {"table": "no_header", "rerank": None},
    "C": {"table": "table_header", "rerank": None},
    "A+R": {"table": "chunks", "rerank": (40, 1024)},
    "A+R20": {"table": "chunks", "rerank": (20, 512)},
    "C+R": {"table": "table_header", "rerank": (40, 1024)},
}


@lru_cache
def _reranker(max_length: int):
    import torch
    from sentence_transformers import CrossEncoder

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    return CrossEncoder(RERANK_MODEL, device=device, max_length=max_length)


@lru_cache
def _lookup():
    with session_scope() as s:
        names = dict(s.execute(select(Company.corp_name, Company.corp_code)).all())
    return build_lookup(names)


def retrieve(question: str, table: str) -> list[tuple[str, str]]:
    """(접수번호, 청크 텍스트) 목록, 거리순 POOL개."""
    from app.rag.embedder import embed_query

    vec = embed_query(question)
    codes = find_companies(question, _lookup())
    model = Chunk if table == "chunks" else ChunkExp
    dist = model.embedding.cosine_distance(vec)
    stmt = select(model.rcept_no, model.text)
    if model is ChunkExp:
        stmt = stmt.where(ChunkExp.variant == table)
    if codes:
        stmt = stmt.where(model.corp_code.in_(codes))
    with session_scope() as s:
        return list(s.execute(stmt.order_by(dist).limit(POOL)).all())


def rerank(
    question: str, hits: list[tuple[str, str]], top: int, max_length: int
) -> list[tuple[str, str]]:
    """상위 top개만 재순위 모델로 다시 정렬하고, 나머지는 원래 순서로 뒤에 둔다."""
    head, tail = hits[:top], hits[top:]
    if not head:
        return hits
    scores = _reranker(max_length).predict([(question, t) for _, t in head], batch_size=16)
    order = sorted(range(len(head)), key=lambda i: float(scores[i]), reverse=True)
    return [head[i] for i in order] + tail


def ranked_filings(hits: list[tuple[str, str]]) -> list[str]:
    return list(dict.fromkeys(r for r, _ in hits))


def variant_available(table: str) -> bool:
    if table == "chunks":
        return True
    with session_scope() as s:
        return s.scalar(select(ChunkExp.id).where(ChunkExp.variant == table).limit(1)) is not None


def _load_checkpoint(limit: int | None) -> dict:
    if not CHECKPOINT.exists():
        return {}
    data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return data.get("results", {}) if data.get("limit") == limit else {}


def _save_checkpoint(results: dict, limit: int | None) -> None:
    RESULTS.mkdir(exist_ok=True)
    CHECKPOINT.write_text(
        json.dumps({"limit": limit, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run(variants: list[str], limit: int | None, fresh: bool = False) -> dict:
    items = [q for q in load_gold() if q["gold"]]
    if limit:
        items = items[:limit]
    out: dict[str, dict] = {} if fresh else _load_checkpoint(limit)
    for name in variants:
        if name in out:
            print(f"[{name}] 이미 끝남 (체크포인트) → 건너뜀")
            continue
        cfg = VARIANTS[name]
        if not variant_available(cfg["table"]):
            print(f"[{name}] 건너뜀: 실험 인덱스 '{cfg['table']}'가 없습니다")
            continue
        rows, times = [], []
        for q in items:
            t = time.perf_counter()
            hits = retrieve(q["question"], cfg["table"])
            if cfg["rerank"]:
                hits = rerank(q["question"], hits, *cfg["rerank"])
            times.append(time.perf_counter() - t)
            rows.append(
                {"id": q["id"], "type": q["type"], **score_one(ranked_filings(hits), q["gold"])}
            )
        summary = summarize(rows)
        summary["all"]["sec_per_query"] = statistics.median(times)
        out[name] = {"summary": summary, "rows": rows}
        _save_checkpoint(out, limit)  # 버전 하나 끝날 때마다 저장
        s = summary["all"]
        print(
            f"[{name}] hit@1 {s['hit@1']:.2f}  hit@3 {s['hit@3']:.2f}  MRR {s['mrr']:.2f}  "
            f"질문당 {s['sec_per_query']:.2f}초"
        )
    return out


def print_comparison(results: dict) -> None:
    print("\n| 버전 | hit@1 | hit@3 | hit@5 | MRR | 함정 hit@1 | 질문당 시간 |")
    print("|---|---|---|---|---|---|---|")
    for name, r in results.items():
        a, trap = r["summary"]["all"], r["summary"].get("trap", {})
        print(
            f"| {name} | {a['hit@1']:.2f} | {a['hit@3']:.2f} | {a['hit@5']:.2f} | {a['mrr']:.2f} | "
            f"{trap.get('hit@1', 0):.2f} | {a['sec_per_query']:.2f}s |"
        )


def main() -> None:
    p = argparse.ArgumentParser(description="검색 실험 비교 (dev)")
    p.add_argument("--variants", nargs="*", default=["A", "B", "C", "A+R20", "A+R", "C+R"])
    p.add_argument("--limit", type=int)
    p.add_argument("--fresh", action="store_true", help="체크포인트 무시하고 처음부터")
    args = p.parse_args()
    results = run(args.variants, args.limit, args.fresh)
    results = {k: results[k] for k in args.variants if k in results}  # 요청한 순서대로
    print_comparison(results)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{datetime.now():%Y%m%d-%H%M}_dev_experiments.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out.relative_to(EVAL_DIR.parent)}")


if __name__ == "__main__":
    main()
