"""Pydantic HTTP boundary for the clean-break review workflow."""

# FastAPI decorator registration is the use of the nested route functions.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Query, Response
from pydantic import Field

from archcompass.bootstrap import Runtime
from archcompass.domain import (
    AnswerStatus,
    Candidate,
    Evidence,
    RecordedInvestigation,
    RepositoryRef,
    Review,
    ReviewStatus,
    Termination,
)
from archcompass.domain.errors import ReviewHasNoReportError
from archcompass.persistence.ports import ReviewSummary
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
    repository, the branch, the case, and the sequence this one will take. So a run is not
    an anonymous job with a thread id; it is revision N of a lineage a reader can already
    see, and it is addressed as one.

    The sequence comes from the snapshot the run has already filed wherever there is one,
    and only otherwise from the newest review on the branch plus one. The distinction is
    the whole of the one-review-one-number rule seen from here: a run that has asked a
    question has filed a waiting snapshot, and asking `latest + 1` after that would answer
    with the number *after* its own.

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
    #: Judging is a loop, and a stage list cannot say how deep into one a run is. These can:
    #: the selection this round made, and how much of it now has a verdict. Both zero before
    #: a round has selected anything, which is what a client reads as "no count to show yet".
    candidates_to_judge: int = 0
    candidates_judged: int = 0
    candidates_retrieved: int = 0
    #: The lineage this run belongs to. Names for a reader, ids so a client can tell that a
    #: run and a review it is looking at are the same line of work.
    repository_name: str = ""
    repository_root: str = ""
    #: The folders this repository is reviewed without, so a client that has the run has the
    #: whole of what it was started with. `root` alone was half an answer: "Start again"
    #: after a failed run carried the repository and dropped the scope, so ten minutes of
    #: ticking folders was lost to a run that broke on its first stage.
    #:
    #: Empty covers both of the ways nothing is left out — nobody has narrowed this
    #: repository, and somebody chose to review the whole of it — because a caller listing
    #: what a run skipped has the same thing to say about either.
    excluded_paths: list[str] = Field(default_factory=list[str])
    branch_name: str = ""
    branch_id: str = ""
    case_id: str = ""
    #: Which revision this is. Taken from the snapshot this run has already filed, and
    #: otherwise from the newest review on the branch plus one — so it is the number the
    #: composed review will carry rather than a placeholder, and it does not move when the
    #: run files a second snapshot for its next round.
    sequence: int = 1
    #: When this process started the run, so a page watching one can say how long it has
    #: been. `None` where the run was started by a process that has since gone: the start
    #: time lives in memory beside the stages, and inventing one after a restart would put a
    #: number on screen that counts from the restart rather than from the work.
    started_at: str | None = None

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
            candidates_to_judge=state.candidates_to_judge,
            candidates_judged=state.candidates_judged,
            candidates_retrieved=state.candidates_retrieved,
            started_at=(None if state.started_at is None else state.started_at.isoformat()),
            **cast("dict[str, Any]", lineage),
        )


class SubmittedAnswerRequest(APIModel):
    question_id: str = Field(min_length=1)
    status: AnswerStatus
    value: str | None = Field(default=None, max_length=4000)
    actor: str = Field(default="user", min_length=1)
    #: The model that drafted this exact value, where the reviewer accepted a draft
    #: unchanged. Empty wherever the words are theirs — typed, picked from the offered
    #: options, or edited from a draft before submitting.
    #:
    #: The client decides it because the client is the only party that saw both the draft
    #: and what was submitted. A server that inferred it would be guessing at authorship.
    drafted_by: str = Field(default="", max_length=200)


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
    note: str | None


class MeasurementResponse(APIModel):
    name: str
    value: float
    unit: str
    nature: str
    definition: str
    limitations: str


class RelationshipResponse(APIModel):
    source: str
    target: str
    kind: str
    resolved_by: str


class ParticipantResponse(APIModel):
    qualified_name: str
    role: str
    #: The atlas node this participant was detected on, where the detection recorded one.
    #: `None` for a finding judged before the id was carried, and for anything a rebuilt
    #: atlas no longer holds — a map reading this must draw around its absence.
    node_id: str | None = None


class CandidateResponse(APIModel):
    id: str
    pattern: str
    summary: str
    participants: list[ParticipantResponse]
    evidence: list[EvidenceResponse]
    measurements: list[MeasurementResponse]
    relationships: list[RelationshipResponse]
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
    investigation_identity: str


class QuestionResponse(APIModel):
    id: str
    text: str
    facet: str
    candidate_ids: list[str]
    round: int
    equivalence_key: str
    # Answers the model proposed. Empty means it had none worth offering, not that the
    # question is closed — an answer is free text however it was chosen.
    options: list[str]


class AnswerResponse(APIModel):
    question: QuestionResponse
    status: str
    value: str | None
    actor: str
    answered_at: str
    #: Which case revision this answer was recorded on — the review that asked it, said the
    #: only way a case can say it. With `question.round` it addresses a round exactly: round
    #: is unique inside a review and repeats across a case's life, because a review keeps one
    #: revision however many rounds it asks. Zero on an answer recorded before this was
    #: stamped, which a reader groups under the case rather than under a round.
    case_revision: int = 0
    #: The model that drafted this answer's exact words, where the reviewer accepted a draft
    #: unchanged. Empty on every answer whose words are their own, which is most of them.
    drafted_by: str = ""


class CaseResponse(APIModel):
    id: str
    revision: int
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
        note=value.note,
    )


def _repository(value: RepositoryRef) -> RepositoryResponse:
    return RepositoryResponse(
        id=value.id,
        path=str(value.path),
        branch_id=value.branch_id,
        content_id=value.content_id,
        remote_url=value.remote_url,
        branch=value.branch,
        commit=value.commit,
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
                node_id=item.node_id,
            )
            for item in value.participants
        ],
        evidence=[_evidence(item) for item in value.evidence],
        measurements=[
            MeasurementResponse(
                name=item.name,
                value=item.value,
                unit=item.unit,
                nature=item.nature.value,
                definition=item.definition,
                limitations=item.limitations,
            )
            for item in value.measurements
        ],
        relationships=[
            RelationshipResponse(
                source=item.source,
                target=item.target,
                kind=item.kind,
                resolved_by=item.resolved_by,
            )
            for item in value.relationships
        ],
        detection_rationale=value.detection_rationale,
        limitations=value.limitations,
    )


class InvestigationLookupResponse(APIModel):
    tool: str
    arguments: dict[str, str]
    result: str


class RecordedInvestigationResponse(APIModel):
    """What one hinged finding checked against the repository before the review asked.

    No `identity` field, following `RetrievalProvenanceResponse`: a reader joins these to
    findings on `candidate_id`, and the hash a finding carries is the one thing that has to
    be on the finding.
    """

    candidate_id: str
    lookups: list[InvestigationLookupResponse]
    closing: str
    withheld: str
    #: Why the looking stopped. `null` says only that it was not recorded — true of every
    #: investigation stored before this field existed — and never that it ended naturally.
    #: A reader must render it as unknown rather than as completion.
    termination: Termination | None
    atlas_fingerprint: str
    prompt_identity: str
    model_identity: str


def investigation_response(
    value: RecordedInvestigation | None,
) -> RecordedInvestigationResponse | None:
    """One investigation for the wire, or None where nothing looked."""

    if value is None:
        return None
    return RecordedInvestigationResponse(
        candidate_id=str(value.candidate_id),
        lookups=[
            InvestigationLookupResponse(
                tool=lookup.tool,
                arguments=dict(lookup.arguments),
                result=lookup.result,
            )
            for lookup in value.lookups
        ],
        closing=value.closing,
        withheld=value.withheld,
        termination=value.termination,
        atlas_fingerprint=value.atlas_fingerprint,
        prompt_identity=value.prompt_identity,
        model_identity=value.model_identity,
    )


class ReviewResponse(APIModel):
    """Complete, typed HTTP projection of one immutable review snapshot."""

    id: str
    sequence: int
    #: Which clarification round of this revision the snapshot was taken in. A revision that
    #: asked and was answered has a snapshot per round under one `sequence`, so a client
    #: comparing two reviews needs this to tell "the same revision, later" from "the next
    #: revision".
    round: int
    status: str
    previous_review_id: str | None
    repository: RepositoryResponse
    atlas: AtlasResponse
    case: CaseResponse
    findings: list[FindingResponse]
    questions: list[QuestionResponse]
    delta: DeltaResponse
    retrieval_manifest: list[RetrievalProvenanceResponse]
    investigation_manifest: list[RecordedInvestigationResponse]
    # No `markdown_report`. It is twenty kilobytes of Markdown on every review in every
    # listing, and the one surface that renders it fetches it from
    # `/api/reviews/{id}/report` — which is where a document that is read as a document
    # belongs, and which is still here.
    synopsis: str | None
    synopsis_identity: str
    model_identity: str
    prompt_identity: str
    started_at: str
    finished_at: str | None
    failure: str | None
    #: Whether this snapshot is the round still waiting for an answer, rather than one that
    #: was answered and superseded.
    #:
    #: `status` cannot say this and should not be asked to. A review is immutable, so a
    #: snapshot that asked says `awaiting_answers` for ever — a true statement about the
    #: moment it was recorded, and not a statement about now. A client reading it as one drew
    #: an answer form on a round that had already been answered and was being judged, and
    #: submitting it did nothing: the server refuses a submission written against a
    #: superseded snapshot, which is the right answer to a request that should never have
    #: been offered.
    #:
    #: So this is the execution's answer to the same question, and the two facts behind it
    #: are the two `_resume_command` checks: the round is open, and this snapshot is the one
    #: it is open on. False on every review that is not waiting at all, which is most of
    #: them.
    answerable: bool = False
    #: The snapshot that replaced this one, where this is not the newest of its revision.
    #:
    #: A review is immutable and a revision is recorded once per round, so review 2 can be
    #: three records: the round it first asked in, the round it asked again in, and the one
    #: it finished as. Only the last is in the listing — that is one entry per revision, and
    #: it is right — which leaves the earlier two reachable by their own URLs and by nothing
    #: else. A reader holding one of those URLs was shown a review waiting on a question that
    #: had been answered hours ago, with a report composed before the answers existed, and
    #: nothing on the page said so or pointed anywhere.
    #:
    #: `answerable` cannot carry this. It says whether the round is open, and both a
    #: superseded snapshot and a finished review answer `false` to that while needing
    #: opposite things said about them: one is history with a successor to read, the other is
    #: the review itself.
    superseded_by: str | None = None
    #: What became of that snapshot: `completed`, `cancelled`, `failed`, or `awaiting_answers`
    #: where the review went on to ask again.
    #:
    #: Carried beside the id because the id alone cannot support a true sentence. A waiting
    #: snapshot is superseded by two different acts — its round was answered, or somebody
    #: stopped the review — and both leave it saying `awaiting_answers` with a successor. A
    #: surface told only that a successor exists has to guess, and it guessed "answered",
    #: which told a reader who had stopped the review that their question had been answered.
    superseded_by_status: str | None = None

    @classmethod
    def from_domain(
        cls,
        review: Review,
        *,
        answerable: bool = False,
        superseded_by: str | None = None,
        superseded_by_status: str | None = None,
    ) -> ReviewResponse:
        repository = _repository(review.repository)
        questions = {
            item.id: QuestionResponse(
                id=item.id,
                text=item.text,
                facet=item.facet.value,
                candidate_ids=list(item.candidate_ids),
                round=item.round,
                equivalence_key=item.equivalence_key,
                options=list(item.options),
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
                options=list(item.question.options),
            )
            for item in review.case.answers
        }
        return cls(
            id=review.id,
            sequence=review.sequence,
            round=review.round,
            status=review.status.value,
            answerable=answerable,
            superseded_by=superseded_by,
            superseded_by_status=superseded_by_status,
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
                answers=[
                    AnswerResponse(
                        question=case_questions[item.question.id],
                        status=item.status.value,
                        value=item.value,
                        actor=item.actor,
                        answered_at=item.answered_at.isoformat(),
                        case_revision=item.case_revision,
                        drafted_by=item.drafted_by,
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
                    investigation_identity=item.investigation_identity,
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
            investigation_manifest=[
                response
                for item in review.investigation_manifest
                if (response := investigation_response(item)) is not None
            ],
            synopsis=review.synopsis,
            synopsis_identity=review.synopsis_identity,
            model_identity=review.model_identity,
            prompt_identity=review.prompt_identity,
            started_at=review.started_at.isoformat(),
            finished_at=(
                None if review.finished_at is None else review.finished_at.isoformat()
            ),
            failure=review.failure,
        )


class ReviewSummaryResponse(APIModel):
    """One review as a listing shows it, and nothing else.

    Eight screens list reviews. Between them they read a repository name, a branch, a
    number, a case revision, two timestamps and a few counts — and every one of them was
    served the whole review to find them, atlas included. So this is the listing shape:
    the same identity and the same lineage as `ReviewResponse`, with the counts in place
    of the collections they are counts of.

    Not a `ReviewResponse` with fields omitted, because the two are read differently and a
    reader holding one has to know which it is. The counts are named for what they count
    rather than nested, so a listing reads `material_count` instead of filtering an array
    that is not there.
    """

    id: str
    sequence: int
    round: int
    status: str
    previous_review_id: str | None
    repository: RepositoryResponse
    case_id: str
    case_revision: int
    #: How many questions the case this review ran against carries answers to. Here rather
    #: than left to be counted off the review, because a screen deciding what a run will
    #: continue prints it — and reading the whole review for one integer is the download this
    #: projection exists to avoid.
    answer_count: int
    started_at: str
    finished_at: str | None
    #: How many candidates this review judged, and how each verdict fell. `finding_count` is
    #: their sum and is carried anyway: it is the number a listing prints, and deriving it
    #: from three others is arithmetic on the wrong side of the wire.
    finding_count: int
    material_count: int
    held_count: int
    cleared_count: int
    #: Questions this review is waiting on. Zero for every review that settled without
    #: asking, which is not the same as a review whose questions have all been answered —
    #: that one is `completed` and has none pending either.
    question_count: int
    #: The delta, as the four numbers a listing states it in. The candidates themselves are
    #: on the review, which is where a reader goes to see what moved.
    unchanged_count: int
    changed_count: int
    new_count: int
    addressed_count: int

    @classmethod
    def from_summary(cls, summary: ReviewSummary) -> ReviewSummaryResponse:
        return cls(
            id=summary.id,
            sequence=summary.sequence,
            round=summary.round,
            status=summary.status,
            previous_review_id=summary.previous_review_id,
            repository=_repository(summary.repository),
            case_id=summary.case_id,
            case_revision=summary.case_revision,
            answer_count=summary.answer_count,
            started_at=summary.started_at.isoformat(),
            finished_at=(
                None if summary.finished_at is None else summary.finished_at.isoformat()
            ),
            finding_count=summary.finding_count,
            material_count=summary.material_count,
            held_count=summary.held_count,
            cleared_count=summary.cleared_count,
            question_count=summary.question_count,
            unchanged_count=summary.unchanged_count,
            changed_count=summary.changed_count,
            new_count=summary.new_count,
            addressed_count=summary.addressed_count,
        )


def _identity(runtime: Runtime, root: str) -> tuple[str, str]:
    return runtime.atlas_service.repository_identity(Path(root))


def _submitted(request: ReviewAnswersRequest) -> tuple[SubmittedAnswer, ...]:
    """One round of answers as the workflow takes them, however the caller will wait."""

    return tuple(
        SubmittedAnswer(
            item.question_id, item.status, item.value, item.actor, item.drafted_by
        )
        for item in request.answers
    )


def _projected(runtime: Runtime, review: Review) -> ReviewResponse:
    """One review as a client reads it, including whether it can still be answered.

    The status is checked first and it is not a redundant guard: `is_answerable` reads two
    rows, a listing is a hundred reviews, and all but one of them are settled. Asking the
    execution store about a completed review from last week to be told "no" is a hundred
    lookups to reach the answer its own status already gave.
    """

    workflow = runtime.review_workflow_service
    # Asked once and passed on rather than resolved twice: a listing is a hundred rows, and
    # the successor's status is a read of the successor rather than of this review.
    superseding = workflow.superseding_review_of(review.id)
    # Advertised only where it can actually be read. `delete` removes a snapshot and leaves the
    # execution's `current_review_id` naming it, so the id survives its record: published on its
    # own it was a successor that answered 404, under a banner inviting somebody to go and read
    # it. Being able to say what became of it is the same question as being able to open it.
    superseding_status = workflow.status_of(superseding) if superseding else None
    return ReviewResponse.from_domain(
        review,
        answerable=(
            review.status is ReviewStatus.AWAITING_ANSWERS
            and workflow.is_answerable(review.id)
        ),
        superseded_by=superseding if superseding_status else None,
        superseded_by_status=superseding_status,
    )


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
        return _projected(runtime, review)

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
        # A run that has already composed a snapshot carries that snapshot's number: it is
        # the revision, not the one before it. Only a run with nothing filed yet has to be
        # told what number it is going to take.
        sequence = None
        if state.review_id is not None:
            sequence = runtime.review_workflow_service.sequence_of(state.review_id)
        if sequence is None:
            previous = runtime.review_workflow_service.latest_for_branch(lineage.branch_id)
            sequence = (previous.sequence + 1) if previous else 1
        return ReviewRunResponse.from_state(
            state,
            repository_name=Path(root).name if root else "this repository",
            repository_root=root,
            # Read by the same path the line above answers with, so the two travel together:
            # a client handed a root and somebody else's folder list would start the next run
            # against a scope that was never chosen for it.
            excluded_paths=list(runtime.repository_service.scope(root)) if root else [],
            branch_name=branch.branch_name if branch else "",
            branch_id=lineage.branch_id,
            case_id=lineage.case_id,
            sequence=sequence,
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
        "/api/reviews/runs/{run_id}/cancel", responses=problem_responses(404)
    )
    def cancel_review_run(runtime: RuntimeDep, run_id: str) -> ReviewRunResponse:
        """Stop a run somebody no longer wants, and answer with what became of it.

        200 rather than 204, because the answer is the run: it keeps its id, its stages and
        whatever review it had already filed, under the status `cancelled`. A person who
        started a review of the wrong repository could otherwise only wait it out.

        Not idempotent in the sense of doing nothing twice — cancelling a run that has
        already finished still writes `cancelled` over the row — so a caller that means
        "stop this" reads the answer rather than assuming it.
        """

        state = runtime.review_workflow_service.cancel_run(run_id)
        return _describe_run(state.run_id, runtime)

    @router.post(
        "/api/reviews/{review_id}/answers",
        responses=problem_responses(404, 409, 422, 503),
    )
    def answer_review(
        runtime: RuntimeDep, review_id: str, request: ReviewAnswersRequest
    ) -> ReviewResponse:
        """Answer a clarification round and wait for the rejudgement in this request.

        Kept beside the run below for a caller that reads a review out of one call and has
        nowhere to come back to — a script, or a CI step driving the API. A browser should
        use the run: this holds a connection open for the length of a full rejudgement.

        Not for the CLI, which this used to name: it makes no HTTP calls at all and drives
        `Runtime` directly.
        """

        review = runtime.review_workflow_service.resume(
            review_id,
            _submitted(request),
            stop=request.stop,
        )
        return _projected(runtime, review)

    @router.post(
        "/api/reviews/{review_id}/answers/runs",
        status_code=202,
        # No `SpendsModelBudget`, matching the route above it. The budget admits a review,
        # and this is a review that was already admitted reaching its end — a demo that
        # charged again for each clarification round would ration finishing rather than
        # starting, and would stop a review it had already agreed to.
        responses=problem_responses(404, 409, 422, 503),
    )
    def answer_review_run(
        runtime: RuntimeDep, review_id: str, request: ReviewAnswersRequest
    ) -> ReviewRunResponse:
        """Answer a clarification round and get a run to watch it on.

        The same fix `POST /api/reviews/runs` was for, on the other half of a review.
        Answering rejudges every extant candidate, which is minutes of model work, and it
        used to happen inside this request — so a reload, a closed laptop or a proxy's idle
        timeout left the person unable to tell whether their answers had been recorded.

        202, and the run is the one the review has been on all along: same thread id, same
        address, so `/api/reviews/runs/{id}` keeps working across the whole review. The
        answers are still validated here, where a question that does not exist can be
        refused properly rather than becoming a failed run.
        """

        state = runtime.review_workflow_service.resume_background(
            review_id,
            _submitted(request),
            stop=request.stop,
        )
        return _describe_run(state.run_id, runtime)

    @router.get("/api/reviews/runs")
    def list_review_runs(
        runtime: RuntimeDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[ReviewRunResponse]:
        """Every run that has begun and has not finished.

        Registered above `/api/reviews/{review_id}` so `runs` is not read as an id.

        This exists because a run was only ever addressable by an id somebody was already
        holding: start a review, navigate away, and there was no way back to it short of the
        browser's history. Judging a repository takes as long as it takes, which makes
        "navigate away" the ordinary case rather than the careless one.

        A run stays here until it is genuinely done, `review_id` and all. It used to leave
        the moment a review was attached, which is several nodes before the end — so the
        progress marker vanished, the review was not in the reviews listing yet, and a
        client could not tell a run that had finished from one that had never existed.
        """

        return [
            _describe_run(execution.thread_id, runtime)
            for execution in runtime.review_workflow_service.in_flight(limit=limit)
        ]

    @router.get("/api/reviews")
    def list_reviews(
        runtime: RuntimeDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        view: Annotated[Literal["full", "summary"], Query()] = "full",
    ) -> list[ReviewResponse] | list[ReviewSummaryResponse]:
        """Every review, either whole or as a listing reads it.

        `view=summary` is the one to ask for unless the caller is going to render a review.
        A stored review is most of a repository's atlas, and the listing screens read a
        name, a number and a few counts off it — so the full view was several megabytes a
        row to produce a line of text, and the server decoded every one of those rows to
        count five integers off it. The summary is projected in SQL and never opens the
        document at all.

        One route with a view rather than two routes, because it is one listing: the rows
        and their order are the same either way, and only how much of each row travels
        differs.
        """

        if view == "summary":
            return [
                ReviewSummaryResponse.from_summary(item)
                for item in runtime.review_workflow_service.list_summaries(limit=limit)
            ]
        return [
            _projected(runtime, item)
            for item in runtime.review_workflow_service.list(limit=limit)
        ]

    @router.get("/api/reviews/{review_id}", responses=problem_responses(404, 422))
    def get_review(runtime: RuntimeDep, review_id: str) -> ReviewResponse:
        return _projected(runtime, runtime.review_workflow_service.get(review_id))

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
        return _projected(runtime, runtime.review_workflow_service.cancel(review_id))

    @router.delete(
        "/api/reviews/{review_id}", status_code=204, responses=problem_responses(404, 409)
    )
    def delete_review(runtime: RuntimeDep, review_id: str) -> Response:
        runtime.review_workflow_service.delete(review_id)
        return Response(status_code=204)

    return router
