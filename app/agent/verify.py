"""④ 숫자 검증 노드: 답변의 금액이 근거(공시 발췌·재무 데이터)에 실제로 있는지 코드로 대조한다.

LLM에게 "맞는지 확인해 줘"라고 묻지 않고 결정적인 규칙으로 확인한다. 같은 답이면 항상 같은 결과가 나온다.

- 쉼표가 들어간 큰 숫자(예: 14,999,999,992,000)는 근거에 같은 숫자열이 있어야 한다.
- 조·억·만 단위 표현(예: 약 15조원, 1조 1,672억원)은 근거의 어떤 숫자에 표 단위(원·천원·백만원·억원·조원)를
  곱한 값과 0.5% 안에서 맞아야 한다.
- 퍼센트, 날짜, 1만 미만의 작은 수(1주당 배당금 등은 근거에 그대로 있음)는 검사 대상에서 뺀다.
  증감률처럼 답변에서 계산한 값까지 막으면 정상 답변을 오류로 잡기 쉽기 때문이다.
"""

import re
from dataclasses import dataclass

_DATE_LIKE = re.compile(r"\d{4}\s*[-./년]\s*\d{1,2}\s*[-./월]\s*\d{1,2}")
_PERCENT = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?\s*%")
_COMMA_NUM = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?![\d,])")
_KR_AMOUNT = re.compile(
    r"(?:(?P<jo>\d[\d,]*(?:\.\d+)?)\s*조)?\s*(?:(?P<eok>\d[\d,]*(?:\.\d+)?)\s*억)?\s*(?:(?P<man>\d[\d,]*)\s*만)?\s*원"
)
_ANY_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
UNITS = (1, 1_000, 1_000_000, 100_000_000, 1_000_000_000_000)  # 원, 천원, 백만원, 억원, 조원
MIN_CHECK = 10_000  # 이보다 작은 숫자는 검사하지 않는다


@dataclass
class VerifyResult:
    checked: int
    unverified: list[str]

    @property
    def ok(self) -> bool:
        return not self.unverified


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _strip_noise(text: str) -> str:
    return _PERCENT.sub(" ", _DATE_LIKE.sub(" ", text))


def evidence_numbers(evidence_text: str) -> tuple[set[str], list[float]]:
    """근거의 (쉼표 제거 숫자열 집합, 숫자 값 목록)"""
    raw = _ANY_NUM.findall(evidence_text)
    return {r.replace(",", "") for r in raw}, [_num(r) for r in raw]


def _close_to_evidence(value: float, values: list[float], tol: float = 0.005) -> bool:
    for v in values:
        for unit in UNITS:
            target = v * unit
            if target and abs(value - target) / target <= tol:
                return True
    return False


def verify_numbers(answer: str, evidence_text: str) -> VerifyResult:
    digits, values = evidence_numbers(evidence_text)
    text = _strip_noise(answer)
    unverified: list[str] = []
    checked = 0

    # 1) 조·억·만 단위 금액 (먼저 처리하고 지워서 2)에서 중복으로 잡지 않게 한다)
    for m in list(_KR_AMOUNT.finditer(text)):
        if not (m.group("jo") or m.group("eok") or m.group("man")):
            continue
        value = (
            _num(m.group("jo") or "0") * 1e12
            + _num(m.group("eok") or "0") * 1e8
            + _num(m.group("man") or "0") * 1e4
        )
        if value < MIN_CHECK:
            continue
        checked += 1
        if not _close_to_evidence(value, values):
            unverified.append(m.group(0).strip())
    text = _KR_AMOUNT.sub(lambda m: " " if (m.group("jo") or m.group("eok")) else m.group(0), text)

    # 2) 쉼표가 들어간 큰 숫자: 근거에 같은 숫자열이 있어야 한다
    for raw in _COMMA_NUM.findall(text):
        if _num(raw) < MIN_CHECK:
            continue
        checked += 1
        if raw.replace(",", "") not in digits:
            unverified.append(raw)

    return VerifyResult(checked=checked, unverified=list(dict.fromkeys(unverified)))
