"""A review that outlives the request, and can be found again after a reload."""

from __future__ import annotations

import threading

import pytest

from archcompass.workflow.runs import ReviewRunner


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
    runner = ReviewRunner()
    release = threading.Event()
    runner.start(run_id="thread-4", work=lambda report: release.wait(timeout=5))
    with pytest.raises(ValueError, match="already in flight"):
        runner.start(run_id="thread-4", work=lambda report: None)
    release.set()
    _settle(runner, "thread-4")


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


def _settle(runner: ReviewRunner, run_id: str) -> None:
    for _ in range(500):
        if not runner.is_running(run_id):
            return
        threading.Event().wait(0.01)
    raise AssertionError(f"run {run_id} never finished")


def test_a_run_is_listed_until_it_has_a_review_to_be_listed_as(tmp_path) -> None:
    """The half of findability the id could never provide.

    An address is only findable by somebody still holding it, and a run that judges in a
    batch is answered in minutes or hours — long enough that looking at something else in
    between is the ordinary way to use the page, not a mistake. So a run that has begun and
    has no review yet is listed, and stops being listed the moment there is a review to list
    in its place. Never both: one row per thing.
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
        status = ReviewStatus.COMPLETED

    executions.bind("thread-1", _Review())  # type: ignore[arg-type]

    assert executions.in_flight() == ()


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
