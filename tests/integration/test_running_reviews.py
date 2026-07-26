"""A review exists while it is being produced, not only once it is over.

A review is one model call per boundary and takes minutes. Persisting it only at the end
meant that for those minutes it was indistinguishable from a run that never started: nothing
to open, nothing to come back to, and no way to tell the difference from a listing. The row
is written when the run begins and finished when it ends, and the transition out of
`running` is the only one a stored review ever makes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.bootstrap import Runtime
from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.case import ArchitectureCase, RepositoryReference
from archcompass.domain.errors import (
    AtlasNotFoundError,
    ProviderError,
    ReviewNotFoundError,
)
from archcompass.domain.review import ReviewStatus
from archcompass.domain.workspace import BoundaryReviewSummary

FIXTURE = Path("eval/cases/boundary-review/repository").resolve()


def _indexed_case(runtime: Runtime) -> str:
    atlas = runtime.analyzer.analyze(FIXTURE)
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_repository.create(
        ArchitectureCase(
            title="Scheduler boundaries",
            problem_statement="Decide which of these ports are earning their place.",
            desired_outcome="A verdict per boundary.",
            repository=RepositoryReference(root_path=str(FIXTURE)),
        ),
        actor="test",
    )
    return revision.case_id


def _only(runtime: Runtime) -> BoundaryReviewSummary:
    listed = runtime.review_repository.list()
    assert len(listed) == 1, listed
    return listed[0]


def test_the_review_is_listed_before_the_first_verdict_lands(runtime: Runtime) -> None:
    case_id = _indexed_case(runtime)
    seen: list[BoundaryReviewSummary] = []

    # Read from inside the run, at the first moment the run itself reports anything. What
    # matters is that the listing already knows about it — the row is what a second reader
    # would find while waiting.
    runtime.review_service.review(
        case_id,
        repository_root=FIXTURE,
        on_detected=lambda _candidates: seen.append(_only(runtime)),
    )

    assert seen[0].status == ReviewStatus.RUNNING.value
    assert seen[0].case_id == case_id


def test_the_run_reports_its_length_and_its_progress(runtime: Runtime) -> None:
    case_id = _indexed_case(runtime)
    at_detection: list[BoundaryReviewSummary] = []
    per_verdict: list[BoundaryReviewSummary] = []

    def detected(candidates: list[FindingCandidate]) -> None:
        del candidates
        at_detection.append(_only(runtime))

    runtime.review_service.review(
        case_id,
        repository_root=FIXTURE,
        on_detected=detected,
        on_verdict=lambda *_: per_verdict.append(_only(runtime)),
    )

    # Detection is where the length becomes known, and before it the honest answer is that
    # nothing is known — not zero, which reads as "the sweep found none".
    assert at_detection[0].boundaries_detected == len(per_verdict)
    assert at_detection[0].boundaries_reviewed == 0
    assert [item.boundaries_reviewed for item in per_verdict] == list(
        range(1, len(per_verdict) + 1)
    )
    assert all(item.status == ReviewStatus.RUNNING.value for item in per_verdict)


def test_a_finished_review_stops_saying_it_is_running(runtime: Runtime) -> None:
    case_id = _indexed_case(runtime)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    listed = _only(runtime)
    assert listed.status == ReviewStatus.SUCCEEDED.value
    assert listed.review_id == review.review_id
    assert listed.boundaries_detected == listed.boundaries_reviewed
    assert listed.case_title == "Scheduler boundaries"
    # The identity is the same one the run held, so a page opened mid-run is the page that
    # ends up holding the review.
    assert runtime.review_repository.get(review.review_id).status is ReviewStatus.SUCCEEDED


def test_a_failed_run_is_recorded_rather_than_left_running(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id = _indexed_case(runtime)
    monkeypatch.setattr(
        DeterministicReasoningProvider,
        "judge_finding_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(ProviderError("the model went away")),
    )

    with pytest.raises(ProviderError):
        runtime.review_service.review(case_id, repository_root=FIXTURE)

    listed = _only(runtime)
    assert listed.status == ReviewStatus.FAILED.value
    stored = runtime.review_repository.get(listed.review_id)
    assert stored.report is None
    # ArchCompass wrote that message for a person to read, which is the same rule the web
    # layer applies before putting one in a response.
    assert stored.sanitized_errors == ["the model went away"]


def test_an_unexpected_failure_is_recorded_without_quoting_it(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id = _indexed_case(runtime)
    monkeypatch.setattr(
        DeterministicReasoningProvider,
        "judge_finding_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("connection reset by peer")),
    )

    with pytest.raises(RuntimeError):
        runtime.review_service.review(case_id, repository_root=FIXTURE)

    stored = runtime.review_repository.get(_only(runtime).review_id)
    assert stored.status is ReviewStatus.FAILED
    assert "connection reset" not in " ".join(stored.sanitized_errors)


def test_nothing_is_stored_when_the_run_is_refused_before_it_starts(
    runtime: Runtime,
) -> None:
    """A case with no indexed atlas never becomes a row.

    The record starts after everything that can refuse the run, so a listing never fills up
    with runs that could not have happened.
    """

    revision = runtime.case_repository.create(
        ArchitectureCase(
            title="No atlas",
            problem_statement="A repository that was never indexed.",
            desired_outcome="Nothing, because this cannot run.",
        ),
        actor="test",
    )

    with pytest.raises(AtlasNotFoundError):
        runtime.review_service.review(revision.case_id, repository_root=FIXTURE)

    assert runtime.review_repository.list() == []


def test_a_run_left_behind_by_a_stopped_workspace_is_reported_not_left_running(
    runtime: Runtime,
) -> None:
    """A run cannot outlive its process, so a row still running at startup is orphaned."""

    case_id = _indexed_case(runtime)
    orphan: list[str] = []

    def abandon_mid_run(*_args: object) -> None:
        orphan.append(_only(runtime).review_id)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        runtime.review_service.review(
            case_id, repository_root=FIXTURE, on_detected=abandon_mid_run
        )
    # KeyboardInterrupt is not an Exception, so nothing recorded a failure — which is the
    # situation a killed process leaves behind.
    assert _only(runtime).status == ReviewStatus.RUNNING.value

    assert runtime.review_repository.abandon_running(reason="The workspace stopped.") == 1

    listed = _only(runtime)
    assert listed.status == ReviewStatus.FAILED.value
    assert listed.review_id == orphan[0]
    stored = runtime.review_repository.get(listed.review_id)
    # Rewritten from its own document, so it still names the case and atlas it was
    # judging rather than becoming an anonymous failure.
    assert stored.case_id == case_id
    assert "The workspace stopped." in stored.sanitized_errors


def test_abandoning_leaves_finished_reviews_alone(runtime: Runtime) -> None:
    case_id = _indexed_case(runtime)
    runtime.review_service.review(case_id, repository_root=FIXTURE)

    assert runtime.review_repository.abandon_running(reason="The workspace stopped.") == 0
    assert _only(runtime).status == ReviewStatus.SUCCEEDED.value


def test_completing_a_review_that_was_never_begun_is_refused(runtime: Runtime) -> None:
    """The row is the run's own; there is no path that writes a judgement without one."""

    case_id = _indexed_case(runtime)
    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    with pytest.raises(ReviewNotFoundError):
        runtime.review_repository.complete(review.model_copy(update={"review_id": "rev_absent"}))
