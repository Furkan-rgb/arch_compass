"""Independent workspace selection for policy-embedding models."""

from __future__ import annotations

from archcompass.boundary.model_catalog import (
    EmbeddingModelCatalog,
    EmbeddingModelSelection,
    EmbeddingModelStatus,
)
from archcompass.configuration import EmbeddingModelConfig
from archcompass.domain.errors import ConfigurationError
from archcompass.ports.model_catalog import (
    EmbeddingModelDiscovery,
    EmbeddingModelSelectionRepository,
    ProviderDescriptor,
)


class EmbeddingModelService:
    def __init__(
        self,
        *,
        providers: tuple[ProviderDescriptor, ...],
        discovery: EmbeddingModelDiscovery,
        selections: EmbeddingModelSelectionRepository,
        default: EmbeddingModelSelection | None = None,
        pin: EmbeddingModelConfig | None = None,
    ) -> None:
        self._providers = providers
        self._discovery = discovery
        self._selections = selections
        self._default = default
        self._pin = pin

    def status(self) -> EmbeddingModelStatus:
        if self._pin is not None:
            return EmbeddingModelStatus(
                selection=EmbeddingModelSelection(
                    provider=self._pin.provider,
                    model=self._pin.model,
                    dimensions=self._pin.dimensions,
                ),
                pinned=True,
            )
        return EmbeddingModelStatus(
            selection=self._selections.get() or self._available_default()
        )

    def catalog(self) -> EmbeddingModelCatalog:
        catalog = self._discovery.discover(self._providers)
        selected = self.status().selection
        return catalog.model_copy(
            update={
                "candidates": [
                    candidate.model_copy(
                        update={
                            "is_selected": (
                                selected is not None
                                and candidate.provider == selected.provider
                                and candidate.model == selected.model
                                and candidate.dimensions == selected.dimensions
                            )
                        }
                    )
                    for candidate in catalog.candidates
                ]
            }
        )

    def select(self, provider: str, model: str) -> EmbeddingModelStatus:
        if self._pin is not None:
            raise ConfigurationError(
                "Embedding configuration is pinned by ARCHCOMPASS_EMBEDDING_* variables."
            )
        if provider not in {item.name for item in self._providers}:
            raise ConfigurationError(f"{provider} is not enabled for this workspace.")
        if not model.strip():
            raise ConfigurationError("An embedding selection needs a model.")
        candidate = next(
            (
                item
                for item in self._discovery.discover(self._providers).candidates
                if item.provider == provider and item.model == model
            ),
            None,
        )
        if candidate is None:
            raise ConfigurationError(
                f"{provider}:{model} is not an available embedding model. Refresh Models "
                "and choose one of the models the provider currently reports."
            )
        self._selections.set(
            EmbeddingModelSelection(
                provider=provider,
                model=model.strip(),
                dimensions=candidate.dimensions,
            )
        )
        return self.status()

    def clear(self) -> None:
        if self._pin is not None:
            raise ConfigurationError(
                "Embedding configuration is pinned by ARCHCOMPASS_EMBEDDING_* variables."
            )
        self._selections.clear()

    def current(self) -> EmbeddingModelConfig:
        if self._pin is not None:
            return self._pin
        selection = self.status().selection
        if selection is None:
            raise ConfigurationError(
                "No embedding model is selected. Choose one in Models before starting a review."
            )
        descriptor = next(
            (item for item in self._providers if item.name == selection.provider), None
        )
        if descriptor is None:
            raise ConfigurationError(
                f"Embedding provider {selection.provider} is not enabled."
            )
        return EmbeddingModelConfig(
            provider=selection.provider,
            model=selection.model,
            dimensions=selection.dimensions,
            base_url=descriptor.defaults.resolved_base_url(),
            api_key_env=descriptor.defaults.api_key_env,
        )

    def _available_default(self) -> EmbeddingModelSelection | None:
        if self._default is None:
            return None
        enabled = {item.name for item in self._providers}
        return self._default if self._default.provider in enabled else None
