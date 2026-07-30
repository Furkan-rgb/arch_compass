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

import shutil
from pathlib import Path

import pytest
import yaml

from archcompass.application.cases import WrittenAnswer
from archcompass.application.review_rendering import render_review
from archcompass.application.reviews import UNSTATED_CASE
from archcompass.bootstrap import Runtime
from archcompass.domain.case import ArchitectureCase, CaseField, CaseUpdate
from archcompass.domain.errors import (
    CaseRevisionConflictError,
    CaseValidationError,
    ConversationNotFoundError,
    PersistenceError,
)
from archcompass.domain.finding_detectors import detect_finding_candidates
from archcompass.domain.review import ReviewEvidence, ReviewStatus

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


def test_a_thin_case_is_judged_in_full_and_then_holds(runtime: Runtime) -> None:
    """Investigate first, then ask — and do not report until the asking is answered.

    Both halves matter. Every boundary is judged before anything is asked, because a
    question asked before looking is generic and the specific ones are the residue of real
    judgement. And the run then stops rather than reporting, because verdicts reached
    against a case this thin are provisional: on this very example, four of five moved once
    the questions were answered (ADR 0010).
    """

    case_id = _loaded(runtime)

    review = runtime.review_service.review(case_id, repository_root=REPOSITORY)

    assert review.status is ReviewStatus.AWAITING_ANSWERS
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

    # A first pass asks; it does not conclude. Its overview is composed by the application
    # from facts already known, so no model call was spent writing a synthesis of a case
    # that has not been written yet.
    assert report.overview.themes == []
    assert report.overview.recommended_sequence == []


def test_a_review_that_is_still_asking_is_not_a_finished_review(runtime: Runtime) -> None:
    """The status, and the document, both have to stop claiming otherwise.

    Before this, a first pass was stored as `succeeded` and rendered its verdicts under
    "what should change" — so a run holding questions nobody had answered read as a finished
    review, for ever, in every listing. The verdicts exist and are kept; what changes is that
    nothing presents them as findings until they have been through a second pass.
    """

    case_id = _loaded(runtime)

    review = runtime.review_service.review(case_id, repository_root=REPOSITORY)

    assert review.awaiting_answers
    listed = runtime.review_repository.list()
    assert [item.status for item in listed if item.review_id == review.review_id] == [
        "awaiting_answers"
    ]

    markdown = render_review(review)
    assert "waiting on answers" in markdown
    assert "## What should change" not in markdown
    assert "## Examined and left alone" not in markdown
    # The verdicts are held, not lost: every boundary was judged and the document says so
    # rather than reading like a run that gave up part-way.
    report = review.report
    assert report is not None
    assert len(report.reviewed) == 5
    assert "all 5 boundaries were judged" in markdown


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


def test_the_questions_reach_the_page_with_their_citations(runtime: Runtime) -> None:
    """Each question prints once, saying which verdicts it would settle and where it lands.

    The citations are the reason a reader can tell a question worth answering from one that
    changes nothing, and they are the only thing on this document pointing at the held
    verdicts — so they have to survive into the text rather than existing only as data.
    """

    case_id = _loaded(runtime)

    review = runtime.review_service.review(case_id, repository_root=REPOSITORY)

    report = review.report
    assert report is not None
    markdown = render_review(review)
    assert review.markdown_report == markdown
    assert "## What it needs to know" in markdown
    for question in report.overview.open_questions:
        assert question.question in markdown
        assert question.answer_belongs_in.value in markdown
        for reference in question.supporting_references:
            assert reference in markdown


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

    second = runtime.review_service.review(
        case_id,
        repository_root=REPOSITORY,
        elicited_from=first.review_id,
    )

    assert second.status is ReviewStatus.SUCCEEDED, "the second pass concludes"
    later = second.report
    assert later is not None
    assert later.overview.open_questions == [], "an answered case is not asked again"
    assert not any(item.hinge for item in later.reviewed)
    # Both reviews survive, each pinned to the revision it ran against — nothing was
    # overwritten and there is nothing to reconcile. The link between them is stored rather
    # than inferred from adjacency, so revising the case by hand cannot be mistaken for this.
    assert first.case_revision == 1
    assert second.case_revision == 2
    assert first.elicited_from is None
    assert second.elicited_from == first.review_id
    assert len(later.reviewed) == len(report.reviewed)


def test_a_second_pass_cannot_open_a_fresh_round_of_questions(runtime: Runtime) -> None:
    """What makes the loop terminate, asserted where a reader would look for the rule.

    A reader may answer nothing, or answer one of five. The verdicts that still hinge are
    reported as findings with their contingency stated, never as another gate: a second pass
    that could ask again would leave the flow with no way to end. The rule is enforced by the
    summarising stage having no field for a question, so it holds whatever a model returns.
    """

    case_id = _loaded(runtime)
    first = runtime.review_service.review(case_id, repository_root=REPOSITORY)
    assert first.awaiting_answers

    # Deliberately no answer at all: the case is untouched, so every hinge that made the
    # first pass stop is still open when the second one runs.
    second = runtime.review_service.review(
        case_id,
        repository_root=REPOSITORY,
        elicited_from=first.review_id,
    )

    assert second.status is ReviewStatus.SUCCEEDED
    later = second.report
    assert later is not None
    assert later.overview.open_questions == [], "a second pass never asks"
    assert any(item.hinge for item in later.reviewed), (
        "the contingency is still real and is reported on the boundary rather than hidden"
    )
    markdown = render_review(second)
    assert "## What it needs to know" not in markdown
    assert "turns on an open question" in markdown


def test_a_review_waiting_on_answers_survives_the_workspace_stopping(
    runtime: Runtime,
) -> None:
    """The hold is durable because it is a status, not something a page remembers.

    A workspace that restarts reports every row still marked `running` as failed, because a
    run cannot outlive the process holding its request. A run waiting on a person is the
    opposite case: nothing is executing, and the wait is exactly what should still be there
    tomorrow. Sweeping it up with the abandoned runs would lose the questions and the
    verdicts behind them.
    """

    case_id = _loaded(runtime)
    review = runtime.review_service.review(case_id, repository_root=REPOSITORY)
    assert review.awaiting_answers

    abandoned = runtime.review_repository.abandon_running(
        reason="The workspace stopped while this review was running."
    )

    assert abandoned == 0
    stored = runtime.review_repository.get(review.review_id)
    assert stored.status is ReviewStatus.AWAITING_ANSWERS
    assert stored == review, "nothing about it changed, including the questions it asked"


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


def test_a_review_runs_against_a_repository_with_no_case_written(runtime: Runtime) -> None:
    """The entry for someone who has not written a case (master plan §6C.1).

    The point of elicitation taken to its conclusion: point at code, get every boundary
    judged, and get back the questions that would settle them. Writing a case first is work
    nobody has to do until they have seen something.
    """

    runtime.repository_service.index(REPOSITORY)
    revision = runtime.case_service.start_from_repository(REPOSITORY)

    assert revision.snapshot.title == "Boundaries in repository"
    # Empty, not pre-filled. A placeholder problem statement would be read by the judging
    # stage as intent the user never expressed (invariant 23).
    assert revision.snapshot.problem_statement == ""
    assert revision.snapshot.desired_outcome == ""

    review = runtime.review_service.review(revision.case_id, repository_root=REPOSITORY)

    assert review.status is ReviewStatus.AWAITING_ANSWERS
    report = review.report
    assert report is not None
    assert len(report.reviewed) == 5, "an unwritten case still gets every boundary judged"
    assert report.overview.open_questions, "and must come back asking for what it lacked"
    # The report says the case was unwritten rather than printing a blank heading.
    assert report.problem_and_desired_outcome == UNSTATED_CASE
    assert UNSTATED_CASE in render_review(review)


def test_answering_carries_the_same_boundaries_forward(runtime: Runtime) -> None:
    """Continuing is a second pass over the same repository, not a different question.

    The atlas does not change, so the same boundaries are judged again against a case that
    now says more. That is what makes the two passes comparable — and what makes a verdict
    that moved attributable to the answer rather than to anything else.
    """

    runtime.repository_service.index(REPOSITORY)
    revision = runtime.case_service.start_from_repository(REPOSITORY)
    first = runtime.review_service.review(revision.case_id, repository_root=REPOSITORY)

    runtime.case_service.update(
        revision.case_id,
        CaseUpdate(expected_future_changes=["A second warehouse arrives next quarter."]),
        actor="operator",
    )
    second = runtime.review_service.review(
        revision.case_id,
        repository_root=REPOSITORY,
        elicited_from=first.review_id,
    )

    before = first.report
    after = second.report
    assert before is not None and after is not None
    assert [item.candidate.summary for item in after.reviewed] == [
        item.candidate.summary for item in before.reviewed
    ]
    assert first.atlas_version_id == second.atlas_version_id
    assert (first.case_revision, second.case_revision) == (1, 2)


def _waiting(runtime: Runtime) -> tuple[str, list[str]]:
    """A first pass that stopped to ask, with the references of what it asked."""

    case_id = _loaded(runtime)
    review = runtime.review_service.review(case_id, repository_root=REPOSITORY)
    assert review.status is ReviewStatus.AWAITING_ANSWERS
    report = review.report
    assert report is not None
    return review.review_id, [item.reference for item in report.overview.open_questions]


def test_a_review_still_asking_refuses_to_discuss_itself_but_will_discuss_a_question(
    runtime: Runtime,
) -> None:
    """The two conversations a waiting review can be asked for, and why only one opens.

    Refusing both would tell a reader who does not understand the question that they must
    answer it before they may ask about it, which is §6C.5's adoption tax in its purest
    form. Allowing both would hand over the withheld verdicts through a side door. What
    separates them is scope: a question-scoped discussion is shown the boundaries that
    question cites and no others (§6C.7).
    """

    review_id, references = _waiting(runtime)
    assert references, "the example is built to leave something unstated"

    with pytest.raises(ConversationNotFoundError, match="waiting on answers"):
        runtime.review_conversation_service.create(review_id)

    conversation = runtime.review_conversation_service.create(
        review_id, question_reference=references[0]
    )

    assert conversation.question_reference == references[0]
    # Titled with the question, because that is what the thread is about and a reader will
    # have more than one of these open at once.
    assert references[0] in conversation.title


def test_a_discussion_never_sees_a_verdict_its_question_does_not_cite(
    runtime: Runtime,
) -> None:
    """The property that makes the stage safe to run while verdicts are withheld.

    Asserted through grounding, which is the only channel a boundary can come back out of:
    references are resolved from positional flags over exactly the boundaries that were
    presented, so a citation to an uncited boundary is unreachable rather than unlikely.
    """

    review_id, references = _waiting(runtime)
    stored = runtime.review_repository.get(review_id)
    report = stored.report
    assert report is not None
    question = next(
        item for item in report.overview.open_questions if item.reference == references[0]
    )
    cited = set(question.supporting_references)
    assert cited < {item.reference for item in report.reviewed}, (
        "this assertion is vacuous unless the question cites fewer than every boundary"
    )

    conversation = runtime.review_conversation_service.create(
        review_id, question_reference=references[0]
    )
    message = runtime.review_conversation_service.ask(
        conversation.conversation_id, "What are you actually asking me here?"
    )

    assert message.answer is not None
    assert set(message.answer.supporting_references) <= cited


def test_a_reference_the_review_never_asked_is_refused(runtime: Runtime) -> None:
    """`Q-n` is the application's own identifier, so the application resolves it (§12.0)."""

    review_id, _ = _waiting(runtime)

    with pytest.raises(ConversationNotFoundError, match="asked no question Q-99"):
        runtime.review_conversation_service.create(review_id, question_reference="Q-99")


def test_a_discussion_offers_a_phrasing_only_after_the_reader_has_said_something(
    runtime: Runtime,
) -> None:
    """It may help them reach an answer; it may not reach one on their behalf (§6C.5).

    The substitute proposes a phrasing only where the reader's turn settles something, which
    is the shape the contract asks a real model for. What is asserted here is the path — that
    a suggestion travels as its own field of the record rather than as prose a caller has to
    parse, and that an opening question produces none.
    """

    review_id, references = _waiting(runtime)
    conversation = runtime.review_conversation_service.create(
        review_id, question_reference=references[0]
    )

    opening = runtime.review_conversation_service.ask(
        conversation.conversation_id, "I do not follow what this question is asking."
    )
    assert opening.answer is not None
    assert opening.answer.suggested_answer == ""

    settled = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "Yes, a second warehouse is contracted for next quarter.",
    )

    assert settled.answer is not None
    assert settled.answer.suggested_answer


def test_discussing_a_question_writes_nothing_to_the_case_or_the_review(
    runtime: Runtime,
) -> None:
    """Invariant 25 across the new surface.

    A suggested phrasing is offered and nothing more. The case gains no revision, the review
    keeps the status and the questions it had, and the only way any of it reaches the case is
    the walk the reader completes themselves.
    """

    review_id, references = _waiting(runtime)
    before = runtime.review_repository.get(review_id)
    case_before = runtime.case_repository.get(before.case_id)

    conversation = runtime.review_conversation_service.create(
        review_id, question_reference=references[0]
    )
    runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "Yes, a second warehouse is contracted for next quarter.",
    )

    after = runtime.review_repository.get(review_id)
    assert after == before, "a discussion is not a change to the review it is about"
    assert runtime.case_repository.get(before.case_id).revision == case_before.revision


def test_a_discussion_is_given_the_case_the_review_pinned(runtime: Runtime) -> None:
    """The case guides the review, so it accompanies the review into the discussion.

    Not the answers being typed in this round — those batch into one revision and do not
    exist until the reader saves (§6C.4), so a stage reasoning from them would be reasoning
    from a reply they can still delete. What it gets is the pinned revision: what was written
    before, including answers from an earlier round.
    """

    review_id, references = _waiting(runtime)
    stored = runtime.review_repository.get(review_id)
    pinned = runtime.case_repository.get(stored.case_id, stored.case_revision).snapshot

    # The workspace's case moves on; this review's does not. A conversation about an old
    # review must be explained from what that review actually ran against.
    runtime.case_service.update(
        stored.case_id,
        CaseUpdate(non_goals=["Something written after this review ran."]),
        actor="operator",
    )

    conversation = runtime.review_conversation_service.create(
        review_id, question_reference=references[0]
    )
    message = runtime.review_conversation_service.ask(
        conversation.conversation_id, "What does my case already say about this?"
    )

    # The substitute counts what the case states rather than quoting it, so this asserts
    # arrival — and that what arrived was the pinned revision rather than the current one.
    assert message.answer is not None
    stated = len(pinned.expected_future_changes) + len(pinned.assumptions)
    assert f"case states {stated}" in message.answer.answer
    assert runtime.case_repository.get(stored.case_id).revision == stored.case_revision + 1


def test_answering_records_which_questions_it_answered(runtime: Runtime) -> None:
    """The arrow from a case line back to the question that produced it (§6C.4).

    Everything either side of an answer was already kept — the questions in the review that
    asked them, the case as an append-only history — and this is the join. Without it a
    second pass can report that four verdicts moved and cannot say which sentence moved any
    one of them.
    """

    review_id, references = _waiting(runtime)
    stored = runtime.review_repository.get(review_id)
    report = stored.report
    assert report is not None
    answered_reference = references[0]
    question = next(
        item for item in report.overview.open_questions if item.reference == answered_reference
    )

    revision = runtime.case_service.answer(
        stored,
        [
            WrittenAnswer(
                question_reference=answered_reference,
                recorded_text="Whether a second warehouse is coming — no, and none is planned.",
            )
        ],
    )

    assert revision.revision == stored.case_revision + 1
    assert revision.answered is not None
    assert revision.answered.review_id == review_id
    recorded = revision.answered.answers
    assert [item.question_reference for item in recorded] == [answered_reference]
    # The destination comes from the question, not from the request — the caller never named
    # one, so a client cannot route an answer into a list its question did not mention.
    assert recorded[0].answer_belongs_in is question.answer_belongs_in
    # And the line is in the case, in that list.
    entries = getattr(revision.snapshot, question.answer_belongs_in.value)
    written = [item if isinstance(item, str) else item.text for item in entries]
    assert "Whether a second warehouse is coming — no, and none is planned." in written


def test_a_reference_the_review_never_asked_is_refused_when_answering(
    runtime: Runtime,
) -> None:
    """`Q-n` is the application's own identifier, so the application resolves it (§12.0)."""

    review_id, _ = _waiting(runtime)
    stored = runtime.review_repository.get(review_id)

    with pytest.raises(CaseValidationError, match="asked no question Q-99"):
        runtime.case_service.answer(
            stored,
            [WrittenAnswer(question_reference="Q-99", recorded_text="Answering nothing.")],
        )

    # And nothing was written: a refused round leaves no revision behind.
    assert runtime.case_repository.get(stored.case_id).revision == stored.case_revision


def test_a_hand_edited_revision_records_no_answers(runtime: Runtime) -> None:
    """The absence is the distinction. Editing the case is not answering a review."""

    review_id, _ = _waiting(runtime)
    stored = runtime.review_repository.get(review_id)

    revision = runtime.case_service.update(
        stored.case_id,
        CaseUpdate(non_goals=["Something nobody was asked about."]),
        actor="operator",
    )

    assert revision.answered is None


def test_answering_one_review_twice_is_refused(runtime: Runtime) -> None:
    """One review is asked once, so it maps to at most one answering revision.

    Two guards, and the outer one fires first. Answering appends onto the revision the review
    pinned, so a second round finds the case has already moved past it and is refused as the
    stale write it is — before the unique index underneath ever has to decide.
    """

    review_id, references = _waiting(runtime)
    stored = runtime.review_repository.get(review_id)
    runtime.case_service.answer(
        stored,
        [WrittenAnswer(question_reference=references[0], recorded_text="Answered once.")],
    )

    with pytest.raises(CaseRevisionConflictError):
        runtime.case_service.answer(
            stored,
            [WrittenAnswer(question_reference=references[0], recorded_text="And again.")],
        )


def test_the_store_refuses_a_second_revision_answering_the_same_review(
    runtime: Runtime,
) -> None:
    """The backstop under the flow, reached by going around the service.

    `answer()` cannot produce this — its stale-revision check fires first — which is exactly
    why the constraint is in the schema. A property only the flow enforces is one a later
    caller can break with nothing noticing.
    """

    review_id, references = _waiting(runtime)
    stored = runtime.review_repository.get(review_id)
    revision = runtime.case_service.answer(
        stored,
        [WrittenAnswer(question_reference=references[0], recorded_text="Answered once.")],
    )

    with pytest.raises(PersistenceError):
        runtime.case_repository.append(
            revision.snapshot,
            expected_revision=revision.revision,
            event_type="user_update",
            actor="a caller going around the service",
            answered=revision.answered,
        )


def test_a_discussion_is_shown_code_only_for_the_boundaries_its_question_cites(
    runtime: Runtime,
) -> None:
    """The scope that makes the stage safe to run applies to the code as well.

    A question discussion sees the boundaries its question cites and no others, because the
    verdicts a first pass withholds must not reach it. Source follows the same list: reading
    the code behind a verdict the reader is not being shown would widen the input past the
    thing that makes this surface safe (ADR 0013).
    """

    review_id, references = _waiting(runtime)
    stored = runtime.review_repository.get(review_id)
    report = stored.report
    assert report is not None
    question = next(
        item for item in report.overview.open_questions if item.reference == references[0]
    )
    cited = set(question.supporting_references)
    assert cited < {item.reference for item in report.reviewed}, (
        "this assertion is vacuous unless the question cites fewer than every boundary"
    )

    scoped = [
        excerpt
        for reference in question.supporting_references
        for excerpt in runtime.review_source_service.for_review(stored, reference=reference)
    ]
    whole = runtime.review_source_service.for_review(stored)

    assert {item.reference for item in scoped} == cited
    # And the whole-review call, which the concluded-review conversation uses, does cover
    # every boundary — so the narrowing is the question discussion's, not the service's.
    assert {item.reference for item in whole} == {item.reference for item in report.reviewed}


def test_every_recorded_span_resolves_to_the_code_at_it(runtime: Runtime) -> None:
    """The claim the whole change rests on: the review always knew where the evidence was.

    Asserted against a real repository rather than a fixture, because the point is that the
    detector's spans are usable — a span that pointed at nothing readable would make the
    conversation's old refusal correct after all.
    """

    review_id, _ = _waiting(runtime)
    stored = runtime.review_repository.get(review_id)

    excerpts = runtime.review_source_service.for_review(stored)

    assert excerpts, "a review of a real repository records spans to read"
    for excerpt in excerpts:
        assert excerpt.location is not None, excerpt.qualified_name
        assert excerpt.text, f"{excerpt.qualified_name}: {excerpt.unavailable}"
        assert not excerpt.unavailable


def test_the_code_is_pinned_on_the_review_rather_than_reread(runtime: Runtime) -> None:
    """A review carries its evidence, so it can still be read after the repository moves on.

    This was a live read, on the reasoning that the span was pinned and the text could always
    be recovered from it. It could not: freshness is a single repository-wide fingerprint, so
    a comment appended to a file no finding cites took every excerpt in a review to a caption.
    That is the moment a review is most read — someone has started acting on it.
    """

    review_id, _ = _waiting(runtime)
    report = runtime.review_repository.get(review_id).report
    assert report is not None

    assert report.excerpts, "a completing review reads its spans and keeps them"
    assert {item.reference for item in report.excerpts} == {
        item.reference for item in report.reviewed
    }
    assert all(item.text for item in report.excerpts)


def test_pinned_code_outlives_an_unrelated_change_to_the_repository(
    runtime: Runtime,
    tmp_path: Path,
) -> None:
    """The regression, against a copy so the edit is real rather than simulated.

    The file edited is cited by no finding, which is the point: the lines that were judged
    are untouched, and re-reading refused to show them anyway because the fingerprint covers
    the whole repository.
    """

    repository = tmp_path / "repository"
    shutil.copytree(REPOSITORY, repository)
    runtime.repository_service.index(repository)
    case_id = runtime.case_service.start_from_repository(repository).case_id
    review = runtime.review_service.review(case_id, repository_root=repository)
    stored = runtime.review_repository.get(review.review_id)
    report = stored.report
    assert report is not None

    cited = {
        participant.location.path
        for boundary in report.reviewed
        for participant in boundary.candidate.participants
        if participant.location is not None
    }
    untouched = next(
        path
        for path in sorted(repository.rglob("*.py"))
        if str(path.relative_to(repository)) not in cited
    )
    untouched.write_text(
        untouched.read_text(encoding="utf-8") + "\n# edited after the review ran\n",
        encoding="utf-8",
    )

    # Non-vacuous by construction: the same review with its pinned copy removed is the old
    # behaviour, and it must refuse. Without this the test would pass on a repository the
    # edit happened not to make stale, asserting nothing.
    without_pinned = stored.model_copy(
        update={"report": report.model_copy(update={"excerpts": []})}
    )
    rereading = runtime.review_source_service.for_review(without_pinned)
    assert not any(item.text for item in rereading), (
        "the edit must make the atlas stale, or this test asserts nothing"
    )
    assert "changed since the review ran" in rereading[0].unavailable

    served = runtime.review_source_service.for_review(stored)

    assert served, "the review still answers with its evidence"
    assert all(item.text for item in served), (
        "an edit elsewhere in the repository must not take the judged lines away"
    )


def test_a_review_stored_before_excerpts_were_pinned_still_reads_its_code(
    runtime: Runtime,
) -> None:
    """The widening half: an older review holds none and falls back to reading the repository.

    This is why the field is optional with a default rather than a schema bump. A narrowed
    schema is re-run under ADR 0002; making every stored review unreadable to add a field
    whose absence has an obvious meaning would be paying that price for nothing.
    """

    review_id, _ = _waiting(runtime)
    stored = runtime.review_repository.get(review_id)
    assert stored.report is not None
    older = stored.model_copy(
        update={"report": stored.report.model_copy(update={"excerpts": []})}
    )

    served = runtime.review_source_service.for_review(older)

    assert served, "a review without pinned excerpts still resolves its spans"
    assert all(item.text for item in served)


def test_unfolding_more_lines_reads_now_and_keeps_what_was_judged(
    runtime: Runtime,
    tmp_path: Path,
) -> None:
    """Context is browsing, not evidence, so it may fail without costing the evidence.

    Surrounding lines were never recorded, so they can only come from the repository as it is
    now. When it has moved on the request keeps the pinned span rather than losing it — an
    excerpt that could not grow beats one that disappeared.
    """

    repository = tmp_path / "repository"
    shutil.copytree(REPOSITORY, repository)
    runtime.repository_service.index(repository)
    case_id = runtime.case_service.start_from_repository(repository).case_id
    review = runtime.review_service.review(case_id, repository_root=repository)
    stored = runtime.review_repository.get(review.review_id)
    reference = stored.report.reviewed[0].reference if stored.report else "BR-001"

    pinned = runtime.review_source_service.for_review(stored, reference=reference)
    grown = runtime.review_source_service.for_review(
        stored, reference=reference, context_lines=6
    )
    assert len(grown[0].text.splitlines()) > len(pinned[0].text.splitlines()), (
        "a fresh repository can still be unfolded"
    )

    (repository / "main.py").write_text(
        (repository / "main.py").read_text(encoding="utf-8") + "\n# moved on\n",
        encoding="utf-8",
    )
    after = runtime.review_source_service.for_review(
        stored, reference=reference, context_lines=6
    )

    assert all(item.text for item in after), "the judged lines survive a failed unfold"
    assert [item.text for item in after] == [item.text for item in pinned]


def test_the_stage_is_given_the_round_that_produced_the_review_it_answers_about(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression for "the review does not contain any record of previous questions".

    The two halves are stored apart and both correctly: a question is advisor output pinned
    in the pass that asked it, an answer is user-authored and belongs to the revision it
    created (invariant 25). Nothing joined them, so a reader asking a concluded review what
    they had answered was told no such record exists — accurate about the review in front of
    the stage, false about the workspace holding both halves.

    Walked end to end rather than asserted on the assembler, because the join runs across a
    review, its predecessor and a case revision, and a unit test of any one of them would
    have passed while this was broken.
    """

    case_id = _loaded(runtime)
    first = runtime.review_service.review(case_id, repository_root=REPOSITORY)
    report = first.report
    assert report is not None
    asked = report.overview.open_questions
    assert asked, "there must be something to answer"

    runtime.case_service.answer(
        first,
        [
            WrittenAnswer(
                question_reference=asked[0].reference,
                recorded_text="A second warehouse arrives next quarter; both stay in service.",
            )
        ],
        actor="operator",
    )
    second = runtime.review_service.review(
        case_id, repository_root=REPOSITORY, elicited_from=first.review_id
    )
    conversation = runtime.review_conversation_service.create(second.review_id)

    seen: list[ReviewEvidence] = []
    original = runtime.review_conversation_service._reasoner.answer_review_question

    def capture(review: object, evidence: ReviewEvidence, *rest: object) -> object:
        seen.append(evidence)
        return original(review, evidence, *rest)

    monkeypatch.setattr(
        runtime.review_conversation_service._reasoner,
        "answer_review_question",
        capture,
    )
    runtime.review_conversation_service.ask(
        conversation.conversation_id, "What were the questions and answers again?"
    )

    evidence = seen[0]
    assert evidence.answers_were_recorded
    # Every question the first pass asked, in the order it asked them. That a skipped one is
    # carried too is pinned where a fixture can produce two, in `test_review_answers`.
    assert [item.question.reference for item in evidence.elicitation] == [
        item.reference for item in asked
    ]
    assert evidence.elicitation[0].answer.startswith(
        "A second warehouse arrives next quarter"
    )
    # The question travels whole, not just its text: the stage is shown what the review saw
    # and which way the verdicts moved, which is what makes the answer worth reading back.
    assert evidence.elicitation[0].question.what_the_review_saw
    assert evidence.elicitation[0].question.why_it_matters


def test_a_first_pass_carries_no_round_because_it_has_asked_nothing_yet(
    runtime: Runtime,
) -> None:
    """A pass that asked its questions has not answered them, and must not imply it did.

    Its conversation is scoped to a single open question anyway (§6C.7), so the round it
    would describe is the one still being typed — the reader could be shown their own draft
    answers as though they were recorded.
    """

    case_id = _loaded(runtime)
    first = runtime.review_service.review(case_id, repository_root=REPOSITORY)
    report = first.report
    assert report is not None
    reference = report.overview.open_questions[0].reference

    evidence = runtime.review_conversation_service._evidence(
        first, about_question=report.overview.open_questions[0]
    )

    assert evidence.elicitation == []
    assert not evidence.answers_were_recorded
    # And the scope that makes a mid-review discussion safe is unchanged.
    assert {item.reference for item in evidence.excerpts} <= set(
        report.overview.open_questions[0].supporting_references
    ), reference
