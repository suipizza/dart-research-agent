"""채점기 검증: 사람이 직접 채점한 결과와 LLM 채점 결과가 얼마나 일치하는지 본다.

    uv run python -m eval.manual_sheet make <결과파일.json>    # 블라인드 채점지 생성
    uv run python -m eval.manual_sheet compare                 # 사람 채점 vs LLM 채점 비교

채점지(eval/manual_grading.md)에는 LLM 채점 결과를 보여주지 않는다(사람 판단이 끌려가지 않게).
각 문항의 '내 채점:' 뒤에 정답 / 부분 / 오답 중 하나를 적는다.
"""

import json
import re
import sys
from pathlib import Path

from eval.retrieval import EVAL_DIR

SHEET = EVAL_DIR / "manual_grading.md"
KEY = EVAL_DIR / "manual_grading_key.json"  # LLM 채점 결과 (비교용, 채점 끝날 때까지 열지 않기)
LABELS = {"정답": "correct", "부분": "partial", "오답": "wrong"}


def link(r: str) -> str:
    return f"[{r}](https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r})"


def make(result_path: str) -> None:
    rows = json.loads(Path(result_path).read_text(encoding="utf-8"))["rows"]
    lines = [
        f"# 채점기 검증용 직접 채점 ({len(rows)}문항)",
        "",
        "> 각 문항의 **내 채점:** 뒤에 `정답` / `부분` / `오답` 중 하나를 적어주세요.",
        "> 기준: 핵심 사실(숫자·날짜·주체)이 모두 맞으면 정답,",
        "> 일부만 맞거나 핵심 결론이 흐리면 부분, 핵심이 틀리거나 답을 못 했으면 오답.",
        "> 기대 답변이 '거절'이면, 모델이 거절했을 때 정답입니다.",
        "",
    ]
    for r in rows:
        cited = ", ".join(link(c) for c in r["cited"]) or "없음"
        lines += [
            f"## {r['id']}. {r['question']}",
            f"- **기대 답변**: {r['expected']}",
            f"- **모델 답변**: {r['answer']}",
            f"- **모델이 인용한 공시**: {cited}",
            "- **내 채점:** ",
            "",
        ]
    SHEET.write_text("\n".join(lines), encoding="utf-8")
    KEY.write_text(
        json.dumps({r["id"]: r["correctness"] for r in rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"채점지: {SHEET}\n(LLM 채점 결과는 {KEY.name}에 따로 저장)")


def compare() -> None:
    text = SHEET.read_text(encoding="utf-8")
    human: dict[str, str] = {}
    for block in text.split("\n## ")[1:]:
        qid = block.split(".", 1)[0].strip()
        m = re.search(r"\*\*내 채점:\*\*\s*(정답|부분|오답)", block)
        if m:
            human[qid] = LABELS[m.group(1)]
    llm = json.loads(KEY.read_text(encoding="utf-8"))
    both = [q for q in llm if q in human]
    if not both:
        print("채점된 문항이 없습니다.")
        return
    agree = [q for q in both if human[q] == llm[q]]
    print(f"일치율: {len(agree)}/{len(both)} = {len(agree) / len(both):.0%}")
    for q in both:
        mark = "✓" if human[q] == llm[q] else "✗"
        print(f"  {mark} {q}: 사람={human[q]:8} LLM={llm[q]}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["make"]:
        make(sys.argv[2])
    elif sys.argv[1:2] == ["compare"]:
        compare()
    else:
        print(__doc__)
