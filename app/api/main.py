"""FastAPI 서버.

    uv run uvicorn app.api.main:app --reload       # http://localhost:8000/docs (Swagger)

POST /ask        질문 → 에이전트 실행. stream=true면 SSE(Server-Sent Events)로 진행 단계와 결과를 보낸다.
GET  /companies  수집 대상 기업 목록
GET  /health     서버·DB·Redis 상태
"""

import json
import logging
import threading
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.api import guard
from app.config import get_settings
from app.db import session_scope
from app.llm import EXPERIMENT_MODEL
from app.models import Company

log = logging.getLogger("api")

SERVING_MODEL = EXPERIMENT_MODEL  # 데모 답변 모델. 바꾸면 캐시 키도 달라진다.


def run_agent_stream(question: str, model: str):
    """에이전트 실행 (테스트에서 가짜로 바꿀 수 있게 한 겹 감싼다)."""
    from app.agent.graph import run_agent_stream as _run

    yield from _run(question, model)


def list_companies() -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(Company.corp_name, Company.stock_code, Company.corp_code).order_by(
                Company.corp_name
            )
        ).all()
    return [{"corp_name": n, "stock_code": sc, "corp_code": cc} for n, sc, cc in rows]


def db_ok() -> bool:
    try:
        with session_scope() as s:
            s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _warm_up() -> None:
    try:
        from app.rag.embedder import embed_query

        embed_query("warm up")
        log.info("embedder ready")
        if get_settings().rerank:
            from app.rag import rerank

            rerank.warm_up()
            log.info("reranker ready")
    except Exception as e:  # 실패해도 첫 질문에서 다시 불러온다
        log.warning("embedder warm-up failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # 요청 URL(키 포함) 로그 방지
    if get_settings().preload_embedder:
        # 임베딩·재순위 모델을 미리 불러 둔다. 안 하면 첫 질문이 약 20초 더 걸린다.
        # 백그라운드에서 해서 서버는 바로 뜬다(/health는 그동안에도 응답).
        threading.Thread(target=_warm_up, name="embedder-warmup", daemon=True).start()
    yield
    from app import obs

    obs.flush()  # 종료 전에 남은 추적을 Langfuse로 보낸다


app = FastAPI(
    title="DART 공시 리서치 에이전트",
    description="상장사 공시를 근거로 답하고 답변 속 숫자를 원문과 대조하는 LangGraph 에이전트 API",
    version="0.5.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],  # Next.js 개발 서버. 배포 시 도메인 추가
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── 스키마 ───────────────────────────────────────────────────────


class AskRequest(BaseModel):
    question: str = Field(
        min_length=2, max_length=300, examples=["삼성전자 2026년 3분기 영업이익은?"]
    )
    stream: bool = Field(default=True, description="true면 SSE로 진행 단계를 보낸다")


class Source(BaseModel):
    rcept_no: str
    title: str
    url: str


class VerifiedNumber(BaseModel):
    value: str = Field(description="답변에 쓰인 숫자 표현")
    line: str = Field(description="그 숫자가 확인된 공시 원문의 줄")
    rcept_no: str
    title: str


class AskResponse(BaseModel):
    question: str
    answer: str
    unanswerable: bool
    sources: list[Source]
    verified: list[VerifiedNumber] = []
    model: str
    cached: bool
    steps: list[str] = []
    answered_at: str


# ── 라우트 ───────────────────────────────────────────────────────


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "db": db_ok(), "redis": guard.redis_ok()}


@app.get("/companies")
def companies() -> list[dict]:
    return list_companies()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:  # 리버스 프록시(배포 환경) 뒤에서는 실제 클라이언트 IP가 여기에 온다
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _payload(question: str, result, steps: list[str], cached: bool) -> dict:
    return AskResponse(
        question=question,
        answer=result.answer,
        unanswerable=result.unanswerable,
        sources=[Source(**s) for s in result.sources],
        verified=[VerifiedNumber(**v) for v in getattr(result, "verified", [])],
        model=result.model,
        cached=cached,
        steps=steps,
        answered_at=datetime.now().isoformat(timespec="seconds"),
    ).model_dump()


def _run_and_cache(question: str) -> Iterator[tuple[str, dict]]:
    """에이전트를 돌리며 ("step", {...})와 마지막 ("result", payload)를 내보내고 결과를 캐시에 저장."""
    steps: list[str] = []
    for kind, data in run_agent_stream(question, SERVING_MODEL):
        if kind == "step":
            steps.append(data["label"])
            yield "step", {"label": data["label"], "node": data["node"]}
        else:
            payload = _payload(question, data, steps, cached=False)
            guard.set_cached(question, SERVING_MODEL, payload)
            yield "result", payload


@app.post(
    "/ask",
    response_model=AskResponse,
    responses={429: {"description": "하루 질문 한도 초과"}},
    summary="공시 질문하기",
)
def ask(req: AskRequest, request: Request):
    question = req.question.strip()

    cached = guard.get_cached(question, SERVING_MODEL)
    if cached:
        cached["cached"] = True
        if not req.stream:
            return cached

        def replay() -> Iterator[str]:
            yield _sse("step", {"label": "저장된 답변", "node": "cache"})
            yield _sse("result", cached)
            yield _sse("done", {})

        return StreamingResponse(replay(), media_type="text/event-stream")

    try:
        guard.check_rate_limit(_client_ip(request))
    except guard.RateLimited as e:
        msg = (
            "오늘 질문 한도를 넘었습니다."
            if e.scope == "ip"
            else "오늘 데모 전체 한도를 넘었습니다."
        )
        return JSONResponse(status_code=429, content={"detail": f"{msg} 내일 다시 시도해 주세요."})

    if not req.stream:
        result = None
        for kind, data in _run_and_cache(question):
            if kind == "result":
                result = data
        return result

    def events() -> Iterator[str]:
        try:
            for kind, data in _run_and_cache(question):
                yield _sse(kind, data)
        except (
            Exception
        ) as e:  # 스트림이 시작된 뒤에는 HTTP 상태코드를 바꿀 수 없어 이벤트로 알린다
            log.exception("agent failed")
            yield _sse("error", {"detail": f"답변 생성 중 오류가 발생했습니다: {type(e).__name__}"})
        yield _sse("done", {})

    return StreamingResponse(events(), media_type="text/event-stream")
