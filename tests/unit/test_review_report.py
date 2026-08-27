"""The document a review becomes when it leaves the product.

The report is read where the workbench is not: in a pull request comment, in a terminal, in
a decision log six months later. Every claim here is a charter rule that a Markdown file has
to keep on its own, without a gutter, a colour or anything to click.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from archcompass.domain import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Evidence,
    Finding,
    Participant,
    Policy,
    PolicyBearing,
    PolicyScope,
    PolicyStrength,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
    ReviewStatus,
    SourceLocation,
    Verdict,
)
from archcompass.domain.case import Question
from archcompass.domain.values import Measurement, MetricNature
from archcompass.ports.capabilities import ReviewSynopsis
from archcompass.workflow.report import compose_markdown_report

REPOSITORY = RepositoryRef(
    id="repo-1",
    path=Path("/work/payments-platform"),
    branch_id="branch-1",
    content_id="content-1",
    branch="main",
    commit="8f31c2a91b4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f",
)

ATLAS = RepositoryAtlas(
    id="atlas-1",
    repository=REPOSITORY,
    nodes=("a", "b", "c"),
    edges=("a->b",),
    parser_configuration=(("parser", "python-ast"),),
)

POLICY = Policy(
    id="dependency-direction",
    title="Dependencies point inward",
    body="## Rule\n\nAdapters depend on the domain.",
    scope=PolicyScope.GENERAL,
    strength=PolicyStrength.REQUIRED,
    content_hash="hash-1",
)


def candidate(name: str, *, pattern: str = "dependency_direction", summary: str) -> Candidate:
    return Candidate.identified(
        pattern=pattern,
        summary=summary,
        participants=(
            Participant(qualified_name=name, role="source"),
            Participant(qualified_name="adapters.db.Store", role="target"),
        ),
        evidence=(
            Evidence(
                description="The domain module imports the persistence adapter directly",
                location=SourceLocation(path="domain/orders.py", start_line=4, end_line=9),
                excerpt="from adapters.db import Store",
            ),
        ),
        measurements=(
            Measurement(name="imports", value=1, unit="imports"),
            Measurement(
                name="dependants_of_abstraction",
                value=0,
                unit="references",
                nature=MetricNature.STRUCTURAL_PROXY,
            ),
        ),
        detection_rationale=(
            "Detected deterministically from the repository atlas; participant fingerprint "
            "39cc5c2746aa271bb743b4c279cf6333b9b977a62d7da510fc663af9a336a0c4"
        ),
        limitations="Static imports only. Wiring resolved at runtime is not visible.",
    )


MATERIAL = Finding(
    candidate=candidate("domain.orders", summary="domain.orders depends on an adapter."),
    verdict=Verdict.MATERIAL,
    reasoning="the import reverses the intended direction of dependency",
    policies=(
        PolicyBearing(policy=POLICY, reasoning="The import may reverse the intended direction."),
    ),
    evidence=(),
    recommended_response="introduce a port owned by the domain",
    model_identity="fake:deterministic",
    prompt_identity="judge:v1",
)

HELD = Finding(
    candidate=candidate(
        "domain.invoices",
        pattern="sole_implementation",
        summary="domain.invoices is implemented once.",
    ),
    verdict=Verdict.HELD,
    reasoning="ownership determines whether this is intentional",
    policies=(),
    evidence=(),
    hinge="the constraints this architecture has to respect",
    model_identity="fake:deterministic",
    prompt_identity="judge:v1",
)

CLEARED = Finding(
    candidate=candidate(
        "domain.billing",
        pattern="boundary_shape",
        summary="The billing boundary is appropriate.",
    ),
    verdict=Verdict.CLEARED,
    reasoning="the boundary is where the case says it should be",
    policies=(),
    evidence=(),
    model_identity="fake:deterministic",
    prompt_identity="judge:v1",
)


def case(*, revision: int = 2) -> ArchitectureCase:
    answered = Question.create(
        text="Is Stripe the only provider this has to support?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate-1",),
        round=1,
    )
    return ArchitectureCase(
        id="case-1",
        revision=revision,
        answers=(
            Answer(
                answered,
                AnswerStatus.ANSWERED,
                "Stripe is the only provider today",
                "architect",
                datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def previous_review() -> Review:
    return Review(
        id="review-0",
        sequence=1,
        repository=REPOSITORY,
        atlas=ATLAS,
        case=case(revision=1),
        findings=(),
        questions=(),
        status=ReviewStatus.COMPLETED,
        delta=ReviewDelta(),
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def report(**overrides: object) -> str:
    arguments: dict[str, object] = {
        "repository": REPOSITORY,
        "atlas": ATLAS,
        "case": case(),
        "findings": (MATERIAL, HELD, CLEARED),
        "questions": (),
        "delta": ReviewDelta(new=(MATERIAL.candidate,), unchanged=(CLEARED.candidate,)),
        "previous": previous_review(),
        "retrievers": ("dense-scoped/1",),
        "sequence": 2,
        "waiting": False,
    }
    arguments.update(overrides)
    return compose_markdown_report(**arguments)  # type: ignore[arg-type]


def test_a_heading_names_the_code_rather_than_describing_it() -> None:
    """The bug this replaced: `## <the whole summary sentence>`.

    "Scanning beats reading" is a charter rule about the queue and it holds harder in a
    document, where there is no rail to fall back on. A heading is what a reader's eye lands
    on and what a search finds, so it is the identifier; the sentence keeps its place
    directly underneath.
    """

    text = report()

    assert "### `domain.orders`" in text
    assert "## domain.orders depends on an adapter." not in text
    heading = text.index("### `domain.orders`")
    summary = text.index("domain.orders depends on an adapter.", heading)
    assert text[heading:summary].count("\n") <= 3


def test_verdicts_are_grouped_in_the_order_that_needs_a_human() -> None:
    text = report()

    assert text.index("## Material") < text.index("## Held") < text.index("## Cleared")
    # And every group says what its word means, because a document has no colour to lean on
    # and "held" is not a word a reader arrives already knowing.
    assert "Judgement is waiting on context the repository cannot supply." in text


def test_the_three_jobs_stay_apart_without_a_gutter() -> None:
    """The workbench separates them with a column; a document has run-in labels instead."""

    text = report()

    assert "**Measured.**" in text
    assert "**Judged material.**" in text
    # No third label: what the team decided is a separate record, and the report says so
    # rather than leaving a reader to assume the absence means nobody decided anything.
    assert "**Decided" not in text
    assert "recorded separately as standing decisions on the branch" in text


def test_a_cleared_candidate_keeps_its_reasoning_and_loses_its_readings() -> None:
    """A report of only problems reads the same whether everything was examined and cleared
    or nothing was examined at all — so cleared candidates keep a heading and the reasoning
    that cleared them. What they lose is the measurement paragraph, which is what would turn
    forty of them into a document nobody finishes.
    """

    text = report()

    cleared = text[text.index("## Cleared") :]
    assert "### `domain.billing`" in cleared
    assert "**Judged cleared.** The boundary is where the case says it should be." in cleared
    assert "**Measured.**" not in cleared


def test_a_measurement_keeps_its_own_honesty_and_its_grammar() -> None:
    text = report()

    assert "1 import" in text and "1 imports" not in text
    assert "0 references (a structural proxy, not a count)" in text


def test_a_detector_id_does_not_leak_into_the_prose() -> None:
    """`detection_rationale` carries a fingerprint. The clause is the sentence; the hash is
    an id, and an id mid-paragraph is the workbench's Technical detail in the wrong place."""

    text = report()

    assert "detected deterministically from the repository atlas" in text
    assert "39cc5c2746aa271b" not in text


def test_a_hinge_is_stated_and_does_not_run_into_the_next_sentence() -> None:
    """And says the right thing about it, which depends on whether anyone can still answer.

    A held finding keeps its hinge on both paths, so this used to assert the waiting
    sentence against a report composed with `waiting=False` — a concluded review, whose case
    revision is already sealed, telling its reader to answer. Both paths are asserted here
    because the defect was invisible while only one of them was.
    """

    concluded = report()

    assert (
        "**Unresolved.** The constraints this architecture has to respect. "
        "This review concluded without it" in concluded
    )
    assert "Answering it records" not in concluded

    asking = report(waiting=True)

    assert (
        "**Waiting on a person.** The constraints this architecture has to respect. "
        "Answering it records the answer on this review's case revision" in asking
    )


def test_an_identifier_in_a_summary_is_not_capitalised_into_something_else() -> None:
    text = report()

    assert "domain.invoices is implemented once." in text
    assert "Domain.invoices" not in text


def test_a_limitation_is_stated_once_however_many_findings_carry_it() -> None:
    """Three findings, three detectors, one limitation between them.

    Repeating the same sixty words under every finding teaches a reader to skip the
    paragraph, which is the opposite of what stating a limit is for. It is said once, under
    every detector it belongs to.
    """

    text = report()

    assert text.count("Static imports only.") == 1
    assert "**Boundary shape, Dependency direction, Sole implementation** —" in text
    assert "## What this review could not see" in text


def test_what_moved_is_a_section_named_by_identifier() -> None:
    text = report()

    moved = text[text.index("## What moved since review 1") :]
    assert "- `domain.orders`" in moved
    # Names, not sentences: the finding above already carries the sentence and this is a
    # list to be scanned for which things moved.
    assert "domain.orders depends on an adapter." not in moved


def test_a_first_review_says_it_has_nothing_to_compare_against() -> None:
    text = report(previous=None, sequence=1)

    assert "first review of this case" in text
    assert "since review" not in text


def test_a_waiting_review_says_it_is_not_final_and_asks_its_questions() -> None:
    question = Question.create(
        text="Who owns persistence?",
        facet=CaseFacet.DECISION,
        candidate_ids=(str(HELD.candidate.id),),
        round=1,
        options=("The domain owns it", "The persistence layer owns it"),
    )

    text = report(waiting=True, questions=(question,))

    assert "**Not final.**" in text
    assert "## Open questions — 1" in text
    assert "Who owns persistence?" in text
    assert "The domain owns it" in text


def test_a_concluded_review_calls_its_leftovers_what_they_are() -> None:
    """Concluding with remaining uncertainty is a decision somebody took, not an oversight."""

    question = Question.create(
        text="Who owns persistence?",
        facet=CaseFacet.DECISION,
        candidate_ids=(str(HELD.candidate.id),),
        round=1,
    )

    text = report(waiting=False, questions=(question,))

    assert "## Left unanswered — 1" in text
    assert "concluded with these still unanswered" in text
    assert "**Not final.**" not in text


def test_the_footer_says_where_every_part_of_it_came_from() -> None:
    text = report()

    assert "`fake:deterministic`" in text
    assert "`judge:v1`" in text
    assert "`dense-scoped/1`" in text
    assert "3 nodes and 1 edge" in text
    assert "`parser=python-ast`" in text
    # Shortened where the line is scanned, whole where it is looked up.
    assert "commit `8f31c2a91b`" in text
    assert "commit `8f31c2a91b4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f`" in text


def test_the_footer_names_the_endpoints_that_answered_and_only_where_one_did() -> None:
    """"Judged by" names a model; a gateway serves one model from several endpoints.

    `google/gemini-3.5-flash-lite` has seven, they are not the same silicon or the same
    sampler, and which one answered is the gateway's decision rather than a selection
    anybody made — so it is a separate line rather than more of the "judged by" one. Each
    finding stores its own comma-joined set, so a review's line is the union of them, said
    once however many findings answered from the same place.

    The second half is the part that has to keep holding for the rest of the corpus: with
    nothing recorded there is no line at all. A "— " there would read as a hosted route that
    failed to be recorded, and what is true of a local Ollama, of the deterministic
    stand-in, and of all 148 findings stored before the field existed is that there was no
    endpoint to name.
    """

    routed = report(
        findings=(
            replace(MATERIAL, served_by="Google AI Studio,Vertex"),
            replace(HELD, served_by="Vertex"),
            CLEARED,
        )
    )

    assert "- **Served by** `Google AI Studio`, `Vertex`" in routed
    assert "Served by" not in report()


def test_the_context_it_was_judged_against_is_printed_not_referenced() -> None:
    text = report()

    assert "Stripe is the only provider today" in text


def test_an_empty_case_says_so_rather_than_disappearing() -> None:
    text = report(case=ArchitectureCase(id="case-1", revision=1))

    assert "Case revision 1 is empty" in text
    assert "the code and the policy corpus alone" in text


def test_a_review_with_no_candidates_says_what_that_does_and_does_not_mean() -> None:
    text = report(findings=(), delta=ReviewDelta())

    assert "No architectural candidates were detected" in text
    assert "not a claim that the architecture is sound" in text


def test_the_same_review_composes_the_same_bytes() -> None:
    """Reports are diffed between revisions the way the reviews themselves are."""

    assert report() == report()
    assert "\n\n\n" not in report()


def test_the_report_opens_on_what_the_review_amounts_to() -> None:
    """The counts say how much there is; the summary says what it comes to.

    Under the counts rather than over them: the document opens on what was measured and only
    then on what somebody concluded from it. Labelled, because a document has no gutter and
    a run-in label is how every other model-authored block in here says whose voice it is.
    """

    text = report(
        synopsis=ReviewSynopsis(
            "both material findings reach past the ports layer", "google:gemini-3-pro"
        )
    )

    counts = text.index("Three candidates judged")
    summary = text.index("**In summary.**")
    material = text.index("## Material — 1")
    assert counts < summary < material
    assert "**In summary.** Both material findings reach past the ports layer." in text
    # Said where every other provenance is said, and apart from "judged by": a finding
    # carried forward was judged by whatever was selected then.
    assert "- **Summarised by** `google:gemini-3-pro`" in text


def test_a_report_with_nothing_to_summarise_opens_on_its_counts() -> None:
    """No summary is a state the document already had, not a hole in it."""

    text = report(synopsis=None)

    assert "**In summary.**" not in text
    assert "Summarised by" not in text
    assert "Three candidates judged" in text
