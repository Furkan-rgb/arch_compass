from __future__ import annotations

from types import SimpleNamespace

import pytest

from archcompass.ports.model_catalog import ProviderDefaults, ProviderDescriptor
from archcompass.reasoning.adapters import embedding_catalog
from archcompass.reasoning.adapters.embedding_catalog import ProviderEmbeddingModelDiscovery
from archcompass.reasoning.records import ProbeResult


def test_google_client_stays_open_while_embedding_models_are_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SDK pager must finish before its owning HTTP client is closed."""

    events: list[str] = []

    class Models:
        def list(self, *, config: embedding_catalog.types.ListModelsConfig):
            del config
            events.append("list")
            return SimpleNamespace(
                page=[SimpleNamespace(name="models/gemini-embedding-2")]
            )

    class Client:
        def __init__(self, **kwargs: object):
            del kwargs
            self.models = Models()
            events.append("open")

        def close(self) -> None:
            events.append("close")

    def api_key(api_key_env: str, *, provider: str) -> str:
        del api_key_env, provider
        return "key"

    monkeypatch.setattr(embedding_catalog, "resolve_api_key", api_key)
    monkeypatch.setattr(embedding_catalog.genai, "Client", Client)

    def probe(defaults: ProviderDefaults) -> ProbeResult:
        del defaults
        return ProbeResult(available=True)

    descriptor = ProviderDescriptor(
        name="google",
        probe=probe,
        defaults=ProviderDefaults(api_key_env="GOOGLE_API_KEY"),
    )
    result = ProviderEmbeddingModelDiscovery().discover((descriptor,))

    assert events == ["open", "list", "close"]
    assert [candidate.model for candidate in result.candidates] == [
        "gemini-embedding-2"
    ]
