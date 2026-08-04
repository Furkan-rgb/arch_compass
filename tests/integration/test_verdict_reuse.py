"""A second run over an unchanged question asks nothing and answers the same.

Run against the deterministic substitute, which would return the same verdict anyway — so
nothing here asserts that two runs agree. What is asserted is that the model was not called
and that each boundary names the run its verdict was reached by. Those two hold whatever a
real model would have said, which is the point: reuse has to be provable from the record
rather than inferred from two runs happening to coincide.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from archcompass.adapters.retrieval.policy_markdown import REQUIRED_SECTIONS
from archcompass.application.cases import CaseUpdate
from archcompass.application.reviews import JudgedCandidate
from archcompass.bootstrap import AUTHORED_POLICY_DIRECTORY, Runtime
from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.case import ArchitectureCase, RepositoryReference
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryReview,
    CandidateVerdict,
    OpenQuestion,
    ReviewedBoundary,
    ReviewOverview,
    ReviewStatus,
)
from archcompass.ports.reasoning import FocusedReasoningProvider, ReasoningTask

FIXTURE = Path("eval/cases/speech-vendor/repository").resolve()


class CountingReasoner:
    """The real substitute, plus a tally of the one call the cache exists to skip.

    Wrapping rather than replacing. The other stages have to go on working — a run that
    could not elicit or summarise would never reach the assertions — and only judgement is
    counted, because only judgement is per boundary.
    """

    def __init__(self, delegate: FocusedReasoningProvider) -> None:
        self._delegate = delegate
        self.judgements = 0

    @property
    def model_identity(self) -> str:
        return self._delegate.model_identity

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._delegate.prompt_identity(task)

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
    ) -> CandidateVerdict:
        self.judgements += 1
        return self._delegate.judge_finding_candidate(case, candidate, policies)

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


@pytest.fixture
def counting(runtime: Runtime, monkeypatch: pytest.MonkeyPatch) -> CountingReasoner:
    service = runtime.review_service
    spy = CountingReasoner(service._reasoner)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(service, "_reasoner", spy)
    return spy


@pytest.fixture
def case_id(runtime: Runtime) -> str:
    """One indexed repository and one case, so a second run is the same question."""

    runtime.atlas_repository.save(runtime.analyzer.analyze(FIXTURE))
    revision = runtime.case_repository.create(
        ArchitectureCase(
            title="Provider variation",
            problem_statement="Decide where provider-specific knowledge should live.",
            desired_outcome="One owner for provider differences.",
            expected_future_changes=["A hosted provider may be added later"],
            repository=RepositoryReference(root_path=str(FIXTURE)),
        ),
        actor="test",
    )
    return revision.case_id


def _reviewed(review: BoundaryReview) -> list[ReviewedBoundary]:
    report = review.report
    assert report is not None
    return report.reviewed


def test_an_unchanged_rerun_reuses_every_verdict_and_calls_nothing(
    runtime: Runtime, counting: CountingReasoner, case_id: str
) -> None:
    first = runtime.review_service.review(case_id, repository_root=FIXTURE)
    assert first.status is ReviewStatus.SUCCEEDED
    paid = counting.judgements
    assert paid == len(_reviewed(first)) > 0, "the first run pays for every boundary"

    second = runtime.review_service.review(case_id, repository_root=FIXTURE)

    assert counting.judgements == paid, "the second run asks the model about nothing"
    assert len(_reviewed(second)) == len(_reviewed(first)), "and still reports all of them"
    assert all(
        item.verdict_reused_from == first.review_id for item in _reviewed(second)
    ), "every boundary names the run its verdict was reached by"
    assert [item.rationale for item in _reviewed(second)] == [
        item.rationale for item in _reviewed(first)
    ], "reuse is the same words, not a fresh answer that happens to agree"


def test_a_first_run_reaches_its_own_verdicts_and_says_so(
    runtime: Runtime, counting: CountingReasoner, case_id: str
) -> None:
    """The other half: nothing is attributed to an earlier run when there was none."""

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    assert counting.judgements == len(_reviewed(review))
    assert all(item.verdict_reused_from is None for item in _reviewed(review))
    assert all(item.fingerprint for item in _reviewed(review))


def test_a_cached_run_reports_itself_exactly_as_a_judged_one_does(
    runtime: Runtime, case_id: str
) -> None:
    """The run looks identical to anyone watching it: same events, same counts, same order.

    Also the one place a carried verdict's own `candidate_id` is visible. It is re-pointed
    at this run's candidate, because a candidate id is minted at detection and a verdict
    still naming the previous run's would be about something that no longer exists.
    """

    first: list[tuple[str, int, int]] = []
    second: list[tuple[str, int, int]] = []

    def record(
        into: list[tuple[str, int, int]],
    ) -> Callable[[JudgedCandidate, int, int], None]:
        def observe(item: JudgedCandidate, position: int, total: int) -> None:
            assert item.verdict.candidate_id == item.candidate.candidate_id
            into.append((item.candidate.summary, position, total))

        return observe

    runtime.review_service.review(
        case_id, repository_root=FIXTURE, on_verdict=record(first)
    )
    runtime.review_service.review(
        case_id, repository_root=FIXTURE, on_verdict=record(second)
    )

    assert first == second and first, "a cached run is not a quieter run"


def test_the_same_structure_keeps_its_fingerprint_across_runs(
    runtime: Runtime, case_id: str
) -> None:
    first = runtime.review_service.review(case_id, repository_root=FIXTURE)
    second = runtime.review_service.review(case_id, repository_root=FIXTURE)

    fingerprints = [item.fingerprint for item in _reviewed(first)]
    assert fingerprints == [item.fingerprint for item in _reviewed(second)]
    assert len(set(fingerprints)) == len(fingerprints), "distinct boundaries stay distinct"


def test_answering_the_case_re_judges_everything(
    runtime: Runtime, counting: CountingReasoner, case_id: str
) -> None:
    """A revision is a different question, so a second pass has nothing to carry.

    The property moved-verdict attribution rests on: what the second pass reports is what
    the model concluded knowing the answers, not last pass's conclusion wearing a new date.
    """

    runtime.review_service.review(case_id, repository_root=FIXTURE)
    paid = counting.judgements
    runtime.case_service.update(
        case_id,
        CaseUpdate(desired_outcome="One owner for provider differences, decided this quarter."),
    )

    second = runtime.review_service.review(case_id, repository_root=FIXTURE)

    assert counting.judgements == paid + len(_reviewed(second))
    assert all(item.verdict_reused_from is None for item in _reviewed(second))


def test_a_new_policy_re_judges_everything(
    runtime: Runtime, counting: CountingReasoner, case_id: str
) -> None:
    """A corpus is what a verdict was weighed under, so widening it invalidates the lot."""

    runtime.review_service.review(case_id, repository_root=FIXTURE)
    paid = counting.judgements
    authored = runtime.workspace / AUTHORED_POLICY_DIRECTORY
    authored.mkdir(parents=True, exist_ok=True)
    sections = "".join(
        f"## {heading.title()}\nText.\n\n" for heading in sorted(REQUIRED_SECTIONS)
    )
    (authored / "keep-one-owner.md").write_text(
        "---\n"
        "id: keep-one-owner\n"
        "title: Keep one owner for a decision\n"
        "scope: general\n"
        "strength: guidance\n"
        "tags: [ownership]\n"
        "source:\n"
        "  author: test\n"
        "description: >-\n"
        "  A decision with two owners is a decision nobody made.\n"
        f"---\n{sections}",
        encoding="utf-8",
    )

    second = runtime.review_service.review(case_id, repository_root=FIXTURE)

    assert counting.judgements == paid + len(_reviewed(second))
    assert all(item.verdict_reused_from is None for item in _reviewed(second))


def test_deleting_the_run_that_reached_a_verdict_does_not_unlearn_it(
    runtime: Runtime, counting: CountingReasoner, case_id: str
) -> None:
    """The choice migration 025 documents, asserted rather than left as prose.

    A verdict is true about the structure it judged, and the run that happened to produce it
    going away does not make it wrong. Dropping cached verdicts with their origin review
    would mean tidying up a listing silently re-imposes a full, paid re-run.
    """

    first = runtime.review_service.review(case_id, repository_root=FIXTURE)
    paid = counting.judgements
    runtime.review_repository.delete(first.review_id)

    second = runtime.review_service.review(case_id, repository_root=FIXTURE)

    assert counting.judgements == paid, "the deleted run's answers still stand"
    assert all(
        item.verdict_reused_from == first.review_id for item in _reviewed(second)
    ), "attribution names the run even though it is gone"
