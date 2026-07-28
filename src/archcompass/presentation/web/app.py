"""FastAPI adapter for the local Arch Compass workspace."""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Annotated, Any, Literal, cast

import yaml
from fastapi import Body, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    ValidationError,
    model_validator,
)

from archcompass.application.reviews import JudgedCandidate
from archcompass.bootstrap import Runtime
from archcompass.domain.atlas import AtlasQueryResult, AtlasVersion, FindingCandidate
from archcompass.domain.case import ArchitectureCase, CaseRevision, CaseUpdate
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
    ReviewNotCancellableError,
    ReviewNotFoundError,
    ReviewStillRunningError,
    StaleAtlasError,
)
from archcompass.domain.policy import (
    PolicyDocument,
    PolicyIndexVersion,
    PolicySourceRegistration,
)
from archcompass.domain.review import BoundaryReview
from archcompass.domain.review_conversation import ReviewConversation, ReviewMessage
from archcompass.domain.workspace import (
    BoundaryReviewSummary,
    CaseSummary,
    RepositorySummary,
)

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


class ReviewRequest(APIModel):
    case_id: str = Field(min_length=1)
    repository_root: str = Field(min_length=1)


class ReviewConversationCreateRequest(APIModel):
    review_id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)


class ReviewQuestionRequest(APIModel):
    question: str = Field(min_length=1, max_length=4000)


class AnswerProse(APIModel):
    """A fragment of the answer being written, to append to whatever came before.

    Text only, and never a citation: grounding comes from positional flags that do not exist
    until the whole reply has arrived, so there is nothing here a reader could mistake for
    something the review supports. Fragments may stop before the answer does — a reply that
    needs the one sanctioned repair round is rewritten unstreamed — so this is provisional
    until the `answered` line.
    """

    event: Literal["prose"] = "prose"
    text: str


class QuestionAnswered(APIModel):
    """The appended message — the same object `POST .../messages` returns.

    This line is the record, and it replaces rather than completes whatever prose arrived
    before it: the message carries the validated answer and its grounding, and a turn that
    failed carries the failure even if fragments were shown first.
    """

    event: Literal["answered"] = "answered"
    message: ReviewMessage


class QuestionFailed(APIModel):
    """The turn could not be attempted, so no message was appended.

    Distinct from a failed message: a question refused before it reached the reasoner — blank,
    too long, a conversation that is gone — never becomes part of the history, and the status
    code cannot say so once the response has started.
    """

    event: Literal["failed"] = "failed"
    problem: ProblemDetail


AnswerProgressLine = Annotated[
    AnswerProse | QuestionAnswered | QuestionFailed,
    Field(discriminator="event"),
]


class AnswerProgress(RootModel[AnswerProgressLine]):
    """One line of `POST /api/review-conversations/{id}/messages/stream`."""


class BundledCase(APIModel):
    """One example case shipped with ArchCompass, ready to load into the workspace.

    Exists so the tool can be exercised without hand-writing a case first. The repository
    path is absolute and resolved on the server, because the browser cannot know where the
    package was installed.
    """

    name: str
    title: str
    problem_statement: str
    repository_root: str
    has_expected_answers: bool


class ScoredBoundaryResponse(APIModel):
    reference: str
    abstraction: str
    expected: bool
    actual: bool
    correct: bool
    because: str


class ReviewScoreResponse(APIModel):
    """A review graded against the answers its example ships.

    `unscored` names boundaries the key does not cover. They are reported rather than
    folded into the total, because a score over the remainder would look complete while
    measuring less than it claims.
    """

    example: str
    correct: int
    total: int
    boundaries: list[ScoredBoundaryResponse]
    unscored: list[str]


class ReviewStarted(APIModel):
    """The run has a record, so it has an identity — the stream's first line.

    Sent before detection, because this is the moment the review can be opened: everything
    that could refuse the run has passed, and a client that has this can leave the page it
    started from and watch the run where it lives.
    """

    event: Literal["started"] = "started"
    review_id: str
    case_id: str
    case_revision: int


class ReviewDetected(APIModel):
    """The deterministic sweep finished, so the run now has a known length.

    The boundaries are named in judgement order, which is the order the review will store
    them in and the order every later position refers to.
    """

    event: Literal["detected"] = "detected"
    total: int
    boundaries: list[str]


class ReviewJudged(APIModel):
    """One boundary judged. `position` counts from one, in the detected order."""

    event: Literal["judged"] = "judged"
    position: int
    total: int
    abstraction: str
    material: bool


class ReviewSummarising(APIModel):
    """Every boundary is judged; one call remains, over all of them at once."""

    event: Literal["summarising"] = "summarising"
    total: int


class ReviewCompleted(APIModel):
    """The composed, persisted review — the same object the non-streaming route returns."""

    event: Literal["completed"] = "completed"
    review: BoundaryReview


class ReviewFailed(APIModel):
    """The run failed. Nothing was persisted; the case and atlas are untouched."""

    event: Literal["failed"] = "failed"
    problem: ProblemDetail


ReviewProgressLine = Annotated[
    ReviewStarted
    | ReviewDetected
    | ReviewJudged
    | ReviewSummarising
    | ReviewCompleted
    | ReviewFailed,
    Field(discriminator="event"),
]


class ReviewProgress(RootModel[ReviewProgressLine]):
    """One line of `POST /api/reviews/stream`, discriminated by `event`."""


class NDJSONStreamingResponse(StreamingResponse):
    """A stream of one JSON object per line.

    Declared as a class so the OpenAPI document says `application/x-ndjson` where the
    schema is: a body that is a sequence of lines is not one JSON document, and describing
    it as `application/json` would tell a generated client the wrong thing to parse.
    """

    media_type = "application/x-ndjson"


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


class WorkspaceSummaryResponse(APIModel):
    workspace: str
    models: WorkspaceModels
    policy_index: PolicyIndexVersion | None = None


class PolicySourceRemovalResponse(APIModel):
    removed: bool


def create_app(runtime: Runtime) -> FastAPI:
    # A review runs synchronously inside its request. The background job queue existed
    # because a consultation took eight model calls through several stages and needed
    # recovery after an interrupted process; a review is one call per boundary against an
    # already-indexed atlas, and re-running it costs nothing that has to be reconciled.
    #
    # What does need saying is what happened to a run the last workspace was in the middle
    # of. A run cannot outlive the process holding its request, so a row still marked
    # running when this one starts belongs to a process that is gone, and leaving it saying
    # "in progress" for ever would be the one thing worse than reporting it failed.
    runtime.review_repository.abandon_running(
        reason="The workspace stopped while this review was running, so nothing was judged."
    )
    app = FastAPI(
        title="Arch Compass Local API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
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

    @app.post(
        "/api/repositories/start",
        status_code=201,
        responses=_problem_responses(404, 422),
    )
    def start_from_repository(request: RepositoryPathRequest) -> CaseRevision:
        """Index a repository and open a case about it, with nothing written in it yet.

        The whole of the first step for someone who has not authored a case. Both halves
        happen here so the flow either produces something reviewable or fails outright,
        rather than leaving a case pointing at an atlas that was never built — the same
        ordering, and the same reason, as loading a bundled example.
        """

        root = Path(request.root_path)
        runtime.repository_service.index(root)
        return runtime.case_service.start_from_repository(root)

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

    @app.get("/api/bundled-cases")
    def list_bundled_cases() -> list[BundledCase]:
        return [
            BundledCase(
                name=item.name,
                title=item.title,
                problem_statement=item.problem_statement,
                repository_root=item.repository_root,
                has_expected_answers=item.has_expected_answers,
            )
            for item in runtime.bundled_case_service.list()
        ]

    @app.post(
        "/api/bundled-cases/{name}/load",
        status_code=201,
        responses=_problem_responses(404, 422),
    )
    def load_bundled_case(name: str) -> CaseRevision:
        return runtime.bundled_case_service.load(name)

    @app.post(
        "/api/reviews",
        status_code=201,
        responses=_problem_responses(404, 422, 503),
    )
    def create_review(request: ReviewRequest) -> BoundaryReview:
        return runtime.review_service.review(
            request.case_id,
            repository_root=Path(request.repository_root),
        )

    @app.post(
        "/api/reviews/stream",
        response_class=NDJSONStreamingResponse,
        responses={
            200: {
                "model": ReviewProgress,
                "description": (
                    "The same review as POST /api/reviews, as newline-delimited JSON: one "
                    "ReviewProgress object per line, ending in a completed or failed line."
                ),
            },
            **_problem_responses(422),
        },
    )
    def stream_review(request: ReviewRequest) -> NDJSONStreamingResponse:
        """The review a person watches: countable, because detection knows the length.

        Everything that can go wrong after the first line arrives as a `failed` line
        carrying the same `ProblemDetail` the non-streaming route would have returned. Once
        a response has started, its status code can no longer say anything, so the stream
        has to end in a verdict about itself.
        """

        return NDJSONStreamingResponse(
            _review_progress_lines(runtime, request),
            # Buffering would defeat the point: progress that arrives all at once at the
            # end is the unexplained wait this route exists to replace.
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/reviews")
    def list_reviews(
        case_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[BoundaryReviewSummary]:
        return runtime.review_repository.list(case_id=case_id, limit=limit)

    @app.get(
        "/api/reviews/{review_id}",
        responses=_problem_responses(404, 422),
    )
    def get_review(review_id: str) -> BoundaryReview:
        return runtime.review_repository.get(review_id)

    @app.post(
        "/api/reviews/{review_id}/cancel",
        responses=_problem_responses(404, 409, 422),
    )
    def cancel_review(review_id: str) -> BoundaryReview:
        """Ask a running review to stop, and answer with the record that says it will.

        The run reads that record between model calls, so this returns before the work has
        actually stopped: what is settled here is the outcome, not the timing. A review that
        finished a moment ago is a review that finished, and says so rather than pretending
        to have been cancelled.
        """

        if not runtime.review_repository.cancel(review_id):
            stored = runtime.review_repository.get(review_id)
            raise ReviewNotCancellableError(
                f"That review is {stored.status.value}, not running, so there is nothing "
                "to cancel."
            )
        return runtime.review_repository.get(review_id)

    @app.delete(
        "/api/reviews/{review_id}",
        status_code=204,
        responses=_problem_responses(404, 409, 422),
    )
    def delete_review(review_id: str) -> Response:
        """Remove a review and the question threads hung off it.

        Deleting is not editing: it removes the record rather than leaving one that says
        something else, which is what immutability is about. A running review is refused —
        cancel it first, so the work stops before its record goes.
        """

        runtime.review_repository.delete(review_id)
        return Response(status_code=204)

    @app.get(
        "/api/reviews/{review_id}/score",
        responses=_problem_responses(404, 422),
    )
    def score_review(review_id: str) -> ReviewScoreResponse | None:
        """Null when the reviewed repository ships no answers, which is the usual case."""

        review = runtime.review_repository.get(review_id)
        score = runtime.bundled_case_service.score(review)
        if score is None:
            return None
        return ReviewScoreResponse(
            example=score.example,
            correct=score.correct,
            total=score.total,
            boundaries=[
                ScoredBoundaryResponse(
                    reference=item.reference,
                    abstraction=item.abstraction,
                    expected=item.expected,
                    actual=item.actual,
                    correct=item.correct,
                    because=item.because,
                )
                for item in score.boundaries
            ],
            unscored=list(score.unscored),
        )

    @app.post(
        "/api/review-conversations",
        status_code=201,
        responses=_problem_responses(404, 422),
    )
    def create_review_conversation(
        request: ReviewConversationCreateRequest,
    ) -> ReviewConversation:
        return runtime.review_conversation_service.create(
            request.review_id,
            title=request.title,
        )

    @app.get(
        "/api/review-conversations",
        responses=_problem_responses(404, 422),
    )
    def list_review_conversations(review_id: str) -> list[ReviewConversation]:
        return runtime.review_conversation_service.list(review_id)

    @app.get(
        "/api/review-conversations/{conversation_id}",
        responses=_problem_responses(404, 422),
    )
    def get_review_conversation(conversation_id: str) -> ReviewConversation:
        return runtime.review_conversation_service.show(conversation_id)

    @app.post(
        "/api/review-conversations/{conversation_id}/messages",
        status_code=201,
        responses=_problem_responses(404, 409, 422, 503),
    )
    def ask_review_question(
        conversation_id: str,
        request: ReviewQuestionRequest,
    ) -> ReviewMessage:
        return runtime.review_conversation_service.ask(conversation_id, request.question)

    @app.post(
        "/api/review-conversations/{conversation_id}/messages/stream",
        response_class=NDJSONStreamingResponse,
        responses={
            200: {
                "model": AnswerProgress,
                "description": (
                    "The same turn as POST .../messages, as newline-delimited JSON: any "
                    "number of prose fragments, then one answered or failed line."
                ),
            },
            **_problem_responses(404, 409, 422, 503),
        },
    )
    def stream_review_question(
        conversation_id: str,
        request: ReviewQuestionRequest,
    ) -> NDJSONStreamingResponse:
        """The same turn, with the answer's prose arriving as it is written.

        A second transport for one flow, not a second flow: the same application call appends
        the same message, and this route adds only when its text reaches the reader. A
        provider that cannot stream sends no fragments and the answered line arrives on its
        own, which is why there is no capability to query first.
        """

        return NDJSONStreamingResponse(
            _answer_progress_lines(runtime, conversation_id, request.question),
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
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


def _abstraction_name(candidate: FindingCandidate) -> str:
    """The boundary a person recognises: the abstraction, not the candidate's identity."""

    first = candidate.participants[0] if candidate.participants else None
    return first.qualified_name if first is not None else "unnamed boundary"


def _review_progress_lines(runtime: Runtime, request: ReviewRequest) -> Iterator[str]:
    """Run one review in a worker thread and yield each line as the run produces it.

    A thread, not a job queue (master plan §18). The work is still exactly this request's
    work: a client that navigates away leaves the run to finish or fail on its own, and the
    review it produces is the same either way. What streaming buys is that the caller learns
    the review's identity before the first model call and the length of the sequence after
    detection, instead of learning both after the last one.

    The queue is the only shared state, it lives as long as the request, and the application
    service still owns detection, judgement order and composition: this function chooses
    nothing about the review, it only reports it.
    """

    lines: Queue[str | None] = Queue()

    def emit(
        event: ReviewStarted
        | ReviewDetected
        | ReviewJudged
        | ReviewSummarising
        | ReviewCompleted
        | ReviewFailed,
    ) -> None:
        lines.put(event.model_dump_json())

    def report_start(review: BoundaryReview) -> None:
        emit(
            ReviewStarted(
                review_id=review.review_id,
                case_id=review.case_id,
                case_revision=review.case_revision,
            )
        )

    detected = 0

    def report_detection(candidates: Sequence[FindingCandidate]) -> None:
        nonlocal detected
        detected = len(candidates)
        emit(
            ReviewDetected(
                total=detected,
                boundaries=[_abstraction_name(item) for item in candidates],
            )
        )

    def report_verdict(judged: JudgedCandidate, position: int, total: int) -> None:
        emit(
            ReviewJudged(
                position=position,
                total=total,
                abstraction=_abstraction_name(judged.candidate),
                material=judged.verdict.material,
            )
        )

    def run() -> None:
        try:
            review = runtime.review_service.review(
                request.case_id,
                repository_root=Path(request.repository_root),
                on_started=report_start,
                on_detected=report_detection,
                on_verdict=report_verdict,
                on_summarising=lambda: emit(ReviewSummarising(total=detected)),
            )
        except ArchCompassError as error:
            # The status is deliberately dropped: the response is already a 200 by the time
            # the run fails, and a code in the body that disagreed with it would be worse
            # than one that says nothing.
            _status, code, retryable = _classify_error(error)
            emit(
                ReviewFailed(
                    problem=ProblemDetail(
                        code=code,
                        message=str(error),
                        retryable=retryable,
                    )
                )
            )
        except Exception:
            # Broad on purpose: a stream that simply closes tells the reader nothing, and
            # this is the last place that can still say the run failed. Only ArchCompass's
            # own errors are written out for a person to read, so an unexpected one is
            # reported without forwarding its text.
            emit(
                ReviewFailed(
                    problem=ProblemDetail(
                        code="archcompass_error",
                        message="The review failed unexpectedly, and nothing was saved.",
                    )
                )
            )
        else:
            emit(ReviewCompleted(review=review))
        finally:
            lines.put(None)

    worker = Thread(target=run, daemon=True, name="archcompass-review")
    worker.start()
    while (line := lines.get()) is not None:
        yield f"{line}\n"


def _answer_progress_lines(
    runtime: Runtime,
    conversation_id: str,
    question: str,
) -> Iterator[str]:
    """Ask one question in a worker thread and yield each line as the answer is written.

    The same shape as `_review_progress_lines`, for the same reason: a thread and a queue that
    live exactly as long as this request, no job queue, and an application service that still
    owns the turn. This function chooses nothing — not whether the reply streams, not what the
    message contains, not whether the turn succeeded — it only reports.

    A refusal reaching here as `failed` rather than as a status code is not a downgrade: the
    response is already a 200 by the time the reasoner is called, and the alternative is a
    stream that closes without saying anything. A question rejected before the response starts
    still gets its status, because validation of the body happens before this runs.
    """

    lines: Queue[str | None] = Queue()

    def emit(event: AnswerProse | QuestionAnswered | QuestionFailed) -> None:
        lines.put(event.model_dump_json())

    def run() -> None:
        try:
            message = runtime.review_conversation_service.ask(
                conversation_id,
                question,
                on_prose=lambda text: emit(AnswerProse(text=text)),
            )
        except ArchCompassError as error:
            # The status is deliberately dropped: it can no longer be said, and a code in the
            # body disagreeing with the 200 already sent would be worse than one that is
            # silent about it.
            _status, code, retryable = _classify_error(error)
            emit(
                QuestionFailed(
                    problem=ProblemDetail(code=code, message=str(error), retryable=retryable)
                )
            )
        except Exception:
            # Broad on purpose, and the text is not forwarded: this is the last place that can
            # still say the turn failed, and only ArchCompass's own errors are written for a
            # person to read.
            emit(
                QuestionFailed(
                    problem=ProblemDetail(
                        code="archcompass_error",
                        message="That question failed unexpectedly, and nothing was saved.",
                    )
                )
            )
        else:
            emit(QuestionAnswered(message=message))
        finally:
            lines.put(None)

    worker = Thread(target=run, daemon=True, name="archcompass-review-question")
    worker.start()
    while (line := lines.get()) is not None:
        yield f"{line}\n"


def _classify_error(error: ArchCompassError) -> tuple[int, str, bool]:
    if isinstance(
        error,
        (
            CaseNotFoundError,
            AtlasNotFoundError,
            ReviewNotFoundError,
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
            ReviewNotCancellableError,
            ReviewStillRunningError,
            StaleAtlasError,
        ),
    ):
        # Retryable only where repeating the request could succeed. A review that has
        # already finished will not start running again, so cancelling it never will.
        return 409, "state_conflict", isinstance(
            error,
            (ConversationRevisionConflictError, ReviewStillRunningError, StaleAtlasError),
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
