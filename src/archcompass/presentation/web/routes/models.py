"""Which models this workspace could reason with, and which one it has chosen.

Three routes: ask every enabled provider what it offers, choose one of the answers, and
forget the choice. The chooser is the only screen that pays for a network round trip on
paint, which is why the workspace summary next door does not.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import Field

from archcompass.presentation.web.dependencies import RestrictionsDep, RuntimeDep
from archcompass.presentation.web.routes.workspace import (
    WorkspaceSummaryResponse,
    describe_workspace,
)
from archcompass.presentation.web.schemas import APIModel, problem_responses


class AvailableModelResponse(APIModel):
    """One model a provider currently offers, in one of the thinking modes it has.

    A model that reasons both ways appears twice, once per mode, because the two are
    genuinely different choices: they cost differently and answer differently. A model with
    one mode appears once.
    """

    provider: str
    model: str
    thinking: bool | None = None
    label: str = ""
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    is_selected: bool = False


class ProviderAvailabilityResponse(APIModel):
    """Whether one enabled provider answered, and what it said if it did not."""

    provider: str
    available: bool
    #: Why not, naming the cure where there is one. Empty when available.
    detail: str = ""
    #: The provider's name written for a reader — `Google`, `Groq`, `Ollama`. Empty where
    #: the key already reads as one. The chooser groups by provider and a group needs a
    #: heading; a page that titled its own would need a table of every provider this build
    #: can reach, which is this table again in another language.
    label: str = ""
    probed_at: datetime


class ModelCatalogResponse(APIModel):
    providers: list[ProviderAvailabilityResponse]
    candidates: list[AvailableModelResponse]


class ModelSelectionRequest(APIModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    #: Absent means the model's own default, which is a third choice rather than the absence
    #: of one — so it is sent as null rather than omitted where a page means it.
    thinking: bool | None = None


class EmbeddingModelResponse(APIModel):
    provider: str
    model: str
    dimensions: int
    label: str = ""
    is_selected: bool = False


class EmbeddingCatalogResponse(APIModel):
    providers: list[ProviderAvailabilityResponse]
    candidates: list[EmbeddingModelResponse]


class EmbeddingSelectionRequest(APIModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


def routes() -> APIRouter:
    """The model catalogue and this workspace's selection."""

    router = APIRouter()

    @router.get("/api/models")
    def model_catalog(runtime: RuntimeDep) -> ModelCatalogResponse:
        """Every enabled provider, whether it answered, and what it offered.

        A GET that performs work: each provider is asked, over the network, with its own
        short budget. It also writes, in one narrow sense — a provider that answers clears a
        failure recorded against the current selection. Idempotent, and the alternative was
        making the chooser's first paint a mutation.
        """

        catalog = runtime.model_catalog_service.catalog()
        return ModelCatalogResponse(
            providers=[
                ProviderAvailabilityResponse(
                    provider=provider.provider,
                    available=provider.available,
                    detail=provider.detail,
                    label=provider.label,
                    probed_at=provider.probed_at,
                )
                for provider in catalog.providers
            ],
            candidates=[
                AvailableModelResponse(
                    provider=candidate.provider,
                    model=candidate.model,
                    thinking=candidate.thinking,
                    label=candidate.label,
                    input_token_limit=candidate.input_token_limit,
                    output_token_limit=candidate.output_token_limit,
                    is_selected=candidate.is_selected,
                )
                for candidate in catalog.candidates
            ],
        )

    @router.put("/api/models/selection", responses=problem_responses(409))
    def select_model(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: ModelSelectionRequest,
    ) -> WorkspaceSummaryResponse:
        """Choose the model this workspace reasons with, until it chooses another.

        Returns the whole summary rather than the selection, so the page that asked can
        replace what its chip is reading instead of fetching it again.
        """

        runtime.model_catalog_service.select(
            request.provider, request.model, request.thinking
        )
        return describe_workspace(runtime, hosted_mode)

    @router.get("/api/embeddings")
    def embedding_catalog(runtime: RuntimeDep) -> EmbeddingCatalogResponse:
        catalog = runtime.embedding_model_service.catalog()
        return EmbeddingCatalogResponse(
            providers=[
                ProviderAvailabilityResponse(
                    provider=provider.provider,
                    available=provider.available,
                    detail=provider.detail,
                    label=provider.label,
                    probed_at=provider.probed_at,
                )
                for provider in catalog.providers
            ],
            candidates=[
                EmbeddingModelResponse(
                    provider=candidate.provider,
                    model=candidate.model,
                    dimensions=candidate.dimensions,
                    label=candidate.label,
                    is_selected=candidate.is_selected,
                )
                for candidate in catalog.candidates
            ],
        )

    @router.put("/api/embeddings/selection", responses=problem_responses(409))
    def select_embedding_model(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: EmbeddingSelectionRequest,
    ) -> WorkspaceSummaryResponse:
        runtime.embedding_model_service.select(request.provider, request.model)
        return describe_workspace(runtime, hosted_mode)

    @router.delete("/api/models/selection", status_code=204)
    def clear_model_selection(runtime: RuntimeDep) -> Response:
        """Forget the choice, leaving this workspace with no model until it makes another.

        The way back out of a choice that turned out to be wrong. There is no file to edit
        instead, and on a hosted workspace there never was one.
        """

        runtime.model_catalog_service.clear()
        return Response(status_code=204)

    @router.delete("/api/embeddings/selection", status_code=204)
    def clear_embedding_selection(runtime: RuntimeDep) -> Response:
        runtime.embedding_model_service.clear()
        return Response(status_code=204)

    return router
