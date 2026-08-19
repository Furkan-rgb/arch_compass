from __future__ import annotations

import pytest

from archcompass.domain.errors import ConfigurationError
from archcompass.policies.adapters.embeddings import (
    DEFAULT_GOOGLE_EMBEDDING_DIMENSIONS,
    DEFAULT_GOOGLE_EMBEDDING_MODEL,
    embedding_config_from_environment,
)

_EMBEDDING_VARIABLES = (
    "ARCHCOMPASS_EMBEDDING_PROVIDER",
    "ARCHCOMPASS_EMBEDDING_MODEL",
    "ARCHCOMPASS_EMBEDDING_DIMENSIONS",
    "ARCHCOMPASS_EMBEDDING_BASE_URL",
    "ARCHCOMPASS_EMBEDDING_API_KEY_ENV",
)


def _clear_embedding_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in _EMBEDDING_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def test_google_embeddings_have_working_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_embedding_environment(monkeypatch)

    config = embedding_config_from_environment()

    assert config.provider == "google"
    assert config.model == DEFAULT_GOOGLE_EMBEDDING_MODEL
    assert config.dimensions == DEFAULT_GOOGLE_EMBEDDING_DIMENSIONS
    assert config.api_key_env == "GOOGLE_API_KEY"


def test_google_embedding_defaults_remain_overridable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_embedding_environment(monkeypatch)
    monkeypatch.setenv("ARCHCOMPASS_EMBEDDING_MODEL", "gemini-embedding-001")
    monkeypatch.setenv("ARCHCOMPASS_EMBEDDING_DIMENSIONS", "768")
    monkeypatch.setenv("ARCHCOMPASS_EMBEDDING_API_KEY_ENV", "CUSTOM_GOOGLE_KEY")

    config = embedding_config_from_environment()

    assert config.model == "gemini-embedding-001"
    assert config.dimensions == 768
    assert config.api_key_env == "CUSTOM_GOOGLE_KEY"


def test_non_google_provider_still_requires_its_model_and_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_embedding_environment(monkeypatch)
    monkeypatch.setenv("ARCHCOMPASS_EMBEDDING_PROVIDER", "ollama")

    with pytest.raises(ConfigurationError, match="selected embedding provider"):
        embedding_config_from_environment()
