"""Live discovery of Google and Ollama embedding models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import httpx
from google import genai
from google.genai import errors, types
from ollama import Client, ResponseError

from archcompass.configuration import resolve_api_key
from archcompass.domain.errors import ConfigurationError
from archcompass.reasoning.ports import ProviderDescriptor
from archcompass.reasoning.records import (
    EmbeddingModelCandidate,
    EmbeddingModelCatalog,
    ProviderAvailability,
)

_GOOGLE_EMBEDDINGS = (
    ("gemini-embedding-2", 3072),
    ("gemini-embedding-001", 3072),
)


class ProviderEmbeddingModelDiscovery:
    def discover(
        self, providers: tuple[ProviderDescriptor, ...]
    ) -> EmbeddingModelCatalog:
        availability: list[ProviderAvailability] = []
        candidates: list[EmbeddingModelCandidate] = []
        for descriptor in providers:
            if descriptor.name == "google":
                result, offered = self._google(descriptor)
            elif descriptor.name == "ollama":
                result, offered = self._ollama(descriptor)
            else:
                continue
            availability.append(result)
            candidates.extend(offered)
        return EmbeddingModelCatalog(providers=availability, candidates=candidates)

    @staticmethod
    def _google(
        descriptor: ProviderDescriptor,
    ) -> tuple[ProviderAvailability, list[EmbeddingModelCandidate]]:
        try:
            api_key = resolve_api_key(descriptor.defaults.api_key_env, provider="google")
            # Keep the SDK client alive until the pager has been consumed. Accessing
            # ``genai.Client(...).models.list(...)`` as one chained expression leaves the
            # client temporary eligible for finalization after ``.models`` is resolved;
            # the SDK then closes its HTTP transport before ``list`` sends the request.
            # This surfaced as a 500 from /api/embeddings when the Models page requested
            # the reasoning and embedding catalogues together.
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=2_000),
            )
            try:
                page = client.models.list(
                    config=types.ListModelsConfig(query_base=True, page_size=100)
                ).page
                names = {
                    (model.name or "").removeprefix("models/") for model in page
                }
            finally:
                client.close()
        except (
            ConfigurationError,
            errors.APIError,
            httpx.HTTPError,
            ConnectionError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            return ProviderAvailability(
                provider="google", label="Google", available=False, detail=str(error)
            ), []
        candidates = [
            EmbeddingModelCandidate(
                provider="google",
                model=model,
                dimensions=dimensions,
                label="Google Gemini embedding",
            )
            for model, dimensions in _GOOGLE_EMBEDDINGS
            if model in names
        ]
        return ProviderAvailability(
            provider="google",
            label="Google",
            available=bool(candidates),
            detail="" if candidates else "no supported Google embedding model is available",
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
