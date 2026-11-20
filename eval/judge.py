"""답변 채점.

1) 코드 채점 (무료, 결정적)
   - key_fact 포함률: 반드시 들어갈 사실이 답에 있는가. 숫자는 쉼표·공백을 무시하고 숫자열로 비교.
   - 출처 적중: 답이 인용한 공시 중 정답 공시가 있는가.
2) LLM 채점 (JUDGE_MODEL 고정)
   - 정답 여부(correct/partial/wrong), 환각, 거절 여부.
   - 채점 기준 메모(note)를 함께 넣어 "약 500억도 인정" 같은 합의를 반영한다.

채점 모델은 프로젝트 내내 바꾸지 않는다. 바꾸면 점수의 기준 자체가 바뀌기 때문이다.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.llm import SONNET, Usage, call_json

JUDGE_MODEL = SONNET

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_DATE = re.compile(r"(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})\s*일?")
_MMDD = re.compile(r"^(\d{2})-(\d{2})$")
_MD = re.compile(r"(?<!\d)(\d{1,2})\s*(?:월\s*|[-/])(\d{1,2})(?:\s*일|(?!\d))")


def _dates(s: str) -> set[str]:
    """'2026-08-28', '2026년 08월 28일', '2026.8.28' → {'20260828'}"""
    return {f"{y}{int(m):02d}{int(d):02d}" for y, m, d in _DATE.findall(s)}


def _digits(s: str) -> str:
    return s.replace(",", "")


def key_fact_hits(answer: str, key_facts: list[str]) -> list[bool]:
    """각 key_fact가 답에 들어 있는지. 숫자형은 숫자열 일치, 그 외는 부분 문자열(대소문자 무시)."""
    nums_in_answer = {_digits(m) for m in _NUM.findall(answer)}
    dates_in_answer = _dates(answer)
    compact = re.sub(r"\s+", "", answer).lower()
    out = []
    for fact in key_facts:
        if _dates(fact):  # 날짜는 표기 형식과 무관하게 비교
            out.append(_dates(fact) <= dates_in_answer)
        elif m := _MMDD.match(fact.strip()):  # '04-22' 같은 월-일
            mm, dd = m.groups()
            month_days = {d[4:] for d in dates_in_answer} | {
                f"{int(a):02d}{int(b):02d}" for a, b in _MD.findall(answer)
            }
            out.append(mm + dd in month_days)
        elif _NUM.fullmatch(fact.strip()):
            out.append(_digits(fact.strip()) in nums_in_answer)
        else:
            out.append(re.sub(r"\s+", "", fact).lower() in compact)
    return out


def citation_hit(cited: list[str], gold: list[str]) -> bool | None:
    if not gold:
        return None
    return bool(set(cited) & set(gold))


class Verdict(BaseModel):
    correctness: Literal["correct", "partial", "wrong"] = Field(
        description="기대 답변 대비 정답 여부. 핵심 사실이 모두 맞으면 correct, 일부만 맞으면 partial"
    )
    hallucination: bool = Field(description="제공된 공시 발췌에 없는 사실·숫자를 지어냈으면 true")
    refused: bool = Field(
        description="질문의 핵심 요구를 '확인 불가'·'답할 수 없음'으로 거절했으면 true (부가 정보가 있어도)"
    )
    reason: str = Field(description="판단 이유 한두 문장")


JUDGE_SYSTEM = """당신은 공시 리서치 답변을 채점하는 엄격한 채점자입니다.
기대 답변과 채점 기준을 기준으로 모델 답변을 평가합니다.

- correctness: 기대 답변의 핵심 사실(숫자, 날짜, 주체)이 모두 맞으면 correct, 일부만 맞거나 핵심이 빠지면 partial,
  핵심이 틀리거나 엉뚱한 공시를 근거로 답하면 wrong. 기대 답변이 '거절/확인 불가'인데 모델이 거절했으면 correct.
  숫자는 단위 환산이 맞으면 같은 값으로 본다(예: 83,333,818백만원 = 83조 3,338억원).
  기대 답변에 없는 부가 정보는 사실이면 감점하지 않는다.
- hallucination: [공시 발췌]에 없는 숫자나 사실을 답에 넣었으면 true. 발췌를 기준으로 판단한다.
- refused: 질문의 핵심 요구(질문한 값·판단)에 답하지 않고 '확인 불가'나 '답할 수 없음'으로 응답했으면 true.
  거절하면서 관련 공시 사실을 덧붙였더라도 핵심 요구를 거절했다면 true다.
- 채점 기준 메모가 있으면 그 기준을 우선 적용한다.

공통 판정 규칙 (사람이 정의, 채점기 검증 15문항에서 확인)
1. 질문이 묻지 않은 정보(기대 답변의 참고 정보)가 빠진 것은 감점하지 않는다. 질문이 물은 것을 맞혔으면 correct.
2. 숫자는 맞아도 단위가 없거나 '단위 확인 불가'라고 하면 partial. 금융 숫자는 단위가 없으면 쓸 수 없다.
3. 답의 결론이 틀린 방향이면(예/아니오 질문에 반대로 시작 등) 뒤에서 바로잡아도 partial.
4. 틀린 정보 없이 핵심 숫자를 '확인 불가'로 빠뜨렸으면 partial(wrong 아님). 틀린 숫자를 말했으면 wrong."""


def llm_judge(
    question: str,
    expected: str,
    note: str | None,
    answer: str,
    context: str,
    usage: Usage | None = None,
) -> Verdict:
    user = (
        f"[질문]\n{question}\n\n[기대 답변]\n{expected}\n\n"
        f"[채점 기준 메모]\n{note or '없음'}\n\n[모델 답변]\n{answer}\n\n[공시 발췌]\n{context}"
    )
    return call_json(
        model=JUDGE_MODEL,
        system=JUDGE_SYSTEM,
        user=user,
        schema=Verdict,
        effort="low",
        max_tokens=2000,
        usage=usage,
    )
