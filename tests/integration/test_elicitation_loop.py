"""Elicitation end to end, over the `warehouse-sync` example (master plan §6C).

The example is built for this: its case is detailed about how the service is bound and
silent about exactly one thing — whether a second warehouse is coming — and two of its five
boundaries turn on that silence while three are decidable from what the case already says.
`elicitation.yaml` beside it records which is which, and is read here rather than restated,
so the fixture and the test cannot drift apart into two different claims about the same
repository.

What is defended is the path and the loop, not what a model concludes. These run against
the deterministic substitute, so the assertions hold whatever the reasoning provider says:
the questions reach the report, they are grounded in boundaries of that review, they are
numbered by the application, they render, and answering one produces a review with nothing
left open. Whether a *model* notices the right silence is measured by
`scripts/run_boundary_review.py` against a live provider, which is a different question and
cannot be asserted offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from archcompass.application.review_rendering import render_review
from archcompass.bootstrap import Runtime
from archcompass.domain.case import ArchitectureCase, CaseField, CaseUpdate
from archcompass.domain.finding_detectors import detect_finding_candidates
from archcompass.domain.review import ReviewStatus

EXAMPLE = "warehouse-sync"
ROOT = Path(__file__).resolve().parent.parent.parent / "eval" / "cases" / EXAMPLE
REPOSITORY = (ROOT / "repository").resolve()


def _elicitation_key() -> dict[str, object]:
    return yaml.safe_load((ROOT / "elicitation.yaml").read_text(encoding="utf-8"))


def _loaded(runtime: Runtime) -> str:
    """The example as the workspace loads it: indexed, and a case created from its YAML."""

    return runtime.bundled_case_service.load(EXAMPLE).case_id


def test_the_example_is_offered_by_the_workspace(runtime: Runtime) -> None:
    """It has to be pickable in the browser, which means it has to be discovered."""

    offered = {item.name: item for item in runtime.bundled_case_service.list()}

    assert EXAMPLE in offered, "the example must appear beside the others in the workspace"
    summary = offered[EXAMPLE]
    assert summary.title == "Keeping stock in step with the warehouse"
    # No verdict key on purpose: two of its verdicts are contingent by construction, so a
    # scored answer for them would settle the question the case refuses to settle.
    assert summary.has_expected_answers is False


def test_the_example_still_produces_the_five_boundaries_it_grades(runtime: Runtime) -> None:
    """The key names abstractions; if detection drifts, the key silently grades nothing.

    Checked against the detector rather than a review, because this is a property of the
    repository and the catalogue and must fail here — loudly, and without a model — rather
    than as an unexplained gap in a live run's score weeks later.
    """

    atlas = runtime.analyzer.analyze(REPOSITORY)
    found = {
        candidate.participants[0].qualified_name
        for candidate in detect_finding_candidates(atlas)
    }
    key = _elicitation_key()
    named = {item["abstraction"] for item in key["hinged"]} | {
        item["abstraction"] for item in key["not_hinged"]
    }

    assert named <= found, (
        f"elicitation.yaml names boundaries the detector no longer finds: {named - found}"
    )
    assert found == named, (
        f"the repository grew a boundary the key does not cover: {found - named}"
    )


def test_a_thin_case_is_reviewed_and_then_asked_about(runtime: Runtime) -> None:
    """The whole point: value first, and the questions after it.

    A review must be complete before anything is asked. An advisor that opens by demanding
    a better case has put its price ahead of its value, which is the adoption tax
    elicitation exists to remove.
    """

    case_id = _loaded(runtime)

    review = runtime.review_service.review(case_id, repository_root=REPOSITORY)

    assert review.status is ReviewStatus.SUCCEEDED
    report = review.report
    assert report is not None
    assert len(report.reviewed) == 5, "every boundary is judged, thin case or not"
    for item in report.reviewed:
        assert item.rationale, "a contingent verdict is still a verdict with reasoning"

    questions = report.overview.open_questions
    assert questions, "a case this thin must leave something worth asking"

    known = {item.reference for item in report.reviewed}
    for question in questions:
        assert set(question.supporting_references) <= known
        assert question.answer_belongs_in in set(CaseField)
        assert question.question.strip()
        assert question.unknown.strip()


def test_the_application_numbers_the_questions(runtime: Runtime) -> None:
    """`Q-n` is a reference a reader cites, so it cannot be a value a model wrote."""

    case_id = _loaded(runtime)

    review = runtime.review_service.review(case_id, repository_root=REPOSITORY)

    report = review.report
    assert report is not None
    questions = report.overview.open_questions
    assert [item.reference for item in questions] == [
        f"Q-{position}" for position in range(1, len(questions) + 1)
    ]


def test_a_question_consolidates_the_boundaries_that_share_its_unknown(
    runtime: Runtime,
) -> None:
    """Several verdicts turning on one fact are one question, not several (§6C.2).

    Asked once with its boundaries cited, it is the most useful sentence in the report;
    asked once per boundary it is noise that buries the verdicts underneath it.
    """

    case_id = _loaded(runtime)

    review = runtime.review_service.review(case_id, repository_root=REPOSITORY)

    report = review.report
    assert report is not None
    hinged = [item for item in report.reviewed if item.hinge]
    questions = report.overview.open_questions
    assert hinged, "this example must produce at least one contingent verdict"
    assert len(questions) <= len(hinged), "questions are merged from hinges, never multiplied"
    cited = {
        reference for question in questions for reference in question.supporting_references
    }
    assert cited == {item.reference for item in hinged}, (
        "every hinged boundary is asked about, and nothing else is"
    )


def test_the_hinges_and_the_questions_both_reach_the_page(runtime: Runtime) -> None:
    """A hinge prints against its own boundary; the question prints once, with citations."""

    case_id = _loaded(runtime)

    review = runtime.review_service.review(case_id, repository_root=REPOSITORY)

    report = review.report
    assert report is not None
    markdown = render_review(review)
    assert review.markdown_report == markdown
    assert "### What the case does not say" in markdown
    for question in report.overview.open_questions:
        assert question.question in markdown
        assert question.answer_belongs_in.value in markdown
        for reference in question.supporting_references:
            assert reference in markdown
    # And beside each boundary that carried one, where a reader decides whether to act.
    for item in report.reviewed:
        if item.hinge:
            assert item.hinge.unknown in markdown


def test_answering_the_question_closes_the_loop(runtime: Runtime) -> None:
    """The mechanism, run twice against one repository.

    Only the case changes between these two reviews, which is the difference the whole
    product turns on. The answer is written the way §6C.4 requires — a user-authored case
    revision through the loop that already exists — and the second review is pinned to it.
    """

    case_id = _loaded(runtime)
    first = runtime.review_service.review(case_id, repository_root=REPOSITORY)
    report = first.report
    assert report is not None
    questions = report.overview.open_questions
    assert questions, "there must be something to answer"

    # The answer goes where the question said it belongs, and nowhere else.
    question = questions[0]
    assert question.answer_belongs_in is CaseField.EXPECTED_FUTURE_CHANGES
    answered = runtime.case_service.update(
        case_id,
        CaseUpdate(
            expected_future_changes=[
                "A second warehouse is under contract and arrives next quarter. "
                "Both stay in service; neither replaces the other."
            ]
        ),
        actor="operator",
    )
    assert answered.revision == 2, "an answer is a new revision, never an edit"

    second = runtime.review_service.review(case_id, repository_root=REPOSITORY)

    later = second.report
    assert later is not None
    assert later.overview.open_questions == [], "an answered case is not asked again"
    assert not any(item.hinge for item in later.reviewed)
    # Both reviews survive, each pinned to the revision it ran against — nothing was
    # overwritten and there is nothing to reconcile.
    assert first.case_revision == 1
    assert second.case_revision == 2
    assert len(later.reviewed) == len(report.reviewed)


def test_the_case_ships_silent_on_the_fact_its_key_says_is_missing(runtime: Runtime) -> None:
    """The fixture's premise, asserted rather than trusted.

    If someone later fills in `expected_future_changes` to make the example read better,
    every test above still passes against the substitute while the example quietly stops
    measuring anything. This is the one assertion that catches that.
    """

    del runtime
    case = ArchitectureCase.model_validate(
        yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    )

    assert case.expected_future_changes == [], (
        "the example is built on this silence; stating a future change removes what it measures"
    )
    stated = " ".join(
        [
            case.problem_statement,
            case.desired_outcome,
            *case.technical_constraints,
            *case.non_goals,
            *(item.text for item in case.confirmed_facts),
        ]
    ).casefold()
    assert "second warehouse" not in stated, "the withheld fact must not leak in elsewhere"


@pytest.mark.parametrize("field", ["hinged", "not_hinged"])
def test_the_key_explains_every_boundary_it_grades(field: str) -> None:
    """A key entry without a reason is a claim nobody can check or argue with."""

    for entry in _elicitation_key()[field]:
        assert entry["abstraction"].strip()
        assert len(entry["because"].split()) > 15, (
            f"{entry['abstraction']} is graded without saying why"
        )
