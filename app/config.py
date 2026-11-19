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

    database_url: str = "postgresql+psycopg://dart:dart@localhost:5432/dart"
    dart_base_url: str = "https://opendart.fss.or.kr/api"


@lru_cache
def get_settings() -> Settings:
    """설정을 한 번만 읽고 재사용한다. 테스트에서는 cache_clear()로 초기화할 수 있다."""
    return Settings()
