"""Pydantic HTTP boundary for the clean-break review workflow."""

# FastAPI decorator registration is the use of the nested route functions.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import Field

from archcompass.bootstrap import Runtime
from archcompass.domain import AnswerStatus, Candidate, Evidence, Review
from archcompass.domain.errors import ReviewHasNoReportError
from archcompass.presentation.web.dependencies import RuntimeDep, SpendsModelBudget
from archcompass.presentation.web.schemas import APIModel, problem_responses
from archcompass.workflow.runs import RunState
from archcompass.workflow.service import SubmittedAnswer


class ReviewRequest(APIModel):
    case_id: str = Field(min_length=1)
    repository_root: str = Field(min_length=1)
    case_revision: int | None = Field(default=None, ge=1)
    ci: bool = False


class ReviewRunResponse(APIModel):
    """A review in flight, addressable as the revision it is going to be.

    Every identifier a review is filed under is known before the review exists: the
    repository, the branch, the case, and — from the newest review on that branch — the
    sequence this one will take. So a run is not an anonymous job with a thread id; it is
    revision N of a lineage a reader can already see, and it is addressed as one.

    What is genuinely absent is the composed review: its atlas, its findings, its delta. A
    client shows the run's progress in their place rather than a review with empty fields,
    and `review_id` appears the moment there is a real record to move to — which is before
    the run finishes.
    """

    run_id: str
    status: str
    review_id: str | None
    stage: str
    stages: list[str]
    failure: str
    #: The lineage this run belongs to. Names for a reader, ids so a client can tell that a
    #: run and a review it is looking at are the same line of work.
    repository_name: str = ""
    repository_root: str = ""
    branch_name: str = ""
    branch_id: str = ""
    case_id: str = ""
    #: Which revision this will be. Derived from the newest review on the branch, so it is
    #: the number the composed review will carry rather than a placeholder.
    sequence: int = 1

    @classmethod
    def from_state(cls, state: RunState, **lineage: object) -> ReviewRunResponse:
        """The run's own state, with whatever the lineage lookup could add to it.

        The lineage is optional so a run whose execution row has gone still answers with
        the half that lives in memory, rather than failing the read that was going to tell
        somebody their review had finished.
        """

        return cls(
            run_id=state.run_id,
            status=state.status,
            review_id=state.review_id,
            stage=state.stage,
            stages=list(state.stages),
            failure=state.failure,
            **cast("dict[str, Any]", lineage),
        )


class SubmittedAnswerRequest(APIModel):
    question_id: str = Field(min_length=1)
    status: AnswerStatus
    value: str | None = Field(default=None, max_length=4000)
    actor: str = Field(default="user", min_length=1)


class ReviewAnswersRequest(APIModel):
    answers: list[SubmittedAnswerRequest] = Field(
        default_factory=lambda: list[SubmittedAnswerRequest]()
    )
    stop: bool = False


class SourceLocationResponse(APIModel):
    path: str
    start_line: int
    end_line: int


class EvidenceResponse(APIModel):
    description: str
    location: SourceLocationResponse | None
    excerpt: str | None


class ParticipantResponse(APIModel):
    qualified_name: str
    role: str


class CandidateResponse(APIModel):
    id: str
    pattern: str
    summary: str
    participants: list[ParticipantResponse]
    evidence: list[EvidenceResponse]
    measurements: dict[str, str]
    detection_rationale: str
    limitations: str


class PolicyBearingResponse(APIModel):
    policy_id: str
    policy_title: str
    reasoning: str


class FindingResponse(APIModel):
    candidate: CandidateResponse
    verdict: str
    reasoning: str
    policies: list[PolicyBearingResponse]
    evidence: list[EvidenceResponse]
    hinge: str | None
    recommended_response: str | None
    reused_from_review_id: str | None
    model_identity: str
    prompt_identity: str
    retrieval_identity: str


class QuestionResponse(APIModel):
    id: str
    text: str
    facet: str
    candidate_ids: list[str]
    round: int
    equivalence_key: str


class AnswerResponse(APIModel):
    question: QuestionResponse
    status: str
    value: str | None
    actor: str
    answered_at: str


class CaseConstraintResponse(APIModel):
    text: str
    facet: str
    source: str | None


class CaseDecisionResponse(APIModel):
    text: str
    source: str | None


class CaseResponse(APIModel):
    id: str
    revision: int
    goal: str
    constraints: list[CaseConstraintResponse]
    decisions: list[CaseDecisionResponse]
    answers: list[AnswerResponse]
    created_at: str
    updated_at: str


class RepositoryResponse(APIModel):
    id: str
    path: str
    branch_id: str
    content_id: str
    remote_url: str | None
    branch: str | None
    commit: str | None


class AtlasResponse(APIModel):
    id: str
    repository: RepositoryResponse
    node_count: int
    edge_count: int
    metric_count: int
    fact_count: int
    signal_count: int
    parser_configuration: dict[str, str]


class CandidateChangeResponse(APIModel):
    candidate_id: str
    causes: list[str]
    predecessor_id: str | None


class AddressedCandidateResponse(APIModel):
    candidate_id: str
    title: str
    last_seen_review_id: str
    last_verdict: str


class DeltaResponse(APIModel):
    unchanged: list[str]
    changed: list[CandidateChangeResponse]
    new: list[str]
    addressed: list[AddressedCandidateResponse]


class RetrievalProvenanceResponse(APIModel):
    candidate_id: str
    retriever: str
    version: str
    corpus_fingerprint: str
    selected_policy_ids: list[str]
    model_identity: str | None
    query_fingerprint: str | None
    metadata: dict[str, str]


def _evidence(value: Evidence) -> EvidenceResponse:
    return EvidenceResponse(
        description=value.description,
        location=(
            None
            if value.location is None
            else SourceLocationResponse(
                path=value.location.path,
                start_line=value.location.start_line,
                end_line=value.location.end_line,
            )
        ),
        excerpt=value.excerpt,
    )


def _candidate(value: Candidate) -> CandidateResponse:
    return CandidateResponse(
        id=str(value.id),
        pattern=value.pattern,
        summary=value.summary,
        participants=[
            ParticipantResponse(
                qualified_name=item.qualified_name,
                role=item.role,
            )
            for item in value.participants
        ],
        evidence=[_evidence(item) for item in value.evidence],
        measurements=dict(value.measurements),
        detection_rationale=value.detection_rationale,
        limitations=value.limitations,
    )


class ReviewResponse(APIModel):
    """Complete, typed HTTP projection of one immutable review snapshot."""

    id: str
    sequence: int
    status: str
    previous_review_id: str | None
    repository: RepositoryResponse
    atlas: AtlasResponse
    case: CaseResponse
    findings: list[FindingResponse]
    questions: list[QuestionResponse]
    delta: DeltaResponse
    retrieval_manifest: list[RetrievalProvenanceResponse]
    markdown_report: str | None
    model_identity: str
    prompt_identity: str
    started_at: str
    finished_at: str | None
    failure: str | None

    @classmethod
    def from_domain(cls, review: Review) -> ReviewResponse:
        repository = RepositoryResponse(
            id=review.repository.id,
            path=str(review.repository.path),
            branch_id=review.repository.branch_id,
            content_id=review.repository.content_id,
            remote_url=review.repository.remote_url,
            branch=review.repository.branch,
            commit=review.repository.commit,
        )
        questions = {
            item.id: QuestionResponse(
                id=item.id,
                text=item.text,
                facet=item.facet.value,
                candidate_ids=list(item.candidate_ids),
                round=item.round,
                equivalence_key=item.equivalence_key,
            )
            for item in review.questions
        }
        case_questions = {
            item.question.id: QuestionResponse(
                id=item.question.id,
                text=item.question.text,
                facet=item.question.facet.value,
                candidate_ids=list(item.question.candidate_ids),
                round=item.question.round,
                equivalence_key=item.question.equivalence_key,
            )
            for item in review.case.answers
        }
        return cls(
            id=review.id,
            sequence=review.sequence,
            status=review.status.value,
            previous_review_id=review.previous_review_id,
            repository=repository,
            atlas=AtlasResponse(
                id=review.atlas.id,
                repository=repository,
                node_count=len(review.atlas.nodes),
                edge_count=len(review.atlas.edges),
                metric_count=len(review.atlas.metrics),
                fact_count=len(review.atlas.facts),
                signal_count=len(review.atlas.signals),
                parser_configuration=dict(review.atlas.parser_configuration),
            ),
            case=CaseResponse(
                id=review.case.id,
                revision=review.case.revision,
                goal=review.case.goal,
                constraints=[
                    CaseConstraintResponse(
                        text=item.text,
                        facet=item.facet.value,
                        source=item.source,
                    )
                    for item in review.case.constraints
                ],
                decisions=[
                    CaseDecisionResponse(text=item.text, source=item.source)
                    for item in review.case.decisions
                ],
                answers=[
                    AnswerResponse(
                        question=case_questions[item.question.id],
                        status=item.status.value,
                        value=item.value,
                        actor=item.actor,
                        answered_at=item.answered_at.isoformat(),
                    )
                    for item in review.case.answers
                ],
                created_at=review.case.created_at.isoformat(),
                updated_at=review.case.updated_at.isoformat(),
            ),
            findings=[
                FindingResponse(
                    candidate=_candidate(item.candidate),
                    verdict=item.verdict.value,
                    reasoning=item.reasoning,
                    policies=[
                        PolicyBearingResponse(
                            policy_id=bearing.policy.id,
                            policy_title=bearing.policy.title,
                            reasoning=bearing.reasoning,
                        )
                        for bearing in item.policies
                    ],
                    evidence=[_evidence(evidence) for evidence in item.evidence],
                    hinge=item.hinge,
                    recommended_response=item.recommended_response,
                    reused_from_review_id=item.reused_from_review_id,
                    model_identity=item.model_identity,
                    prompt_identity=item.prompt_identity,
                    retrieval_identity=item.retrieval_identity,
                )
                for item in review.findings
            ],
            questions=[questions[item.id] for item in review.questions],
            delta=DeltaResponse(
                unchanged=[str(item.id) for item in review.delta.unchanged],
                changed=[
                    CandidateChangeResponse(
                        candidate_id=str(item.candidate.id),
                        causes=[cause.value for cause in item.causes],
                        predecessor_id=(
                            None if item.predecessor_id is None else str(item.predecessor_id)
                        ),
                    )
                    for item in review.delta.changed
                ],
                new=[str(item.id) for item in review.delta.new],
                addressed=[
                    AddressedCandidateResponse(
                        candidate_id=str(item.candidate_id),
                        title=item.title,
                        last_seen_review_id=item.last_seen_review_id,
                        last_verdict=item.last_verdict.value,
                    )
                    for item in review.delta.addressed
                ],
            ),
            retrieval_manifest=[
                RetrievalProvenanceResponse(
                    candidate_id=str(item.candidate_id),
                    retriever=item.retriever,
                    version=item.version,
                    corpus_fingerprint=item.corpus_fingerprint,
                    selected_policy_ids=list(item.selected_policy_ids),
                    model_identity=item.model_identity,
                    query_fingerprint=item.query_fingerprint,
                    metadata=dict(item.metadata),
                )
                for item in review.retrieval_manifest
            ],
            markdown_report=review.markdown_report,
            model_identity=review.model_identity,
            prompt_identity=review.prompt_identity,
            started_at=review.started_at.isoformat(),
            finished_at=(
                None if review.finished_at is None else review.finished_at.isoformat()
            ),
            failure=review.failure,
        )


def _identity(runtime: Runtime, root: str) -> tuple[str, str]:
    return runtime.atlas_service.repository_identity(Path(root))


def routes() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/reviews",
        status_code=201,
        dependencies=[SpendsModelBudget],
        responses=problem_responses(404, 422, 503),
    )
    def create_review(runtime: RuntimeDep, request: ReviewRequest) -> ReviewResponse:
        repository_id, branch_id = _identity(runtime, request.repository_root)
        review = runtime.review_workflow_service.start(
            repository_id=repository_id,
            branch_id=branch_id,
            case_id=request.case_id,
            case_revision=request.case_revision,
            ci=request.ci,
        )
        return ReviewResponse.from_domain(review)

    def _describe_run(run_id: str, runtime: Runtime) -> ReviewRunResponse:
        """A run as the revision it will be: its lineage, and the number it will carry.

        Assembled here rather than in the workflow service because it joins two things the
        service has no reason to know about each other — the execution row and the lineage
        names — and a listing entry and a single read must not describe the same run
        differently.
        """

        state = runtime.review_workflow_service.run_state(run_id)
        lineage = runtime.review_workflow_service.lineage_of(run_id)
        if lineage is None:
            return ReviewRunResponse.from_state(state)
        repositories = runtime.lineage_repository
        repository = repositories.repository(lineage.repository_id)
        branch = repositories.get_branch(lineage.branch_id)
        root = repository.canonical_root if repository else ""
        # The sequence the composed review will carry, taken from the newest review on the
        # branch rather than guessed: a first review is 1, and every later one follows the
        # review it is about to be compared against.
        previous = runtime.review_workflow_service.latest_for_branch(lineage.branch_id)
        return ReviewRunResponse.from_state(
            state,
            repository_name=Path(root).name if root else "this repository",
            repository_root=root,
            branch_name=branch.branch_name if branch else "",
            branch_id=lineage.branch_id,
            case_id=lineage.case_id,
            sequence=(previous.sequence + 1) if previous else 1,
        )

    @router.post(
        "/api/reviews/runs",
        status_code=202,
        dependencies=[SpendsModelBudget],
        responses=problem_responses(404, 422, 503),
    )
    def start_review_run(runtime: RuntimeDep, request: ReviewRequest) -> ReviewRunResponse:
        """Start a review and answer with something to come back to.

        202 rather than 201: nothing has been created yet except the intention to review,
        and the review this produces is addressable through the run until it exists.
        """

        repository_id, branch_id = _identity(runtime, request.repository_root)
        state = runtime.review_workflow_service.start_background(
            repository_id=repository_id,
            branch_id=branch_id,
            case_id=request.case_id,
            case_revision=request.case_revision,
            ci=request.ci,
        )
        return _describe_run(state.run_id, runtime)

    @router.get("/api/reviews/runs/{run_id}", responses=problem_responses(404))
    def read_review_run(runtime: RuntimeDep, run_id: str) -> ReviewRunResponse:
        return _describe_run(run_id, runtime)

    @router.post(
        "/api/reviews/stream",
        response_class=StreamingResponse,
        dependencies=[SpendsModelBudget],
    )
    def stream_review(runtime: RuntimeDep, request: ReviewRequest) -> StreamingResponse:
        def lines() -> Iterator[str]:
            try:
                repository_id, branch_id = _identity(runtime, request.repository_root)
                for progress in runtime.review_workflow_service.start_stream(
                    repository_id=repository_id,
                    branch_id=branch_id,
                    case_id=request.case_id,
                    case_revision=request.case_revision,
                    ci=request.ci,
                ):
                    event: dict[str, object] = {"event": progress.stage}
                    if progress.review is not None:
                        event["review"] = ReviewResponse.from_domain(
                            progress.review
                        ).model_dump(mode="json")
                    yield json.dumps(event, separators=(",", ":")) + "\n"
            except Exception as error:  # The response has already begun; failure is an event.
                yield json.dumps(
                    {"event": "failed", "message": str(error)},
                    separators=(",", ":"),
                ) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    @router.post(
        "/api/reviews/{review_id}/answers",
        responses=problem_responses(404, 409, 422, 503),
    )
    def answer_review(
        runtime: RuntimeDep, review_id: str, request: ReviewAnswersRequest
    ) -> ReviewResponse:
        review = runtime.review_workflow_service.resume(
            review_id,
            tuple(
                SubmittedAnswer(item.question_id, item.status, item.value, item.actor)
                for item in request.answers
            ),
            stop=request.stop,
        )
        return ReviewResponse.from_domain(review)

    @router.get("/api/reviews/runs")
    def list_review_runs(
        runtime: RuntimeDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[ReviewRunResponse]:
        """Every run that has begun and has no review yet.

        Registered above `/api/reviews/{review_id}` so `runs` is not read as an id.

        This exists because a run was only ever addressable by an id somebody was already
        holding: start a review, navigate away, and there was no way back to it short of the
        browser's history. A batch judgement takes as long as a batch takes, which makes
        "navigate away" the ordinary case rather than the careless one.
        """

        return [
            _describe_run(execution.thread_id, runtime)
            for execution in runtime.review_workflow_service.in_flight(limit=limit)
        ]

    @router.get("/api/reviews")
    def list_reviews(
        runtime: RuntimeDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[ReviewResponse]:
        return [
            ReviewResponse.from_domain(item)
            for item in runtime.review_workflow_service.list(limit=limit)
        ]

    @router.get("/api/reviews/{review_id}", responses=problem_responses(404, 422))
    def get_review(runtime: RuntimeDep, review_id: str) -> ReviewResponse:
        return ReviewResponse.from_domain(runtime.review_workflow_service.get(review_id))

    @router.get("/api/reviews/{review_id}/source", responses=problem_responses(404, 422))
    def get_review_source(
        runtime: RuntimeDep, review_id: str
    ) -> list[EvidenceResponse]:
        review = runtime.review_workflow_service.get(review_id)
        return [
            _evidence(evidence)
            for finding in review.findings
            for evidence in finding.evidence
        ]

    @router.get(
        "/api/reviews/{review_id}/report",
        response_class=Response,
        responses=problem_responses(404, 409, 422),
    )
    def get_review_report(runtime: RuntimeDep, review_id: str) -> Response:
        review = runtime.review_workflow_service.get(review_id)
        if review.markdown_report is None:
            raise ReviewHasNoReportError(f"Review {review_id} has no rendered report")
        return Response(review.markdown_report, media_type="text/markdown")

    @router.post(
        "/api/reviews/{review_id}/cancel", responses=problem_responses(404, 409, 422)
    )
    def cancel_review(runtime: RuntimeDep, review_id: str) -> ReviewResponse:
        return ReviewResponse.from_domain(runtime.review_workflow_service.cancel(review_id))

    @router.delete(
        "/api/reviews/{review_id}", status_code=204, responses=problem_responses(404, 409)
    )
    def delete_review(runtime: RuntimeDep, review_id: str) -> Response:
        runtime.review_workflow_service.delete(review_id)
        return Response(status_code=204)

    return router
