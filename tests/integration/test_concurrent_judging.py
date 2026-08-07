"""Several boundaries judged at once, reported one at a time in the order they were found.

A review is one model call per boundary and the call is an HTTP wait, so a run against a
provider that answers several at once spent most of its minutes waiting in sequence for no
reason. How many may overlap is the provider's own answer — a hosted API has a fleet, a
local Ollama has one GPU — and it reaches the run on the resolved configuration.

What must not change is what a reader sees. The stream and the stored counts are the run's
account of itself, and a boundary that finished third arriving second would have the two
disagree with the report. So judging may overlap and reporting may not, which is what the
tests here hold: every assertion is about order, about stopping, or about failing, and none
of them is about speed.
"""

from __future__ import annotations

import threading
from pathlib import Path
from time import monotonic, sleep

import pytest

from archcompass.adapters.models.deterministic import DETERMINISTIC_MODEL
from archcompass.application.reviews import JudgedCandidate
from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.case import ArchitectureCase, RepositoryReference
from archcompass.domain.errors import ProviderError, ReviewCancelledError
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryReview,
    CandidateVerdict,
    OpenQuestion,
    ReviewedBoundary,
    ReviewEvidence,
    ReviewOverview,
    ReviewStatus,
)
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage
from archcompass.domain.workspace import BoundaryReviewSummary
from archcompass.ports.model_catalog import CONCURRENT_REQUESTS_VARIABLE
from archcompass.ports.reasoning import FocusedReasoningProvider, ReasoningTask

FIXTURE = Path("eval/cases/boundary-review/repository").resolve()

#: How long a judgement will wait for the one it is supposed to overlap with. Long enough
#: that a loaded machine does not fail the test, short enough that a sequential run — where
#: the meeting can never happen — reports it rather than hanging the suite.
MEETING_TIMEOUT = 5.0


class OverlappingReasoner:
    """The real substitute, plus a record of how many judgements were inside it at once.

    Wrapping rather than replacing: the other stages have to go on working or the run never
    reaches an assertion, and only judgement is per boundary and so only judgement is
    watched.

    The proof of overlap is a barrier rather than a timing measurement. Two judgements that
    both reach it are two judgements that were genuinely inside this method together — a
    sequential run cannot pass it, it can only wait out the timeout — so nothing here turns
    on how fast the machine is.
    """

    def __init__(
        self,
        delegate: FocusedReasoningProvider,
        *,
        concurrent_requests: int,
        meeting: int = 0,
        fails: bool = False,
    ) -> None:
        self._delegate = delegate
        self._concurrent_requests = concurrent_requests
        self._fails = fails
        #: The first `meeting` calls must be inside this method together. Absent where a
        #: test is about a run that must *not* overlap: there would be nobody to meet.
        self._barrier = (
            threading.Barrier(meeting, timeout=MEETING_TIMEOUT) if meeting > 1 else None
        )
        self._lock = threading.Lock()
        self._entered = 0
        self.in_flight = 0
        #: The most judgements this reasoner ever had inside it at one time. One is a
        #: sequential run, whatever the wall clock says.
        self.high_water = 0
        self.judgements = 0

    @property
    def model_identity(self) -> str:
        return self._delegate.model_identity

    @property
    def concurrent_requests(self) -> int:
        return self._concurrent_requests

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._delegate.prompt_identity(task)

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
    ) -> CandidateVerdict:
        with self._lock:
            self._entered += 1
            entry = self._entered
            self.in_flight += 1
            self.judgements += 1
            self.high_water = max(self.high_water, self.in_flight)
        try:
            if self._fails:
                raise ProviderError("the model went away")
            if self._barrier is not None and entry <= self._barrier.parties:
                # Only the first few wait: a barrier the last judgement reaches alone is one
                # that times out, and the question was never about the last judgement.
                self._barrier.wait()
            return self._delegate.judge_finding_candidate(case, candidate, policies)
        finally:
            with self._lock:
                self.in_flight -= 1

    def elicit_questions(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> list[OpenQuestion]:
        return self._delegate.elicit_questions(case, boundaries)

    def summarise_review(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> ReviewOverview:
        return self._delegate.summarise_review(case, boundaries)

    def answer_review_question(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
    ) -> ReviewAnswer:
        return self._delegate.answer_review_question(
            review, evidence, history, question, knowledge
        )

    def discuss_open_question(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
    ) -> ReviewAnswer:
        return self._delegate.discuss_open_question(
            review, evidence, question, history, asked, knowledge
        )


def _indexed_case(runtime: Runtime) -> str:
    atlas = runtime.analyzer.analyze(FIXTURE)
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_repository.create(
        ArchitectureCase(
            title="Scheduler boundaries",
            problem_statement="Decide which of these ports are earning their place.",
            desired_outcome="A verdict per boundary.",
            # Stated so these runs finish rather than stopping to ask: what is under test
            # here is a review that ended.
            expected_future_changes=["A second scheduler backend is contracted for Q3"],
            repository=RepositoryReference(root_path=str(FIXTURE)),
        ),
        actor="test",
    )
    return revision.case_id


def _only(runtime: Runtime) -> BoundaryReviewSummary:
    listed = runtime.review_repository.list()
    assert len(listed) == 1, listed
    return listed[0]


def _watching(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
    *,
    concurrent_requests: int,
    meeting: int = 0,
    fails: bool = False,
) -> OverlappingReasoner:
    service = runtime.review_service
    spy = OverlappingReasoner(
        service._reasoner,  # pyright: ignore[reportPrivateUsage]
        concurrent_requests=concurrent_requests,
        meeting=meeting,
        fails=fails,
    )
    monkeypatch.setattr(service, "_reasoner", spy)
    return spy


def _no_judging_threads_remain() -> bool:
    """Whether the pool the run built has gone.

    Polled rather than asserted at once: `shutdown(wait=False)` returns before the last
    worker has finished unwinding, and what is being tested is that they end — not that
    they end before the next line of the test.
    """

    deadline = monotonic() + 5.0
    while monotonic() < deadline:
        if not [item for item in threading.enumerate() if item.name.startswith("judge-")]:
            return True
        sleep(0.02)
    return False


def test_two_boundaries_are_genuinely_judged_at_the_same_time(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The barrier is the assertion: a sequential run cannot get two calls to meet at it."""

    case_id = _indexed_case(runtime)
    reasoner = _watching(runtime, monkeypatch, concurrent_requests=2, meeting=2)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    assert review.status is ReviewStatus.SUCCEEDED
    assert reasoner.judgements > 1, "the fixture has to offer more than one boundary"
    assert reasoner.high_water == 2, "two judgements were inside the model at once"


def test_the_verdicts_are_reported_in_the_detected_order_however_they_finish(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Judging overlaps; reporting does not.

    The positions a watcher is given, the counts the record keeps and the boundaries the
    report holds are all one sequence, and it is the order the sweep detected them in. A
    run that reported whatever finished first would have the stream disagree with the page
    it is drawing.
    """

    case_id = _indexed_case(runtime)
    _watching(runtime, monkeypatch, concurrent_requests=4, meeting=2)
    detected: list[str] = []
    reported: list[tuple[str, int, int]] = []
    counted: list[int] = []

    def note_detected(candidates: object) -> None:
        assert isinstance(candidates, list)
        detected.extend(item.candidate_id for item in candidates)

    def note_verdict(item: JudgedCandidate, position: int, total: int) -> None:
        reported.append((item.candidate.candidate_id, position, total))
        counted.append(_only(runtime).boundaries_reviewed)

    review = runtime.review_service.review(
        case_id,
        repository_root=FIXTURE,
        on_detected=note_detected,
        on_verdict=note_verdict,
    )

    assert [item[0] for item in reported] == detected
    assert [item[1] for item in reported] == list(range(1, len(detected) + 1))
    assert {item[2] for item in reported} == {len(detected)}
    # Written from the consuming loop alone, so the stored count is the position and not
    # some larger number a finished worker got there first with.
    assert counted == list(range(1, len(detected) + 1))
    report = review.report
    assert report is not None
    assert [item.candidate.candidate_id for item in report.reviewed] == detected


def test_one_concurrent_request_judges_strictly_one_at_a_time(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provider that says one gets the loop this codebase has always run.

    No barrier here, because there is nothing to meet: what is asserted is that the reasoner
    never saw a second call arrive while it was still answering the first.
    """

    case_id = _indexed_case(runtime)
    reasoner = _watching(runtime, monkeypatch, concurrent_requests=1)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    assert review.status is ReviewStatus.SUCCEEDED
    assert reasoner.judgements > 1
    assert reasoner.high_water == 1, "nothing overlapped"
    assert _no_judging_threads_remain(), "and no pool was built to run it"


def test_a_judgement_that_fails_fails_the_run_and_takes_the_pool_with_it(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exactly the failure a sequential run records, from a worker thread instead.

    Same exception out of `review`, same row, same sanitized message — see
    `test_a_failed_run_is_recorded_rather_than_left_running`, which asserts the identical
    three things about the sequential path. What is new is the last line: the judgements
    that had not started never run, and the pool does not outlive the run that built it.
    """

    case_id = _indexed_case(runtime)
    _watching(runtime, monkeypatch, concurrent_requests=4, fails=True)

    with pytest.raises(ProviderError):
        runtime.review_service.review(case_id, repository_root=FIXTURE)

    listed = _only(runtime)
    assert listed.status == ReviewStatus.FAILED.value
    stored = runtime.review_repository.get(listed.review_id)
    assert stored.report is None
    assert stored.sanitized_errors == ["the model went away"]
    assert _no_judging_threads_remain()


def test_cancelling_a_parallel_run_stops_the_consuming_loop(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancelling still bounds the run at the next boundary, and still discards the rest.

    The judgements already in flight are allowed to finish — they were paid for, and their
    verdicts write through to the cache so the next run does not pay again — but nothing
    after the cancellation is reported, and a partial review is still not a review.
    """

    case_id = _indexed_case(runtime)
    _watching(runtime, monkeypatch, concurrent_requests=4, meeting=2)
    judged: list[int] = []

    def cancel_after_the_first(_item: object, position: int, _total: int) -> None:
        judged.append(position)
        if position == 1:
            assert runtime.review_repository.cancel(_only(runtime).review_id) is True

    with pytest.raises(ReviewCancelledError):
        runtime.review_service.review(
            case_id, repository_root=FIXTURE, on_verdict=cancel_after_the_first
        )

    assert judged == [1], "the run stops at the next boundary, not at the end of the sweep"
    listed = _only(runtime)
    assert listed.status == ReviewStatus.CANCELLED.value
    stored = runtime.review_repository.get(listed.review_id)
    assert stored.report is None
    # Not a failure, for the same reason it is not one sequentially: a review nobody wanted
    # any more is not a review that broke.
    assert stored.sanitized_errors == []
    assert _no_judging_threads_remain()


def test_the_environment_decides_what_an_offline_run_may_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The operator's knob reaches a plain local workspace, not only a hosted deployment.

    Asserted on the substitute, which is the provider a pinned local run uses, because the
    point is that the number travels the same path for every provider: descriptor, then the
    environment, then the resolved configuration, then the reasoner the review asks.
    """

    monkeypatch.setenv(CONCURRENT_REQUESTS_VARIABLE, "3")

    runtime = build_runtime(tmp_path, pin=pinned_model("fake", DETERMINISTIC_MODEL))

    reasoner = runtime.review_service._reasoner  # pyright: ignore[reportPrivateUsage]
    assert reasoner.concurrent_requests == 3
