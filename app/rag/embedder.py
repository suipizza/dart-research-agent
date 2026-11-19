"""bge-m3 임베딩 (로컬 실행).

sentence-transformers / PyTorch는 무거워서(embed 그룹) 실제로 쓸 때만 import한다.
그래서 CI처럼 embed 그룹이 없는 환경에서도 이 모듈을 import하는 다른 코드는 문제없다.
"""

from functools import lru_cache

MODEL_NAME = "BAAI/bge-m3"


def _device() -> str:
    import torch

    if torch.backends.mps.is_available():  # 애플 실리콘 GPU
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME, device=_device())


def embed(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """정규화된 벡터를 돌려준다(길이 1). 그래서 코사인 거리 = 1 - 내적."""
    vectors = _model().encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 100,
    )
    return vectors.tolist()


def embed_query(query: str) -> list[float]:
    return embed([query])[0]
