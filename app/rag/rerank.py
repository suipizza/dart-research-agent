"""재순위 (cross-encoder): 벡터 검색 후보를 질문과 함께 읽어 다시 정렬한다.

벡터 검색은 질문과 청크를 따로 임베딩해 거리만 비교하므로 빠르지만 거칠다.
재순위 모델은 (질문, 청크)를 한 번에 읽고 관련도를 매겨 순서를 더 정확하게 맞춘다. 대신 후보마다
모델을 돌려야 해서 느리다.

6단계 실험(dev 53문항, 검색만): 1위 정답 0.64 → 0.70, MRR 0.75 → 0.78. 맥 GPU에서 후보 40개 기준
질문당 약 25초가 늘었다. 이 프로젝트는 리서치 도구라 속도보다 정확도를 우선해 적용했다.
실서비스라면 후보 수 축소(20개면 약 9초), GPU 서버, 작은 재순위 모델을 검토할 것.
"""

import logging
from functools import lru_cache

from app.rag.search import Hit

log = logging.getLogger("rerank")

MODEL = "BAAI/bge-reranker-v2-m3"
MAX_LENGTH = 1024  # (질문 + 청크) 입력 최대 토큰. 청크가 약 1,000자라 대부분 잘리지 않는다.


@lru_cache
def _model():
    import torch
    from sentence_transformers import CrossEncoder

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    log.info("loading %s on %s", MODEL, device)
    return CrossEncoder(MODEL, device=device, max_length=MAX_LENGTH)


def rerank(query: str, hits: list[Hit]) -> list[Hit]:
    """후보 전체를 재순위 점수 높은 순으로 돌려준다."""
    if len(hits) < 2:
        return hits
    scores = _model().predict([(query, h.text) for h in hits], batch_size=16)
    order = sorted(range(len(hits)), key=lambda i: float(scores[i]), reverse=True)
    return [hits[i] for i in order]


def warm_up() -> None:
    _model()
