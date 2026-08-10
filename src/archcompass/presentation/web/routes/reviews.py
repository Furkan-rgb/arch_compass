"""The routes that run and read reviews.

The centre of the API. A run is started here — once, either as a plain call or as a
watchable stream — and everything afterwards reads what it produced: the record, the code
it was measured from, the Markdown it was written as, and the answers a reader gives to the
questions it asked. Two routes move a review's own state rather than reading it: cancel and
delete.

What the team has since decided about a review's boundaries is joined on at read time, by
`_with_boundary_triage`. That join is the one place a decision meets a review, and it
happens after the fact on purpose — `ReviewService` never reads decisions, so nothing a
team concluded can reach the reasoning that produced a verdict.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query, Response
from pydantic import Field

from archcompass.application.cases import WrittenAnswer
from archcompass.application.review_source import MAX_CONTEXT_LINES
from archcompass.application.standings import standing_for
from archcompass.bootstrap import Runtime
from archcompass.domain.case import CaseRevision
from archcompass.domain.errors import (
    ReviewHasNoReportError,
    ReviewNotCancellableError,
    ReviewStillRunningError,
)
from archcompass.domain.fingerprint import boundary_fingerprint
from archcompass.domain.review import (
    BoundaryExcerpt,
    BoundaryReview,
    ReviewedBoundary,
    ReviewStatus,
)
from archcompass.domain.triage import DecisionState, StandingDecision
from archcompass.domain.workspace import BoundaryReviewSummary
from archcompass.presentation.web.dependencies import RuntimeDep, SpendsModelBudget
from archcompass.presentation.web.schemas import APIModel, problem_responses
from archcompass.presentation.web.streaming import (
    NDJSONStreamingResponse,
    ReviewProgress,
    review_progress_lines,
)


class ReviewRequest(APIModel):
    case_id: str = Field(min_length=1)
    repository_root: str = Field(min_length=1)
    #: The first pass whose questions produced this case revision, where this run is the
    #: second pass of an elicitation. Absent for every review that was not reached by
    #: answering, which is the ordinary start. Supplying it is what stops the run asking
    #: again: a second pass concludes rather than eliciting, and the loop terminates.
    elicited_from: str | None = Field(default=None, min_length=1)


class SubmittedAnswer(APIModel):
    """One answer: which question it settles, and what the reader typed before saving.

    No question and no destination. Both are the question's own properties, read from the
    review by the server — a client that could send the question could put words in a review's
    mouth, and one that could name the field could give an answer a weight its question never
    asked for, with nothing afterwards able to tell either apart from a question that did.

    `recorded_text` is the answer verbatim. It used to be a line the browser composed by
    joining the question's subject to the reply, because the case had nowhere to keep the pair;
    the case keeps pairs now (ADR 0014), so this is the reader's words and nothing else.
    """

    question_reference: str = Field(pattern=r"^Q-[0-9]+$")
    recorded_text: str = Field(min_length=1, max_length=4000)


class ReviewAnswersRequest(APIModel):
    #: Only the questions that were answered. Skipping is normal and is recorded as absence,
    #: so a blank entry is refused rather than stored as an answer nobody gave.
    answers: list[SubmittedAnswer] = Field(min_length=1)


class JoinedDecision(APIModel):
    """The current decision as a review's reader needs to see it."""

    decision_id: str
    state: DecisionState
    author: str
    reason: str | None = None
    decided_at: datetime
    #: False when this run's verdict for the boundary differs from the one the decision was
    #: taken against. Not an expiry — the decision still stands — but the reader is told the
    #: ground moved, and re-affirming it is a human act.
    taken_on_current_verdict: bool


class BoundaryTriage(APIModel):
    """What triage knows about one boundary of one review.

    Carried beside the report rather than inside it: a `ReviewedBoundary` is part of an
    immutable judgement, and joining a team's later opinion into that document would make the
    review look like it had changed its mind.
    """

    #: The `BR-nnn` this boundary has in this review — how a client matches it to the report.
    reference: str
    #: Its structural identity, which is what a decision is actually filed under.
    fingerprint: str
    #: Absent where nobody has decided, and for every review that predates branch lineages:
    #: with no branch there is nothing to look the decision up on.
    decision: JoinedDecision | None = None
    comment_count: int = 0


class ReviewDetailResponse(BoundaryReview):
    """A stored review as it is read, with what the team has since made of it.

    One join, and it is the only one left. The baseline comparison used to sit here too — a
    `new`/`changed`/`known` disposition per boundary, recomputed on every read — and it is gone
    with the baseline itself. What replaced it was already on the document: the revision
    partition, recorded when the run made the comparison. A client finds the summary at
    `report.delta` — the counts, the revision it was compared with, and the boundaries that
    closed — and each boundary's own state at `report.reviewed[].delta_state`. Nothing here
    recomputes either, and nothing copies them to the top level: one path to a value is the
    only way two paths cannot disagree.

    The distinction the removal turned on is worth keeping in view. A delta is a fact about two
    immutable revisions, so it is stored. A standing decision is a fact about *now* — it moves
    the moment somebody decides something — so it is joined at read time and never written into
    the review, which would freeze an answer that is supposed to move.
    """

    #: One entry per reviewed boundary, in report order — the team's standing decisions and
    #: threads, joined on at read time. Empty for a review that reached no verdicts.
    boundary_triage: list[BoundaryTriage] = Field(default_factory=list[BoundaryTriage])


def routes() -> APIRouter:
    """Running a review, reading one, and answering the questions it asked."""

    router = APIRouter()

    @router.post(
        "/api/reviews",
        status_code=201,
        dependencies=[SpendsModelBudget],
        responses=problem_responses(404, 422, 503),
    )
    def create_review(runtime: RuntimeDep, request: ReviewRequest) -> BoundaryReview:
        return runtime.review_service.review(
            request.case_id,
            repository_root=Path(request.repository_root),
            elicited_from=request.elicited_from,
        )

    @router.post(
        "/api/reviews/stream",
        response_class=NDJSONStreamingResponse,
        dependencies=[SpendsModelBudget],
        responses={
            200: {
                "model": ReviewProgress,
                "description": (
                    "The same review as POST /api/reviews, as newline-delimited JSON: one "
                    "ReviewProgress object per line, ending in a completed or failed line."
                ),
            },
            **problem_responses(422),
        },
    )
    def stream_review(runtime: RuntimeDep, request: ReviewRequest) -> NDJSONStreamingResponse:
        """The review a person watches: countable, because detection knows the length.

        Everything that can go wrong after the first line arrives as a `failed` line
        carrying the same `ProblemDetail` the non-streaming route would have returned. Once
        a response has started, its status code can no longer say anything, so the stream
        has to end in a verdict about itself.
        """

        return NDJSONStreamingResponse(
            review_progress_lines(
                runtime,
                case_id=request.case_id,
                repository_root=request.repository_root,
                elicited_from=request.elicited_from,
            ),
            # Buffering would defeat the point: progress that arrives all at once at the
            # end is the unexplained wait this route exists to replace.
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/reviews")
    def list_reviews(
        runtime: RuntimeDep,
        case_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[BoundaryReviewSummary]:
        return runtime.review_repository.list(case_id=case_id, limit=limit)

    @router.get(
        "/api/reviews/{review_id}",
        responses=problem_responses(404, 422),
    )
    def get_review(runtime: RuntimeDep, review_id: str) -> ReviewDetailResponse:
        """The stored review, plus what the team has since decided about its boundaries.

        One join, and no deeper: the standing decision on each boundary, read through the
        branch this run was on and the branch that branch came from. `ReviewService` never
        reads decisions — that is the one invariant of the triage design — so a decision can
        never reach the reasoning that produced a verdict.
        """

        return _with_boundary_triage(runtime, runtime.review_repository.get(review_id))

    @router.get(
        "/api/reviews/{review_id}/source",
        responses=problem_responses(404, 422),
    )
    def review_source(
        runtime: RuntimeDep,
        review_id: str,
        reference: Annotated[str | None, Query(pattern=r"^BR-[0-9]{3}$")] = None,
        context_lines: Annotated[int, Query(ge=0, le=MAX_CONTEXT_LINES)] = 0,
    ) -> list[BoundaryExcerpt]:
        """The code this review's findings were measured from.

        Delivery, not retrieval: every participant already carries the span a deterministic
        detector chose when the verdict was reached, so there is nothing to search for and
        nothing for a caller to select. `reference` narrows to one boundary because a page
        asks for what it is about to draw; `context_lines` is how much surrounding code to
        unfold, bounded by the workspace rather than by the request.

        A boundary whose code cannot be shown answers with the reason instead of the text —
        the repository has changed since the review ran, is gone, or the boundary was never
        written. That is a 200 carrying a stated absence, not a 404: the finding exists and
        is worth reading either way.
        """

        review = runtime.review_repository.get(review_id)
        return runtime.review_source_service.for_review(
            review,
            reference=reference,
            context_lines=context_lines,
        )

    @router.get(
        "/api/reviews/{review_id}/report",
        response_class=Response,
        responses={
            200: {
                "content": {"text/markdown": {}},
                "description": "The stored report, as a file named after the review.",
            },
            **problem_responses(404, 409, 422),
        },
    )
    def review_report(runtime: RuntimeDep, review_id: str) -> Response:
        """The review as the Markdown document it was already written as.

        The stored string, handed over unchanged. It was rendered once, at the moment the
        review concluded, from the report pinned to the case revision and the atlas that
        produced it — rendering it again here would let the exported file drift from the
        record it claims to be, on nothing more than a change to the renderer.

        A review with no report is a conflict rather than a 404: the review is there, and
        what is absent is a document that either has not been written yet or never will be.
        """

        review = runtime.review_repository.get(review_id)
        if review.markdown_report is None:
            if review.status is ReviewStatus.RUNNING:
                raise ReviewStillRunningError(
                    "That review is still running, so there is no report to export yet."
                )
            raise ReviewHasNoReportError(
                f"That review is {review.status.value} and reached no verdicts, so there "
                "is no report to export."
            )
        return Response(
            content=review.markdown_report,
            media_type="text/markdown",
            headers={
                "content-disposition": (
                    f'attachment; filename="{_report_filename(review_id)}"'
                )
            },
        )

    @router.post(
        "/api/reviews/{review_id}/answers",
        status_code=201,
        responses=problem_responses(404, 409, 422),
    )
    def answer_review_questions(
        runtime: RuntimeDep,
        review_id: str,
        request: ReviewAnswersRequest,
    ) -> CaseRevision:
        """Record a round of answers as one case revision that says what it answered.

        Its own route rather than a `PATCH /api/cases/{id}` the browser composes, because
        provenance written that way is optional by construction: a client that forgot it
        produced a revision which had silently lost the link back to the question. Here the
        link cannot be omitted — it is the thing the route exists to write.

        The server resolves each `Q-n` against this review's own report and reads the
        destination field from the question. A client sends the reference and the line the
        reader saw, and nothing that decides where it goes (§12.0).
        """

        review = runtime.review_repository.get(review_id)
        return runtime.case_service.answer(
            review,
            [
                WrittenAnswer(
                    question_reference=item.question_reference,
                    recorded_text=item.recorded_text,
                )
                for item in request.answers
            ],
        )

    @router.post(
        "/api/reviews/{review_id}/cancel",
        responses=problem_responses(404, 409, 422),
    )
    def cancel_review(runtime: RuntimeDep, review_id: str) -> BoundaryReview:
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

    @router.delete(
        "/api/reviews/{review_id}",
        status_code=204,
        responses=problem_responses(404, 409, 422),
    )
    def delete_review(runtime: RuntimeDep, review_id: str) -> Response:
        """Remove a review and the question threads hung off it.

        Deleting is not editing: it removes the record rather than leaving one that says
        something else, which is what immutability is about. A running review is refused —
        cancel it first, so the work stops before its record goes.
        """

        runtime.review_repository.delete(review_id)
        return Response(status_code=204)

    return router


#: Everything a downloaded filename is allowed to keep. Review identifiers are generated
#: and already safe, but this name leaves in a header a browser writes straight to disk, so
#: it is built from what survives the filter rather than from what arrived in the path.
_UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _report_filename(review_id: str) -> str:
    """Named after the review, because a folder of these has to stay tellable apart."""

    return f"archcompass-review-{_UNSAFE_IN_FILENAME.sub('-', review_id)}.md"


def _with_boundary_triage(runtime: Runtime, review: BoundaryReview) -> ReviewDetailResponse:
    """Attach what *now* knows about a review's boundaries: the standing decisions.

    The join happens here, at read time, and never at write time. A review is an immutable
    record of one run; what the team has decided about its boundaries is a fact about the
    present, and a stored copy of it would go stale the first time somebody used the feature.

    Read through the base branch, so a review on a feature branch shows what `main` already
    settled rather than presenting every boundary as undecided. An inherited decision names the
    branch it was actually taken on, which is what lets a page distinguish "we decided this"
    from "we have not disagreed with `main`".

    Entries exist for every reviewed boundary, decided or not: the fingerprint alone is what a
    client needs to post a decision, and a boundary is not going to be triaged by a page that
    cannot name it. A review from before branch lineages carries no decisions — stated by
    leaving them absent rather than by guessing a branch, because a decision filed under a
    guess would be attributed to a team that never took it.
    """

    payload = review.model_dump()
    report = review.report
    if report is None:
        return ReviewDetailResponse.model_validate(payload)

    standings = runtime.triage_service.standings_for_branch(review.branch_id)
    comment_counts = (
        {}
        if review.branch_id is None
        else runtime.triage_service.comment_counts(review.branch_id)
    )
    triage = [
        BoundaryTriage(
            reference=boundary.reference,
            fingerprint=fingerprint,
            decision=_joined_decision(standing_for(boundary, standings), boundary),
            comment_count=comment_counts.get(fingerprint, 0),
        )
        for boundary in report.reviewed
        for fingerprint in (boundary.fingerprint or boundary_fingerprint(boundary.candidate),)
    ]
    payload["boundary_triage"] = [item.model_dump() for item in triage]
    return ReviewDetailResponse.model_validate(payload)


def _joined_decision(
    decision: StandingDecision | None, boundary: ReviewedBoundary
) -> JoinedDecision | None:
    """One standing decision as a review's reader sees it, or nothing where none was taken."""

    if decision is None:
        return None
    return JoinedDecision(
        decision_id=decision.decision_id,
        state=decision.state,
        author=decision.author,
        reason=decision.reason,
        decided_at=decision.decided_at,
        taken_on_current_verdict=decision.taken_on(
            material=boundary.material,
            verdict_label=boundary.verdict_label,
        ),
    )
