"""gold.yaml → 사람이 검토하기 쉬운 마크다운 (원문 링크 포함).

uv run python -m eval.review_sheet          # dev → eval/gold_review.md
uv run python -m eval.review_sheet test     # test → eval/test_review.md
"""

import sys

from eval.retrieval import EVAL_DIR, SETS, load_gold

LABELS = {
    "fact": "사실 조회",
    "financial": "재무 수치",
    "list": "목록",
    "compare": "비교",
    "summary": "요약",
    "trap": "함정",
    "refuse": "거절",
}


def link(rcept_no: str) -> str:
    return f"[{rcept_no}](https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no})"


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "dev"
    items = load_gold(SETS[which])
    lines = [
        f"# 골드 질문 검토표 ({which} 세트, {len(items)}문항)",
        "",
        f"> `{SETS[which].name}`에서 자동 생성. 수정은 yaml에 하고 다시 생성한다.",
        "> 검토 포인트: 질문이 자연스러운가 / 정답이 원문과 맞는가 / 근거 공시가 맞는가",
        "",
    ]
    for t, label in LABELS.items():
        group = [q for q in items if q["type"] == t]
        if not group:
            continue
        lines += [f"## {label} ({len(group)})", ""]
        for q in group:
            lines.append(f"### {q['id']}. {q['question']}")
            lines.append(f"- **정답**: {q['answer']}")
            lines.append(f"- **경로**: `{q['route']}`")
            if q["gold"]:
                lines.append("- **근거 공시**: " + ", ".join(link(r) for r in q["gold"]))
            if q.get("note"):
                lines.append(f"- **메모**: {q['note']}")
            lines.append("- [ ] 확인")
            lines.append("")
    out = EVAL_DIR / ("gold_review.md" if which == "dev" else "test_review.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
