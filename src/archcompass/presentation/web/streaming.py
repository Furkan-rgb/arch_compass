"""The two streaming routes, as lines: what one line can say, and who writes them.

A run and a conversation turn are the only two things here long enough to be worth
watching, and both are reported the same way — a worker thread does the work, a queue
carries what it says, and this module turns each thing said into one JSON object on its own
line. The line models are declared beside the pumps rather than beside the routes because
they *are* the stream's contract: a route only chooses to open one.

Nothing here decides anything about a review or an answer. The application services still
own detection, judgement order, composition and the turn; these functions only report.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Annotated, Literal

from fastapi.responses import StreamingResponse
from pydantic import Field, RootModel

from archcompass.application.reviews import JudgedCandidate
from archcompass.bootstrap import Runtime
from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.errors import ArchCompassError, NothingToReviewError
from archcompass.domain.review import BoundaryReview
from archcompass.domain.review_conversation import ReviewMessage
from archcompass.presentation.web.errors import classify_error
from archcompass.presentation.web.schemas import APIModel, ProblemDetail


class NDJSONStreamingResponse(StreamingResponse):
    """A stream of one JSON object per line.

    Declared as a class so the OpenAPI document says `application/x-ndjson` where the
    schema is: a body that is a sequence of lines is not one JSON document, and describing
    it as `application/json` would tell a generated client the wrong thing to parse.
    """

    media_type = "application/x-ndjson"


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
    #: Which pass this is, echoed back so a watcher can draw the run's stages without
    #: having to remember what it asked for. A client that reloaded onto a stream it did
    #: not start has no other way to know.
    elicited_from: str | None = None


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
    #: The review this verdict was carried forward from, where it was not reached in this
    #: run. Null on every verdict the run actually paid a model call for, and on every line
    #: written before this field existed — so a client that sees nothing here is looking at
    #: a judged boundary, which is what it assumed all along.
    verdict_reused_from: str | None = None
    #: How many verdicts have been carried so far, this one included. Sent rather than left
    #: to the client to accumulate, so a watcher that joined the stream late — or dropped a
    #: line — still has the run's own count instead of a tally of what it happened to see.
    carried: int = 0


class ReviewEliciting(APIModel):
    """Every boundary is judged; the first pass is composing what it needs to ask.

    Distinct from `summarising` because it is a different call with a different outcome: one
    ends in a conclusion, the other may end in a run that stops and waits for a person.
    Exactly one of the two arrives in any run.
    """

    event: Literal["eliciting"] = "eliciting"
    total: int


class ReviewSummarising(APIModel):
    """Every boundary is judged; one call remains, over all of them at once."""

    event: Literal["summarising"] = "summarising"
    total: int


class ReviewCompleted(APIModel):
    """The composed, persisted review — the same object the non-streaming route returns."""

    event: Literal["completed"] = "completed"
    review: BoundaryReview


class ReviewUnchanged(APIModel):
    """The run refused itself: nothing has moved since the branch's latest revision.

    A terminal line and not a failure — the workspace worked the whole partition out and
    the answer was that a revision would repeat the one before it, so nothing was recorded.
    Emitted before a `started` line could exist, because refusal happens before the run has
    a record.
    """

    event: Literal["unchanged"] = "unchanged"
    #: The revision this repository is already up to date with.
    current_against: str
    message: str


class ReviewFailed(APIModel):
    """The run failed. Nothing was persisted; the case and atlas are untouched."""

    event: Literal["failed"] = "failed"
    problem: ProblemDetail


ReviewProgressLine = Annotated[
    ReviewStarted
    | ReviewDetected
    | ReviewJudged
    | ReviewEliciting
    | ReviewSummarising
    | ReviewCompleted
    | ReviewUnchanged
    | ReviewFailed,
    Field(discriminator="event"),
]


class ReviewProgress(RootModel[ReviewProgressLine]):
    """One line of `POST /api/reviews/stream`, discriminated by `event`."""


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


def _abstraction_name(candidate: FindingCandidate) -> str:
    """The boundary a person recognises: the abstraction, not the candidate's identity."""

    first = candidate.participants[0] if candidate.participants else None
    return first.qualified_name if first is not None else "unnamed boundary"


def review_progress_lines(
    runtime: Runtime,
    *,
    case_id: str,
    repository_root: str,
    elicited_from: str | None,
) -> Iterator[str]:
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
        | ReviewEliciting
        | ReviewSummarising
        | ReviewCompleted
        | ReviewUnchanged
        | ReviewFailed,
    ) -> None:
        lines.put(event.model_dump_json())

    def report_start(review: BoundaryReview) -> None:
        emit(
            ReviewStarted(
                review_id=review.review_id,
                case_id=review.case_id,
                case_revision=review.case_revision,
                elicited_from=review.elicited_from,
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

    carried = 0

    def report_verdict(judged: JudgedCandidate, position: int, total: int) -> None:
        nonlocal carried
        if judged.reused_from is not None:
            carried += 1
        emit(
            ReviewJudged(
                position=position,
                total=total,
                abstraction=_abstraction_name(judged.candidate),
                material=judged.verdict.material,
                verdict_reused_from=judged.reused_from,
                carried=carried,
            )
        )

    def run() -> None:
        try:
            review = runtime.review_service.review(
                case_id,
                repository_root=Path(repository_root),
                elicited_from=elicited_from,
                on_started=report_start,
                on_detected=report_detection,
                on_verdict=report_verdict,
                on_eliciting=lambda: emit(ReviewEliciting(total=detected)),
                on_summarising=lambda: emit(ReviewSummarising(total=detected)),
            )
        except NothingToReviewError as unchanged:
            # Its own line, not a `failed` one: the run did exactly what it promised, and a
            # client that showed this as an error would be scolding the reader for having
            # an up-to-date repository. Every caller of this stream gets the same answer,
            # whichever page or client started it — that is the point of refusing in the
            # service rather than in a button.
            emit(
                ReviewUnchanged(
                    current_against=unchanged.current_against,
                    message=str(unchanged),
                )
            )
        except ArchCompassError as error:
            # The status is deliberately dropped: the response is already a 200 by the time
            # the run fails, and a code in the body that disagreed with it would be worse
            # than one that says nothing.
            _status, code, retryable = classify_error(error)
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


def answer_progress_lines(
    runtime: Runtime,
    conversation_id: str,
    question: str,
) -> Iterator[str]:
    """Ask one question in a worker thread and yield each line as the answer is written.

    The same shape as `review_progress_lines`, for the same reason: a thread and a queue that
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
            _status, code, retryable = classify_error(error)
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
