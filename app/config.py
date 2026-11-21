"""애플리케이션 설정.

모든 설정은 이 모듈의 `get_settings()`로만 읽는다.
로컬에서는 `.env`, CI·서버에서는 환경변수에서 같은 코드로 값을 가져온다.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env에 이 클래스가 모르는 값(POSTGRES_USER 등)이 있어도 무시
    )

    # 필수값: 없으면 시작 시점에 ValidationError로 바로 실패한다.
    # SecretStr이라 로그나 repr에 찍혀도 '**********'로 가려진다.
    dart_api_key: SecretStr

    # LLM 키는 답변 생성·채점에만 필요하다. CI처럼 키가 없는 환경에서도 앱이 뜨도록 선택값으로 둔다.
    anthropic_api_key: SecretStr | None = None

    # Langfuse 관측. 키가 없으면 추적 없이 동작한다.
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    database_url: str = "postgresql+psycopg://dart:dart@localhost:5432/dart"
    redis_url: str = "redis://localhost:6379/0"

    # 공개 데모 비용 보호 (캐시에서 나간 답은 세지 않는다)
    rate_limit_per_ip_daily: int = 20
    rate_limit_global_daily: int = 500
    cache_ttl_seconds: int = 7 * 24 * 3600
    # 서버 시작 시 임베딩 모델을 미리 불러올지 (첫 질문 지연 방지)
    preload_embedder: bool = True
    # 재순위(bge-reranker-v2-m3): 검색 후보 rerank_pool개를 다시 정렬한다. 6단계 실험 결과 적용.
    rerank: bool = True
    rerank_pool: int = 40
    dart_base_url: str = "https://opendart.fss.or.kr/api"


@lru_cache
def get_settings() -> Settings:
    """설정을 한 번만 읽고 재사용한다. 테스트에서는 cache_clear()로 초기화할 수 있다."""
    return Settings()
