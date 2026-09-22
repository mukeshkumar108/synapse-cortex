import pytest

from src.config import settings
from src.main import validate_service_token_config


def test_production_requires_service_token(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "SYNAPSE_CORTEX_API_TOKEN", "")
    with pytest.raises(RuntimeError, match="SYNAPSE_CORTEX_API_TOKEN"):
        validate_service_token_config()


def test_development_allows_local_tokenless_mode(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "development")
    monkeypatch.setattr(settings, "SYNAPSE_CORTEX_API_TOKEN", "")
    validate_service_token_config()
