from __future__ import annotations

import pytest

from archcompass.domain.errors import ConfigurationError
from archcompass.policies.adapters.embeddings import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_PROVIDER,
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


def test_an_unconfigured_workspace_embeds_with_what_the_index_was_built_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default and the shipped index are one decision, not two.

    Production retrieval never generates a vector, so the file this package ships is the
    only source a review has — and whichever identity it carries is the embedder that works
    without configuring anything. A default naming a different one would be a workspace
    that refuses its first review while looking correctly set up.
    """

    _clear_embedding_environment(monkeypatch)

    config = embedding_config_from_environment()

    assert config.provider == DEFAULT_EMBEDDING_PROVIDER
    assert config.model == DEFAULT_EMBEDDING_MODEL
    assert config.dimensions == DEFAULT_EMBEDDING_DIMENSIONS
    assert config.api_key_env == "OPENROUTER_API_KEY"


def test_the_shipped_index_carries_the_identity_the_default_asks_for() -> None:
    """The pairing above, checked against the file rather than against the constants."""

    from archcompass.policies.adapters.bundled import bundled_corpus
    from archcompass.policies.adapters.prebuilt import PREBUILT_INDEX, coverage

    found = coverage(PREBUILT_INDEX, bundled_corpus(), embedding_config_from_environment())

    assert found.complete, found.explain(path=PREBUILT_INDEX, identity="the default")


def test_the_embedding_defaults_remain_overridable(
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
