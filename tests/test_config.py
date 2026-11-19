import pytest
from pydantic import ValidationError

from app.config import Settings


def test_loads_key_from_env(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key-123")
    settings = Settings(_env_file=None)  # 실제 .env는 읽지 않는다
    assert settings.dart_api_key.get_secret_value() == "test-key-123"


def test_key_is_masked_in_repr(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key-123")
    settings = Settings(_env_file=None)
    assert "test-key-123" not in repr(settings)
    assert "test-key-123" not in str(settings.dart_api_key)


def test_missing_key_fails_fast(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
