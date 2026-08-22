"""A review that outlives the request, and can be found again after a reload."""

from __future__ import annotations

import threading

import pytest

from archcompass.domain.errors import ReviewStillRunningError
from archcompass.workflow.runs import ReviewRunner
from archcompass.workflow.service import _JudgingProgress


def test_a_run_is_addressable_before_it_has_finished() -> None:
    """The id has to come back immediately: a client cannot watch what it cannot name."""

    release = threading.Event()
    runner = ReviewRunner()

    def work(report):
        report("analyze_repository")
        release.wait(timeout=5)
        report("record_review")

    state = runner.start(run_id="thread-1", work=work)
    assert state.run_id == "thread-1"
    assert state.status == "running"

    # Watchable while the work is still in the middle of it.
    assert runner.is_running("thread-1")
    release.set()
    _settle(runner, "thread-1")
    assert runner.state("thread-1").stages == ("analyze_repository", "record_review")


def test_a_review_id_is_published_as_soon_as_one_exists() -> None:
    runner = ReviewRunner()
    reached = threading.Event()

    def work(report):
        report("compose_waiting_review")
        runner.bind_review("thread-2", "review-99")
        reached.set()

    runner.start(run_id="thread-2", work=work)
    assert reached.wait(timeout=5)
    _settle(runner, "thread-2")
    assert runner.state("thread-2").review_id == "review-99"


def test_a_failure_is_a_state_to_read_rather_than_a_lost_thread() -> None:
    runner = ReviewRunner()

    def work(report):
        report("analyze_repository")
        raise RuntimeError("the atlas could not be built")

    runner.start(run_id="thread-3", work=work)
    _settle(runner, "thread-3")
    state = runner.state("thread-3")
    assert state.status == "failed"
    assert "atlas could not be built" in state.failure
    # The stage it reached is kept, because that is where someone has to look.
    assert state.stages == ("analyze_repository",)


def test_the_same_run_is_not_started_twice() -> None:
    """A refusal a caller can act on: two tabs answering one round reach this."""

    runner = ReviewRunner()
    release = threading.Event()
    runner.start(run_id="thread-4", work=lambda report: release.wait(timeout=5))
    with pytest.raises(ReviewStillRunningError, match="already in flight"):
        runner.start(run_id="thread-4", work=lambda report: None)
    release.set()
    _settle(runner, "thread-4")


def test_a_cancelled_run_stops_at_the_next_stage_and_says_it_was_cancelled() -> None:
    """Cancelled, not failed: the work stopped because somebody stopped it.

    Cooperative, because the alternative is killing a thread part way through a node and
    leaving a checkpoint written by half a step. So the flag is read between stages: the
    stage in flight finishes and no further one starts.
    """

    runner = ReviewRunner()
    entered = threading.Event()
    reached_second_stage = False

    def work(report):
        nonlocal reached_second_stage
        report("analyze_repository")
        entered.wait(timeout=5)
        if runner.is_cancelled("thread-7"):
            return
        reached_second_stage = True
        report("detect_candidates")

    runner.start(run_id="thread-7", work=work)
    runner.cancel("thread-7")
    entered.set()
    _settle(runner, "thread-7")

    state = runner.state("thread-7")
    assert state.status == "cancelled"
    assert not reached_second_stage
    # The stage it reached is kept. A cancelled run is a record of work that was done.
    assert state.stages == ("analyze_repository",)


def test_a_run_started_again_is_not_stopped_by_yesterday_s_cancellation() -> None:
    """The id is the review's thread, and the next round of the same review reuses it."""

    runner = ReviewRunner()
    cancelled = threading.Event()
    runner.start(run_id="thread-8", work=lambda report: cancelled.wait(timeout=5))
    runner.cancel("thread-8")
    cancelled.set()
    _settle(runner, "thread-8")
    assert runner.state("thread-8").status == "cancelled"

    runner.start(run_id="thread-8", work=lambda report: report("select_rejudgements"))
    _settle(runner, "thread-8")
    assert not runner.is_cancelled("thread-8")
    assert runner.state("thread-8").status == "finished"


def test_a_repeated_stage_is_recorded_once() -> None:
    """Re-judgement re-enters the same nodes; the progress list is not a tally."""

    runner = ReviewRunner()

    def work(report):
        report("review_candidates")
        report("review_candidates")
        report("generate_questions")

    runner.start(run_id="thread-5", work=work)
    _settle(runner, "thread-5")
    assert runner.state("thread-5").stages == ("review_candidates", "generate_questions")


def test_the_candidate_loop_is_counted_because_a_stage_list_cannot_count_it() -> None:
    """Judging is one step that is fifteen deep, and a sequence of names cannot say that.

    The stage list already collapses a repeat, so fifteen judgements are one entry there and
    the reader cannot tell a run on its second candidate from one on its last. The depth is
    carried as a count instead of as fifteen rows saying the same words.
    """

    progress = _JudgingProgress()

    assert progress.observe("select_initial_candidates", {"selected_candidates": (1, 2, 3)})
    assert (progress.to_judge, progress.judged) == (3, 0)

    # The subgraph's own nodes are entered per candidate and produce nothing to count.
    assert not progress.observe("retrieve_policy_set", {"retrieval": object()})
    assert progress.observe("judge_candidate", {"findings": {"a": object()}})
    assert progress.judged == 1

    # A second round counts its own selection rather than continuing the first's.
    assert progress.observe("select_candidates_for_rejudgement", {"selected_candidates": (1,)})
    assert (progress.to_judge, progress.judged) == (1, 0)


def test_a_batch_judgement_counts_the_whole_selection_at_once() -> None:
    """One node returns every verdict, so the count arrives in one step rather than fifteen."""

    progress = _JudgingProgress()
    progress.observe("select_initial_candidates", {"selected_candidates": (1, 2)})

    assert progress.observe("review_candidates", {"findings": {"a": object(), "b": object()}})
    assert (progress.to_judge, progress.judged) == (2, 2)


def test_a_run_carries_how_far_through_its_candidates_it_is() -> None:
    runner = ReviewRunner()

    def work(report):
        report("judge_candidate")
        runner.report_judgements("thread-6", judged=4, to_judge=9)

    runner.start(run_id="thread-6", work=work)
    _settle(runner, "thread-6")
    state = runner.state("thread-6")
    assert (state.candidates_judged, state.candidates_to_judge) == (4, 9)


def _settle(runner: ReviewRunner, run_id: str) -> None:
    for _ in range(500):
        if not runner.is_running(run_id):
            return
        threading.Event().wait(0.01)
    raise AssertionError(f"run {run_id} never finished")


def test_a_run_is_listed_until_it_is_finished(tmp_path) -> None:
    """The half of findability the id could never provide.

    An address is only findable by somebody still holding it, and a run that judges in a
    batch is answered in minutes or hours — long enough that looking at something else in
    between is the ordinary way to use the page, not a mistake. So a run that has begun is
    listed, and stops being listed when it is done.

    It used to stop the moment a review id was attached, which is several nodes before the
    end — so the marker vanished while the run was still judging, the review was not in the
    reviews listing yet either, and a finished run and a run that never existed gave the
    same answer.
    """

    import sqlite3

    from archcompass.domain import ReviewStatus
    from archcompass.persistence.executions import SQLiteReviewExecutionRepository

    path = tmp_path / "executions.sqlite3"
    executions = SQLiteReviewExecutionRepository(lambda: sqlite3.connect(path))
    executions.begin(
        thread_id="thread-1",
        repository_id="repo-1",
        branch_id="branch-1",
        case_id="case-1",
    )

    in_flight = executions.in_flight()
    assert [item.thread_id for item in in_flight] == ["thread-1"]
    assert in_flight[0].branch_id == "branch-1"
    assert in_flight[0].case_id == "case-1"

    class _Review:
        id = "review-1"
        status = ReviewStatus.AWAITING_ANSWERS

    executions.bind("thread-1", _Review())

    # It asked a question and stopped, so it is a review now rather than a run.
    assert executions.in_flight() == ()

    # Answering it is minutes of judging on the same thread, and that is a run again.
    executions.resume("thread-1")
    assert [item.thread_id for item in executions.in_flight()] == ["thread-1"]
    assert executions.current_review_id("thread-1") == "review-1"

    class _Completed:
        id = "review-2"
        status = ReviewStatus.COMPLETED

    executions.bind("thread-1", _Completed())
    assert executions.in_flight() == ()


def test_a_cancelled_run_leaves_the_listing_and_keeps_its_row(tmp_path) -> None:
    """Cancelled is a status to read, not a deletion: the id somebody holds still answers."""

    import sqlite3

    from archcompass.persistence.executions import SQLiteReviewExecutionRepository

    executions = SQLiteReviewExecutionRepository(
        lambda: sqlite3.connect(tmp_path / "executions.sqlite3")
    )
    executions.begin(
        thread_id="thread-1",
        repository_id="repo-1",
        branch_id="branch-1",
        case_id="case-1",
    )
    executions.cancel("thread-1")

    assert executions.in_flight() == ()
    assert executions.status("thread-1") == "cancelled"
    assert executions.record("thread-1") is not None


def test_the_newest_run_is_listed_first(tmp_path) -> None:
    import sqlite3

    from archcompass.persistence.executions import SQLiteReviewExecutionRepository

    executions = SQLiteReviewExecutionRepository(
        lambda: sqlite3.connect(tmp_path / "executions.sqlite3")
    )
    for index in range(3):
        executions.begin(
            thread_id=f"thread-{index}",
            repository_id="repo-1",
            branch_id="branch-1",
            case_id=f"case-{index}",
        )

    # No timestamp is stored, so insertion order is start order and that is what is used.
    assert [item.thread_id for item in executions.in_flight()] == [
        "thread-2",
        "thread-1",
        "thread-0",
    ]
