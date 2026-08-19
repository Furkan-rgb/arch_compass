from __future__ import annotations

from archcompass.ports.model_catalog import ProviderDefaults, ProviderDescriptor
from archcompass.reasoning.embedding_models import EmbeddingModelService
from archcompass.reasoning.records import (
    EmbeddingModelCandidate,
    EmbeddingModelCatalog,
    EmbeddingModelSelection,
    ProbeResult,
    ProviderAvailability,
)


class Selections:
    def __init__(self) -> None:
        self.selection: EmbeddingModelSelection | None = None

    def get(self) -> EmbeddingModelSelection | None:
        return self.selection

    def set(self, selection: EmbeddingModelSelection) -> EmbeddingModelSelection:
        self.selection = selection
        return selection

    def clear(self) -> None:
        self.selection = None


class Discovery:
    def discover(
        self, providers: tuple[ProviderDescriptor, ...]
    ) -> EmbeddingModelCatalog:
        del providers
        return EmbeddingModelCatalog(
            providers=[ProviderAvailability(provider="ollama", available=True)],
            candidates=[
                EmbeddingModelCandidate(
                    provider="ollama",
                    model="nomic-embed-text:latest",
                    dimensions=768,
                )
            ],
        )


def _probe(defaults: ProviderDefaults) -> ProbeResult:
    del defaults
    return ProbeResult(available=True)


def test_embedding_selection_uses_provider_owned_dimensions() -> None:
    selections = Selections()
    service = EmbeddingModelService(
        providers=(
            ProviderDescriptor(
                "ollama",
                _probe,
                ProviderDefaults(base_url="http://localhost:11434"),
            ),
        ),
        discovery=Discovery(),
        selections=selections,
    )

    status = service.select("ollama", "nomic-embed-text:latest")
    config = service.current()

    assert status.selection is not None
    assert status.selection.dimensions == 768
    assert config.model == "nomic-embed-text:latest"
    assert config.dimensions == 768
    assert config.base_url == "http://localhost:11434"
