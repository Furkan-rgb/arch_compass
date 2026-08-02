"""The MVP advisory path end to end: index, detect, judge, compose, persist, render.

Runs against the deterministic reasoning substitute, so it covers the wiring without
asserting anything about what a real model concludes. The properties defended here must
hold whatever the model says.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from archcompass.adapters.models.deterministic import DETERMINISTIC_MODEL
from archcompass.application.review_rendering import render_review
from archcompass.bootstrap import Runtime
from archcompass.domain.atlas import FindingPattern, NodeType
from archcompass.domain.case import ArchitectureCase, RepositoryReference
from archcompass.domain.errors import AtlasNotFoundError
from archcompass.domain.review import ReviewStatus
from archcompass.presentation.cli.app import app

FIXTURE = Path("eval/cases/speech-vendor/repository").resolve()


def _case(repository: Path) -> ArchitectureCase:
    return ArchitectureCase(
        title="Provider variation",
        problem_statement="Decide where provider-specific knowledge should live.",
        desired_outcome="One owner for provider differences.",
        expected_future_changes=["A hosted provider may be added later"],
        repository=RepositoryReference(root_path=str(repository)),
    )


def _indexed_case(runtime: Runtime) -> str:
    atlas = runtime.analyzer.analyze(FIXTURE)
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_repository.create(_case(FIXTURE), actor="test")
    return revision.case_id


def test_every_boundary_in_the_repository_is_judged_and_kept(runtime: Runtime) -> None:
    case_id = _indexed_case(runtime)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    interfaces = [
        node
        for node in runtime.analyzer.analyze(FIXTURE).nodes
        if node.node_type is NodeType.INTERFACE
    ]
    assert interfaces, "fixture must declare an abstraction for this path to exercise"
    assert review.status is ReviewStatus.SUCCEEDED
    report = review.report
    assert report is not None
    assert report.reviewed
    # Every reviewed item is a shape the catalogue knows, and the abstraction-shaped half
    # is present. Not "every item is sole_implementation" any more: the second direction of
    # the catalogue ships, and this fixture carries repetition as well as indirection.
    assert {item.candidate.pattern for item in report.reviewed} <= set(FindingPattern)
    assert any(
        item.candidate.pattern is FindingPattern.SOLE_IMPLEMENTATION
        for item in report.reviewed
    )
    # Material and cleared partition the reviewed set. A cleared boundary is a result, not
    # a filtered-out intermediate, so nothing may be dropped between the two.
    assert len(report.material) + len(report.cleared) == len(report.reviewed)


def test_a_review_is_stored_and_can_be_read_back(runtime: Runtime) -> None:
    """Everything downstream — reports, the web workspace, follow-up questions — needs this."""

    case_id = _indexed_case(runtime)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)
    stored = runtime.review_repository.get(review.review_id)

    assert stored == review
    assert [item.review_id for item in runtime.review_repository.list()] == [
        review.review_id
    ]


def test_a_review_pins_the_exact_inputs_that_produced_it(runtime: Runtime) -> None:
    case_id = _indexed_case(runtime)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    atlas = runtime.atlas_repository.latest_for_path(FIXTURE)
    assert atlas is not None
    assert review.atlas_version_id == atlas.version.version_id
    assert review.case_revision == runtime.case_repository.get(case_id).revision
    assert review.prompt_identity.startswith("judge-finding-candidate:")


def test_boundary_references_are_assigned_by_the_application(runtime: Runtime) -> None:
    """A reader cites BR-001; nothing the model wrote is ever that value (12.0)."""

    case_id = _indexed_case(runtime)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    report = review.report
    assert report is not None
    assert [item.reference for item in report.reviewed] == [
        f"BR-{ordinal:03d}" for ordinal in range(1, len(report.reviewed) + 1)
    ]


def test_judgement_sees_the_whole_policy_corpus(runtime: Runtime) -> None:
    """No retrieval, no ranking: the corpus is small enough to present entire."""

    case_id = _indexed_case(runtime)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    catalog = runtime.policy_service.catalog(repository_root=FIXTURE)
    report = review.report
    assert report is not None
    assert set(report.policies_presented) == {policy.id for policy in catalog}


def test_every_recorded_bearing_names_a_policy_that_was_presented(runtime: Runtime) -> None:
    """Position resolves to identity, so an unknown policy ID cannot appear."""

    case_id = _indexed_case(runtime)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    report = review.report
    assert report is not None
    presented = set(report.policies_presented)
    for item in report.reviewed:
        for bearing in item.policy_bearings:
            assert bearing.policy_id in presented


def test_the_rendered_report_shows_cleared_boundaries_too(runtime: Runtime) -> None:
    """A report listing only problems reads the same whether it looked or not."""

    case_id = _indexed_case(runtime)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    markdown = render_review(review)
    assert review.markdown_report == markdown
    report = review.report
    assert report is not None
    if report.cleared:
        assert "Examined and left alone" in markdown
    for item in report.reviewed:
        assert item.reference in markdown
    assert "policies were presented in full" in markdown


def test_a_review_says_what_its_verdicts_amount_to(runtime: Runtime) -> None:
    """The one thing no per-boundary call can do: read the set as a set.

    What is defended here is the binding, not the prose. Every claim the overview makes
    names boundaries of this review, and the references it names were assigned by the
    application — so a summary cannot point at a boundary that was never judged.
    """

    case_id = _indexed_case(runtime)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    report = review.report
    assert report is not None
    overview = report.overview
    assert overview.situation
    assert overview.limits
    known = {item.reference for item in report.reviewed}
    statements = [*overview.themes, *overview.recommended_sequence]
    assert statements, "a review with material and cleared boundaries has something to say"
    for statement in statements:
        assert statement.supporting_references
        assert set(statement.supporting_references) <= known

    markdown = render_review(review)
    assert "## Conclusion" in markdown
    assert overview.situation in markdown
    # The citations are printed, so a reader who doubts a theme can reach the verdicts.
    assert statements[0].supporting_references[0] in markdown


def test_a_thin_case_is_reviewed_and_asked_about(runtime: Runtime) -> None:
    """Elicitation end to end (§6C): value first, then the questions that would sharpen it.

    The case here states no expected future change, which is what a first case written by
    someone evaluating the tool actually looks like. The run must still produce a full
    review — every boundary judged, cleared ones kept — and come back asking for what would
    settle the verdicts that turned on the silence.

    What is defended is the binding rather than the wording: every question names boundaries
    of this review, assigned by the application, and lands in a field the case really has.
    """

    atlas = runtime.analyzer.analyze(FIXTURE)
    runtime.atlas_repository.save(atlas)
    thin = _case(FIXTURE).model_copy(update={"expected_future_changes": []})
    case_id = runtime.case_repository.create(thin, actor="test").case_id

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    report = review.report
    assert report is not None
    assert report.reviewed, "a thin case must still get a full review"
    questions = report.overview.open_questions
    assert questions, "verdicts that turned on the silence must be asked about"

    known = {item.reference for item in report.reviewed}
    case_fields = set(ArchitectureCase.model_fields)
    for question in questions:
        assert question.supporting_references
        assert set(question.supporting_references) <= known
        # The destination has to be somewhere an answer can actually go, or the answer
        # path has nowhere to put it.
        assert question.answer_belongs_in.value in case_fields

    assert [item.reference for item in questions] == [
        f"Q-{position}" for position in range(1, len(questions) + 1)
    ]
    # Consolidated rather than repeated: several boundaries turning on one silence are one
    # question, which is the whole reason this is composed over the set.
    assert len(questions) < len(report.reviewed)

    markdown = render_review(review)
    assert "What it needs to know" in markdown
    assert questions[0].question in markdown


def test_a_case_that_answers_the_question_is_not_asked_it_again(runtime: Runtime) -> None:
    """The loop closes: an answered case produces a review with nothing left open.

    This is the mechanism elicitation exists for, run twice against the same repository —
    the only difference is what the case says, which is the difference the whole product
    turns on.
    """

    case_id = _indexed_case(runtime)

    review = runtime.review_service.review(case_id, repository_root=FIXTURE)

    report = review.report
    assert report is not None
    assert report.overview.open_questions == []
    assert not any(item.hinge for item in report.reviewed)


def test_a_summarising_step_is_reported_before_it_runs(runtime: Runtime) -> None:
    """A caller has to be able to say what the run is doing after the last verdict."""

    case_id = _indexed_case(runtime)
    order: list[str] = []

    runtime.review_service.review(
        case_id,
        repository_root=FIXTURE,
        on_verdict=lambda judged, position, total: order.append(f"judged-{position}"),
        on_summarising=lambda: order.append("summarising"),
    )

    assert order[-1] == "summarising"
    assert order[:-1] == [f"judged-{position}" for position in range(1, len(order))]


def test_an_unindexed_repository_says_so_instead_of_reviewing_nothing(
    runtime: Runtime,
    tmp_path: Path,
) -> None:
    """Zero boundaries and no atlas would render identically. They must not."""

    revision = runtime.case_repository.create(_case(tmp_path), actor="test")

    with pytest.raises(AtlasNotFoundError, match="repo index"):
        runtime.review_service.review(
            revision.case_id,
            repository_root=tmp_path,
        )


def test_the_cli_reports_the_review_it_reached(runtime: Runtime, tmp_path: Path) -> None:
    case_id = _indexed_case(runtime)

    result = CliRunner().invoke(
        app,
        [
            "--workspace",
            str(tmp_path),
            # Named rather than chosen: this process builds its own runtime, and a workspace
            # that has chosen nothing reasons with nothing.
            "--provider",
            "fake",
            "--model",
            DETERMINISTIC_MODEL,
            "review",
            case_id,
            "--repo",
            str(FIXTURE),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "# Boundary review" in result.output
    assert "boundaries reviewed against" in result.output or "boundary reviewed" in result.output
