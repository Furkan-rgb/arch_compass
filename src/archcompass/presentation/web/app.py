"""FastAPI adapter for the local Arch Compass workspace."""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import yaml
from fastapi import Body, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from archcompass.bootstrap import Runtime
from archcompass.domain.atlas import AtlasQueryResult, AtlasVersion
from archcompass.domain.case import ArchitectureCase, CaseRevision, CaseUpdate
from archcompass.domain.consultation import ConsultationRun
from archcompass.domain.conversation import ConversationMessage, ReportConversation
from archcompass.domain.errors import (
    ArchCompassError,
    AtlasNotFoundError,
    CaseNotFoundError,
    CaseRevisionConflictError,
    ConversationNotFoundError,
    ConversationRetrievalError,
    ConversationRevisionConflictError,
    ConversationValidationError,
    ModelOutputValidationError,
    PathValidationError,
    PersistenceError,
    PolicyFormatError,
    PolicyNotFoundError,
    ProviderError,
    RunNotFoundError,
    StaleAtlasError,
)
from archcompass.domain.execution import (
    ConsultationJob,
    ConsultationJobStatus,
    ConsultationProgressEvent,
)
from archcompass.domain.policy import (
    PolicyDocument,
    PolicyIndexVersion,
    PolicySourceRegistration,
)
from archcompass.domain.workspace import CaseSummary, RepositorySummary, RunSummary

STATIC_DIR = Path(__file__).resolve().parent / "static"


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProblemDetail(APIModel):
    code: str
    message: str
    retryable: bool = False
    field_errors: list[str] = Field(default_factory=list[str])


_PROBLEM_RESPONSE_DESCRIPTIONS = {
    404: "The requested pinned resource was not found.",
    409: "The request conflicts with the current persisted revision or pinned state.",
    422: "The request or generated evidence did not satisfy the validated contract.",
    503: "A configured model provider is temporarily unavailable.",
}


def _problem_responses(
    *statuses: Literal[404, 409, 422, 503],
) -> dict[int | str, dict[str, Any]]:
    return {
        status: {
            "model": ProblemDetail,
            "description": _PROBLEM_RESPONSE_DESCRIPTIONS[status],
        }
        for status in statuses
    }


def _export_responses(
    json_schema: dict[str, Any],
    *,
    description: str,
) -> dict[int | str, dict[str, Any]]:
    return {
        200: {
            "description": description,
            "content": {
                "application/json": {"schema": json_schema},
                "text/markdown": {"schema": {"type": "string"}},
            },
        },
        **_problem_responses(404, 422),
    }


class RepositoryPathRequest(APIModel):
    root_path: str = Field(min_length=1)


class AtlasExploreRequest(APIModel):
    root_path: str = Field(min_length=1)
    operation: Literal[
        "children",
        "dependencies",
        "dependants",
        "callers",
        "implementations",
        "tests",
        "forward_neighbourhood",
        "reverse_neighbourhood",
        "search",
        "shortest_path",
        "cycles",
        "signals",
    ]
    node_id: str | None = None
    target_id: str | None = None
    terms: list[str] = Field(default_factory=list, max_length=10)
    signal_codes: list[str] = Field(default_factory=list, max_length=10)
    depth: int = Field(default=1, ge=1, le=5)
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def validate_operation_fields(self) -> AtlasExploreRequest:
        if self.operation == "search" and not self.terms:
            raise ValueError("search requires at least one term")
        if self.operation not in {"search", "cycles", "signals"} and self.node_id is None:
            raise ValueError(f"{self.operation} requires node_id")
        if self.operation == "shortest_path" and self.target_id is None:
            raise ValueError("shortest_path requires target_id")
        return self


class ConsultationStartRequest(APIModel):
    case_id: str = Field(min_length=1)
    repository_root: str | None = None


class ConversationCreateRequest(APIModel):
    run_id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)


class ReportQuestionRequest(APIModel):
    question: str = Field(min_length=1, max_length=4000)


class PolicySourceRequest(APIModel):
    source: str = Field(min_length=1)


class PolicyRebuildRequest(APIModel):
    repository_root: str | None = None


class ModelIdentity(APIModel):
    provider: str
    model: str


class EmbeddingModelIdentity(ModelIdentity):
    dimensions: int


class WorkspaceModels(APIModel):
    reasoning: ModelIdentity
    embedding: EmbeddingModelIdentity


class ConsultationBudgets(APIModel):
    max_zoom_iterations: int
    max_queries_per_iteration: int
    max_query_results: int
    max_excerpt_lines: int


class WorkspaceSummaryResponse(APIModel):
    workspace: str
    models: WorkspaceModels
    consultation: ConsultationBudgets
    policy_index: PolicyIndexVersion | None = None


class PolicySourceRemovalResponse(APIModel):
    removed: bool


def create_app(runtime: Runtime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        runtime.job_service.recover_interrupted()
        try:
            yield
        finally:
            runtime.job_service.close()

    app = FastAPI(
        title="Arch Compass Local API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
        responses=_problem_responses(422),
    )

    @app.exception_handler(ArchCompassError)
    async def archcompass_error(
        _request: Request, error: ArchCompassError
    ) -> JSONResponse:
        status, code, retryable = _classify_error(error)
        return JSONResponse(
            status_code=status,
            content=ProblemDetail(
                code=code,
                message=str(error),
                retryable=retryable,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        fields = [
            ".".join(str(item) for item in detail["loc"])
            + ": "
            + str(detail["msg"])
            for detail in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=ProblemDetail(
                code="validation_error",
                message="The request did not match the API contract.",
                field_errors=fields,
            ).model_dump(mode="json"),
    )

    @app.get("/api/workspace")
    def workspace_summary() -> WorkspaceSummaryResponse:
        policy_version = runtime.policy_service.current_version()
        return WorkspaceSummaryResponse(
            workspace=str(runtime.workspace),
            models=WorkspaceModels(
                reasoning=ModelIdentity(
                    provider=runtime.config.models.reasoning.provider,
                    model=runtime.config.models.reasoning.model,
                ),
                embedding=EmbeddingModelIdentity(
                    provider=runtime.config.models.embedding.provider,
                    model=runtime.config.models.embedding.model,
                    dimensions=runtime.config.models.embedding.dimensions,
                ),
            ),
            consultation=ConsultationBudgets.model_validate(
                runtime.config.consultation.model_dump()
            ),
            policy_index=policy_version,
        )

    @app.get("/api/cases")
    def list_cases(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[CaseSummary]:
        return runtime.case_service.list(limit=limit)

    @app.post("/api/cases", status_code=201)
    def create_case(case: ArchitectureCase) -> CaseRevision:
        return runtime.case_service.create(case)

    @app.post("/api/cases/import-yaml", status_code=201)
    def import_case_yaml(
        source: Annotated[str, Body(media_type="text/yaml")],
    ) -> CaseRevision:
        try:
            case = ArchitectureCase.model_validate(yaml.safe_load(source))
        except (yaml.YAMLError, ValidationError, TypeError, ValueError) as error:
            raise ModelOutputValidationError(f"Invalid architecture case YAML: {error}") from error
        return runtime.case_service.create(case)

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str, revision: int | None = None) -> CaseRevision:
        return runtime.case_service.show(case_id, revision)

    @app.patch("/api/cases/{case_id}")
    def update_case(case_id: str, update: CaseUpdate) -> CaseRevision:
        return runtime.case_service.update(case_id, update)

    @app.get("/api/cases/{case_id}/history")
    def case_history(case_id: str) -> list[CaseRevision]:
        return runtime.case_service.history(case_id)

    @app.get("/api/repositories")
    def list_repositories(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[RepositorySummary]:
        return runtime.repository_service.list(limit=limit)

    @app.post("/api/repositories/index", status_code=201)
    def index_repository(request: RepositoryPathRequest) -> AtlasVersion:
        return runtime.repository_service.index(Path(request.root_path))

    @app.get("/api/repositories/summary")
    def repository_summary(root_path: str) -> AtlasQueryResult:
        return runtime.atlas_service.summary(Path(root_path))

    @app.get("/api/repositories/hotspots")
    def repository_hotspots(
        root_path: str,
        metric: str = "reverse_dependency_reach",
    ) -> AtlasQueryResult:
        return runtime.atlas_service.hotspots(Path(root_path), metric)

    @app.get("/api/repositories/inspect")
    def repository_inspect(root_path: str, node_id: str) -> AtlasQueryResult:
        return runtime.atlas_service.inspect(Path(root_path), node_id)

    @app.post("/api/repositories/explore")
    def repository_explore(request: AtlasExploreRequest) -> AtlasQueryResult:
        repository = Path(request.root_path)
        if request.operation == "search":
            return runtime.atlas_service.search(
                repository, request.terms, limit=request.limit
            )
        if request.operation == "cycles":
            return runtime.atlas_service.cycles(repository, limit=request.limit)
        if request.operation == "signals":
            return runtime.atlas_service.signals(
                repository,
                codes=request.signal_codes,
                limit=request.limit,
            )
        assert request.node_id is not None
        if request.operation == "children":
            return runtime.atlas_service.children(
                repository, request.node_id, limit=request.limit
            )
        if request.operation == "shortest_path":
            assert request.target_id is not None
            return runtime.atlas_service.shortest_path(
                repository, request.node_id, request.target_id
            )
        if request.operation in {"forward_neighbourhood", "reverse_neighbourhood"}:
            return runtime.atlas_service.neighbourhood(
                repository,
                request.node_id,
                direction=cast(
                    Literal["forward_neighbourhood", "reverse_neighbourhood"],
                    request.operation,
                ),
                depth=request.depth,
                limit=request.limit,
            )
        relation_kinds = {
            "dependencies": "direct_dependencies",
            "dependants": "direct_dependants",
            "callers": "known_callers",
            "implementations": "implementations",
            "tests": "related_tests",
        }
        return runtime.atlas_service.relationships(
            repository,
            request.node_id,
            kind=cast(
                Literal[
                    "direct_dependencies",
                    "direct_dependants",
                    "known_callers",
                    "implementations",
                    "related_tests",
                ],
                relation_kinds[request.operation],
            ),
            limit=request.limit,
        )

    @app.post("/api/consultations", status_code=202)
    def start_consultation(request: ConsultationStartRequest) -> ConsultationJob:
        return runtime.job_service.start(
            request.case_id,
            repository_root=(
                Path(request.repository_root)
                if request.repository_root is not None
                else None
            ),
        )

    @app.get("/api/consultations")
    def list_consultations(
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> list[ConsultationJob]:
        return runtime.job_service.list(limit=limit)

    @app.get("/api/consultations/{run_id}")
    def get_consultation(run_id: str) -> ConsultationJob:
        return runtime.job_service.get(run_id)

    @app.get("/api/consultations/{run_id}/events")
    def consultation_events(
        run_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
    ) -> list[ConsultationProgressEvent]:
        return runtime.job_service.events(run_id, after_sequence=after)

    @app.get("/api/consultations/{run_id}/stream")
    async def consultation_stream(
        run_id: str,
        request: Request,
    ) -> StreamingResponse:
        after_header = request.headers.get("last-event-id", "0")
        try:
            after = max(0, int(after_header))
        except ValueError:
            after = 0

        async def stream() -> AsyncIterator[str]:
            sequence = after
            while True:
                if await request.is_disconnected():
                    return
                events = runtime.job_service.events(
                    run_id,
                    after_sequence=sequence,
                )
                for event in events:
                    sequence = event.sequence
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: {event.event_type}\n"
                        f"data: {event.model_dump_json()}\n\n"
                    )
                job = runtime.job_service.get(run_id)
                if job.status in {
                    ConsultationJobStatus.SUCCEEDED,
                    ConsultationJobStatus.SUCCEEDED_WITH_WARNINGS,
                    ConsultationJobStatus.FAILED,
                    ConsultationJobStatus.INTERRUPTED,
                }:
                    return
                if not events:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/runs")
    def list_runs(
        case_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[RunSummary]:
        return runtime.run_service.list(case_id=case_id, limit=limit)

    @app.get(
        "/api/runs/{run_id}",
        responses=_problem_responses(404, 422),
    )
    def get_run(run_id: str) -> ConsultationRun:
        return runtime.run_service.show(run_id)

    @app.post(
        "/api/conversations",
        status_code=201,
        responses=_problem_responses(404, 422),
    )
    def create_report_conversation(
        request: ConversationCreateRequest,
    ) -> ReportConversation:
        return runtime.conversation_service.create(
            request.run_id,
            title=request.title,
        )

    @app.get(
        "/api/conversations",
        responses=_problem_responses(404, 422),
    )
    def list_report_conversations(run_id: str) -> list[ReportConversation]:
        return runtime.conversation_service.list(run_id)

    @app.get(
        "/api/conversations/{conversation_id}",
        responses=_problem_responses(404, 422),
    )
    def get_report_conversation(conversation_id: str) -> ReportConversation:
        return runtime.conversation_service.show(conversation_id)

    @app.get(
        "/api/conversations/{conversation_id}/history",
        responses=_problem_responses(404, 422),
    )
    def get_report_conversation_history(
        conversation_id: str,
    ) -> list[ConversationMessage]:
        return runtime.conversation_service.history(conversation_id)

    @app.post(
        "/api/conversations/{conversation_id}/messages",
        status_code=201,
        responses=_problem_responses(404, 409, 422, 503),
    )
    def ask_report_question(
        conversation_id: str,
        request: ReportQuestionRequest,
    ) -> ConversationMessage:
        return runtime.conversation_service.ask(conversation_id, request.question)

    @app.get(
        "/api/conversations/{conversation_id}/export",
        responses=_export_responses(
            {
                "type": "object",
                "required": ["conversation", "messages"],
                "properties": {
                    "conversation": {
                        "$ref": "#/components/schemas/ReportConversation"
                    },
                    "messages": {
                        "type": "array",
                        "items": {
                            "$ref": "#/components/schemas/ConversationMessage"
                        },
                    },
                },
                "additionalProperties": False,
            },
            description=(
                "The pinned conversation as canonical JSON or a deterministic "
                "Markdown transcript."
            ),
        ),
    )
    def export_report_conversation(
        conversation_id: str,
        format: Literal["markdown", "json"] = "markdown",
    ) -> PlainTextResponse:
        return PlainTextResponse(
            runtime.conversation_service.export(
                conversation_id,
                format=format,
            ),
            media_type=(
                "application/json"
                if format == "json"
                else "text/markdown; charset=utf-8"
            ),
        )

    @app.get(
        "/api/runs/{run_id}/report",
        responses=_export_responses(
            {"$ref": "#/components/schemas/RecommendationReport"},
            description=(
                "The immutable recommendation report as canonical JSON or "
                "deterministic Markdown."
            ),
        ),
    )
    def download_report(
        run_id: str,
        format: Literal["markdown", "json"] = "markdown",
    ) -> PlainTextResponse:
        run = runtime.run_service.show(run_id)
        if format == "markdown":
            if run.markdown_report is None:
                raise PersistenceError(f"Consultation run {run_id} has no Markdown report")
            return PlainTextResponse(
                run.markdown_report,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="{run_id}.md"'
                },
            )
        if run.report is None:
            raise PersistenceError(f"Consultation run {run_id} has no structured report")
        return PlainTextResponse(
            run.report.model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'},
        )

    @app.get("/api/policies")
    def list_policies(repository_root: str | None = None) -> list[PolicyDocument]:
        return runtime.policy_service.catalog(
            repository_root=(
                Path(repository_root) if repository_root is not None else None
            )
        )

    @app.get("/api/policies/sources")
    def list_policy_sources() -> list[PolicySourceRegistration]:
        return runtime.policy_service.list_sources()

    @app.post("/api/policies/sources", status_code=201)
    def add_policy_source(request: PolicySourceRequest) -> PolicySourceRegistration:
        return runtime.policy_service.add_source(Path(request.source))

    @app.delete("/api/policies/sources")
    def remove_policy_source(source: str) -> PolicySourceRemovalResponse:
        return PolicySourceRemovalResponse(
            removed=runtime.policy_service.remove_source(Path(source))
        )

    @app.post("/api/policies/rebuild")
    def rebuild_policies(request: PolicyRebuildRequest) -> PolicyIndexVersion:
        return runtime.policy_service.rebuild(
            repository_root=(
                Path(request.repository_root)
                if request.repository_root is not None
                else None
            )
        )

    @app.get("/api/policies/{policy_id}")
    def get_policy(
        policy_id: str, repository_root: str | None = None
    ) -> PolicyDocument:
        policies = runtime.policy_service.catalog(
            repository_root=(
                Path(repository_root) if repository_root is not None else None
            )
        )
        for policy in policies:
            if policy.id == policy_id:
                return policy
        raise PolicyNotFoundError(f"Policy {policy_id} was not found")

    @app.api_route(
        "/api/{api_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    def unknown_api_route(api_path: str) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=ProblemDetail(
                code="not_found",
                message=f"API route /api/{api_path} was not found",
            ).model_dump(mode="json"),
        )

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    def spa(path: str) -> FileResponse | JSONResponse:
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(STATIC_DIR.resolve()):
            return FileResponse(candidate)
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            status_code=503,
            content=ProblemDetail(
                code="frontend_not_built",
                message="The Arch Compass frontend assets have not been built.",
            ).model_dump(mode="json"),
        )

    return app


def _classify_error(error: ArchCompassError) -> tuple[int, str, bool]:
    if isinstance(
        error,
        (
            CaseNotFoundError,
            AtlasNotFoundError,
            RunNotFoundError,
            PolicyNotFoundError,
            ConversationNotFoundError,
        ),
    ):
        return 404, "not_found", False
    if isinstance(
        error,
        (
            CaseRevisionConflictError,
            ConversationRevisionConflictError,
            StaleAtlasError,
        ),
    ):
        return 409, "state_conflict", isinstance(
            error,
            (ConversationRevisionConflictError, StaleAtlasError),
        )
    if isinstance(
        error,
        (
            PathValidationError,
            PolicyFormatError,
            ModelOutputValidationError,
            ConversationValidationError,
            ConversationRetrievalError,
        ),
    ):
        return 422, "validation_error", False
    if isinstance(error, ProviderError):
        return 503, "provider_unavailable", True
    if isinstance(error, PersistenceError):
        return 500, "persistence_error", False
    return 400, "archcompass_error", False
