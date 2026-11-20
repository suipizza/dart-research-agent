"""기본 RAG 답변: 검색 상위 청크만 근거로 Claude가 답한다.

일부러 단순하게 둔다(날짜 필터·검증·재검색 없음). 4단계 에이전트의 개선 효과를
이 기준선과 비교하기 위해서다.

    uv run python -m app.rag.answer "삼성전자 2026년 8월 자사주 취득 금액" --model haiku
"""

import argparse
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.llm import HAIKU, MODELS, Usage, call_json
from app.rag.search import Hit, search

TODAY = "2026-11-19"  # 데이터 수집 기준일. 평가가 날짜에 따라 흔들리지 않도록 고정한다.
DEFAULT_TOP_K = 5

SYSTEM_PROMPT = f"""당신은 한국 상장사 공시(DART)를 근거로 답하는 리서치 보조입니다.
오늘은 {TODAY}입니다.

규칙
1. 아래 [공시 발췌]에 있는 내용만 근거로 답합니다. 배경지식으로 숫자나 사실을 보태지 않습니다.
2. 숫자는 발췌에 적힌 값을 그대로 쓰고 단위를 함께 적습니다. 읽기 쉽게 환산할 때는 원래 값도 같이 적습니다.
   (예: 14,999,999,992,000원(약 15조원))
3. 답의 각 사실 뒤에 근거 발췌 번호를 [1], [2]처럼 붙이고, citations에 사용한 번호를 모두 넣습니다.
4. 발췌로 답할 수 없으면 추측하지 말고 unanswerable을 true로 하고, answer에 무엇을 확인할 수 없는지 적습니다.
5. 주가 전망, 매수·매도 추천 같은 투자 판단은 하지 않습니다. 이런 질문은 unanswerable을 true로 하고 이유를 적습니다.
6. 한국어로 간결하게 답합니다."""


class AnswerOut(BaseModel):
    answer: str = Field(description="사용자에게 보여줄 답변 (근거 번호 포함)")
    citations: list[int] = Field(description="답변에 사용한 발췌 번호 목록")
    unanswerable: bool = Field(description="발췌로 답할 수 없거나 답하면 안 되는 질문이면 true")


@dataclass
class Answer:
    question: str
    answer: str
    unanswerable: bool
    cited_rcept_nos: list[str]
    hits: list[Hit]
    model: str
    usage: Usage = field(default_factory=Usage)

    @property
    def context_rcept_nos(self) -> list[str]:
        return [h.rcept_no for h in self.hits]


def format_context(hits: list[Hit]) -> str:
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(
            f"[{i}] {h.corp_name} | {h.rcept_dt} | {h.report_nm} | 접수번호 {h.rcept_no}\n"
            f"{h.text.split(chr(10), 1)[-1]}"  # 청크 머리말 줄은 위 제목줄과 중복이라 뺀다
        )
    return "\n\n".join(blocks)


def answer_question(
    question: str, model: str = HAIKU, top_k: int = DEFAULT_TOP_K, effort: str = "medium"
) -> Answer:
    hits, _ = search(question, top_k=top_k)
    usage = Usage()
    user = f"[공시 발췌]\n{format_context(hits)}\n\n[질문]\n{question}"
    out = call_json(
        model=model, system=SYSTEM_PROMPT, user=user, schema=AnswerOut, effort=effort, usage=usage
    )
    cited = [hits[i - 1].rcept_no for i in out.citations if 1 <= i <= len(hits)]
    return Answer(
        question=question,
        answer=out.answer,
        unanswerable=out.unanswerable,
        cited_rcept_nos=list(dict.fromkeys(cited)),
        hits=hits,
        model=model,
        usage=usage,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="기본 RAG 답변")
    p.add_argument("question")
    p.add_argument("--model", choices=list(MODELS), default="haiku")
    p.add_argument("-k", type=int, default=DEFAULT_TOP_K)
    args = p.parse_args()
    a = answer_question(args.question, model=MODELS[args.model], top_k=args.k)
    print(a.answer)
    print("\n출처:")
    for r in a.cited_rcept_nos:
        print(f"  https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r}")
    print(
        f"\n[{a.model}] 토큰 {a.usage.input_tokens}+{a.usage.output_tokens}, ${a.usage.cost_usd:.4f}"
    )


if __name__ == "__main__":
    main()
