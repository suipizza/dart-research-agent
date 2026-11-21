# API 서버 (FastAPI + LangGraph 에이전트 + 로컬 임베딩·재순위 모델)
#
#   docker compose up -d --build
#
# - PyTorch는 CPU 휠 (pyproject의 [tool.uv.sources]). CUDA 휠보다 수 GB 작다.
# - 모델(bge-m3, bge-reranker-v2-m3, 약 4.5GB)은 이미지에 넣지 않고 /models 볼륨에 받는다.
#   처음 시작할 때 한 번 내려받고, 이후에는 볼륨에서 바로 읽는다.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/models \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv

WORKDIR /app

# 의존성만 먼저 설치해 코드가 바뀌어도 이 층은 캐시를 쓴다. (dev 그룹 제외, embed 포함)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY app ./app

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /models \
    && chown appuser:appuser /models
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# --root-path /api: 리버스 프록시(Caddy)가 /api 접두어를 떼고 넘긴다. Swagger 문서 경로가 맞도록 알려 준다.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--root-path", "/api", "--proxy-headers", "--forwarded-allow-ips", "*"]
