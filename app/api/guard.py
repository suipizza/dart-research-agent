"""Redis 기반 응답 캐시와 호출 제한 (공개 데모 비용 보호).

- 캐시: 같은 질문(공백 정리 후)·같은 모델·같은 에이전트 버전이면 저장된 답을 돌려준다 → API 비용 0원.
- 호출 제한: IP당 하루 N회, 서비스 전체 하루 M회. 캐시에서 나간 답은 세지 않는다.
- Redis가 꺼져 있으면 캐시·제한 없이 동작한다(fail-open). 로컬 개발 편의를 위한 선택이며,
  운영에서는 Redis를 compose로 함께 띄운다.
"""

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from functools import lru_cache

import redis

from app.config import get_settings

log = logging.getLogger("api.guard")

AGENT_VERSION = "v2.1"  # 에이전트 로직이 바뀌면 올려서 예전 캐시를 무효화한다


@lru_cache
def client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def _normalize(question: str) -> str:
    return re.sub(r"\s+", " ", question).strip().rstrip("?？").lower()


def cache_key(question: str, model: str) -> str:
    raw = f"{AGENT_VERSION}|{model}|{_normalize(question)}"
    return "answer:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def get_cached(question: str, model: str, r: redis.Redis | None = None) -> dict | None:
    try:
        raw = (r or client()).get(cache_key(question, model))
    except redis.RedisError as e:
        log.warning("cache read skipped: %s", e)
        return None
    return json.loads(raw) if raw else None


def set_cached(question: str, model: str, payload: dict, r: redis.Redis | None = None) -> None:
    try:
        (r or client()).set(
            cache_key(question, model),
            json.dumps(payload, ensure_ascii=False),
            ex=get_settings().cache_ttl_seconds,
        )
    except redis.RedisError as e:
        log.warning("cache write skipped: %s", e)


class RateLimited(Exception):
    def __init__(self, scope: str, limit: int):
        super().__init__(f"{scope} daily limit {limit} exceeded")
        self.scope = scope
        self.limit = limit


def check_rate_limit(ip: str, r: redis.Redis | None = None) -> None:
    """한도를 넘으면 RateLimited. 넘지 않으면 카운터를 1 올린다."""
    s = get_settings()
    today = datetime.now(UTC).strftime("%Y%m%d")
    keys = [(f"rl:ip:{ip}:{today}", s.rate_limit_per_ip_daily, "ip"),
            (f"rl:global:{today}", s.rate_limit_global_daily, "global")]  # fmt: skip
    try:
        conn = r or client()
        counts = [int(conn.get(k) or 0) for k, _, _ in keys]
        for (_, limit, scope), count in zip(keys, counts, strict=True):
            if count >= limit:
                raise RateLimited(scope, limit)
        pipe = conn.pipeline()
        for k, _, _ in keys:
            pipe.incr(k)
            pipe.expire(k, 2 * 24 * 3600)
        pipe.execute()
    except redis.RedisError as e:
        log.warning("rate limit skipped: %s", e)


def redis_ok(r: redis.Redis | None = None) -> bool:
    try:
        return bool((r or client()).ping())
    except redis.RedisError:
        return False
