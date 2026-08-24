"""Live discovery of the embedding models each provider is serving."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import httpx
from ollama import Client, ResponseError

from archcompass.configuration import resolve_api_key
from archcompass.domain.errors import ConfigurationError
from archcompass.reasoning.adapters import openrouter
from archcompass.reasoning.ports import ProviderDescriptor
from archcompass.reasoning.records import (
    EmbeddingModelCandidate,
    EmbeddingModelCatalog,
    ProviderAvailability,
)


class ProviderEmbeddingModelDiscovery:
    def discover(
        self, providers: tuple[ProviderDescriptor, ...]
    ) -> EmbeddingModelCatalog:
        availability: list[ProviderAvailability] = []
        candidates: list[EmbeddingModelCandidate] = []
        for descriptor in providers:
            if descriptor.name == "ollama":
                result, offered = self._ollama(descriptor)
            elif descriptor.name == openrouter.DESCRIPTOR.name:
                result, offered = self._openrouter(descriptor)
            else:
                continue
            availability.append(result)
            candidates.extend(offered)
        return EmbeddingModelCatalog(providers=availability, candidates=candidates)

    @staticmethod
    def _openrouter(
        descriptor: ProviderDescriptor,
    ) -> tuple[ProviderAvailability, list[EmbeddingModelCandidate]]:
        """The rows OpenRouter is serving today, from its own embedding catalogue.

        A separate endpoint from the reasoning one: `/models` is the chat catalogue and has
        none of these in it. Which widths they return is `openrouter._EMBEDDING_MODELS`, and
        the docstring there says why it cannot come from the listing.
        """

        try:
            api_key = resolve_api_key(descriptor.defaults.api_key_env, provider="openrouter")
            rows = openrouter.embedding_candidates(api_key)
        except (
            ConfigurationError,
            httpx.HTTPError,
            ConnectionError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            return ProviderAvailability(
                provider="openrouter",
                label="OpenRouter",
                available=False,
                detail=str(error),
            ), []
        candidates = [
            EmbeddingModelCandidate(
                provider="openrouter", model=model, dimensions=dimensions, label=label
            )
            for model, dimensions, label in rows
        ]
        return ProviderAvailability(
            provider="openrouter",
            label="OpenRouter",
            available=bool(candidates),
            detail="" if candidates else "OpenRouter is serving none of the supported "
            "embedding models",
        ), candidates

    @staticmethod
    def _ollama(
        descriptor: ProviderDescriptor,
    ) -> tuple[ProviderAvailability, list[EmbeddingModelCandidate]]:
        base_url = descriptor.defaults.resolved_base_url()
        if not base_url:
            return ProviderAvailability(
                provider="ollama",
                label="Ollama",
                available=False,
                detail="no Ollama base URL configured",
            ), []
        client = Client(host=base_url, timeout=2.0)
        try:
            candidates: list[EmbeddingModelCandidate] = []
            for entry in client.list().models:
                model = entry.model
                if not model:
                    continue
                details = client.show(model)
                if "embedding" not in (details.capabilities or []):
                    continue
                model_info = cast(Mapping[str, object], details.modelinfo or {})
                dimensions = _embedding_dimensions(model_info)
                if dimensions is None:
                    continue
                candidates.append(
                    EmbeddingModelCandidate(
                        provider="ollama",
                        model=model,
                        dimensions=dimensions,
                        label=(entry.details.parameter_size or "local embedding model")
                        if entry.details
                        else "local embedding model",
                    )
                )
        except (ResponseError, httpx.HTTPError, ConnectionError, ValueError) as error:
            return ProviderAvailability(
                provider="ollama", label="Ollama", available=False, detail=f"{base_url}: {error}"
            ), []
        return ProviderAvailability(
            provider="ollama",
            label="Ollama",
            available=True,
            detail="" if candidates else "no installed Ollama model supports embeddings",
        ), candidates


def _embedding_dimensions(model_info: Mapping[str, object]) -> int | None:
    for key, value in model_info.items():
        if key.endswith(".embedding_length") and isinstance(value, int):
            return value
    return None
