from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.domain.case import (
    AnsweredQuestions,
    ArchitectureCase,
    CaseField,
    CaseStatement,
    CaseUpdate,
    Clarification,
    RecordedAnswer,
    StatementKind,
)


def test_case_revisions_are_append_only(runtime) -> None:
    created = runtime.case_service.create(
        ArchitectureCase(
            title="A case",
            problem_statement="A responsibility is unclear.",
            desired_outcome="Choose an owner.",
            functional_requirements=["First"],
        )
    )
    updated = runtime.case_service.update(
        created.case_id,
        CaseUpdate(title="Updated case", functional_requirements=["Replacement"]),
    )
    assert updated.revision == 2
    assert updated.snapshot.title == "Updated case"
    assert updated.snapshot.functional_requirements == ["Replacement"]
    history = runtime.case_service.history(created.case_id)
    assert [item.revision for item in history] == [1, 2]
    assert history[0].snapshot.title == "A case"


def test_case_update_revalidates_nested_statements(runtime) -> None:
    existing = CaseStatement(
        text="Where should discovery live?",
        kind=StatementKind.QUESTION,
        source="user",
    )
    created = runtime.case_service.create(
        ArchitectureCase(
            title="A case with a follow-up",
            problem_statement="A responsibility is unclear.",
            desired_outcome="Choose an owner.",
            unresolved_questions=[existing],
        )
    )

    updated = runtime.case_service.update(
        created.case_id,
        CaseUpdate(
            unresolved_questions=[
                *created.snapshot.unresolved_questions,
                CaseStatement(
                    text="What if discovery becomes remote?",
                    kind=StatementKind.QUESTION,
                    source="advisor_composer",
                ),
            ]
        ),
    )

    assert updated.revision == 2
    assert [item.text for item in updated.snapshot.unresolved_questions] == [
        "Where should discovery live?",
        "What if discovery becomes remote?",
    ]
    assert all(
        isinstance(item, CaseStatement)
        for item in updated.snapshot.unresolved_questions
    )


def test_a_clarification_is_revised_like_any_other_part_of_the_case(runtime) -> None:
    """Answering writes these, and the ordinary update path is how they are changed.

    The pair is the user's record of an exchange they took part in, so withdrawing an answer or
    rewording one is a case revision like any other rather than a special operation on the round
    that produced it — and the review that asked keeps its questions either way, immutable.
    """

    created = runtime.case_service.create(
        ArchitectureCase(
            title="A case with an answered question",
            clarifications=[
                Clarification(
                    question="Is a second warehouse actually planned?",
                    answer="No, and none is planned.",
                    bears_on=CaseField.EXPECTED_FUTURE_CHANGES,
                ),
                Clarification(
                    question="Are the two batch sizes one fact?",
                    answer="Two facts; they are unrelated.",
                    bears_on=CaseField.CONFIRMED_FACTS,
                ),
            ],
        )
    )

    kept = created.snapshot.clarifications[1]
    revised = runtime.case_service.update(
        created.case_id,
        CaseUpdate(clarifications=[kept.model_copy(update={"answer": "Two, and always were."})]),
    )

    assert revised.revision == 2
    assert [item.question for item in revised.snapshot.clarifications] == [kept.question]
    assert [item.answer for item in revised.snapshot.clarifications] == [
        "Two, and always were."
    ]
    # The question half is untouched by a reworded answer. It is the advisor's text, and a
    # revision that let an edit reach it would leave the case claiming a review asked something
    # it never did.
    assert revised.snapshot.clarifications[0].bears_on is kept.bears_on
    # And revision 1 still holds what it held: a review pinned to it judged against both.
    history = runtime.case_service.history(created.case_id)
    assert len(history[0].snapshot.clarifications) == 2


def test_a_clarification_needs_both_halves(runtime) -> None:
    """A pair with one side missing is not a weaker pair; it is a different thing.

    A question with no answer is the review's own text sitting in the user's case, which
    invariant 25 exists to keep out. An answer with no question is the failure the pair was
    introduced to fix: a reply whose subject nothing downstream can recover.
    """

    del runtime
    with pytest.raises(ValidationError):
        Clarification(
            question="Is a second warehouse actually planned?",
            answer="",
            bears_on=CaseField.EXPECTED_FUTURE_CHANGES,
        )
    with pytest.raises(ValidationError):
        Clarification(
            question="",
            answer="No, and none is planned.",
            bears_on=CaseField.EXPECTED_FUTURE_CHANGES,
        )


def test_skipped_questions_are_derived_from_what_was_asked() -> None:
    """Skipping is normal, and is recorded as absence rather than as a flag.

    A stored `skipped` would be a second copy of a fact the application can compute, and the
    two could then disagree about the same round. What was skipped is the review's questions
    minus the ones the revision names — the rule `ReviewAnswer.grounded` already follows.
    """

    answered = AnsweredQuestions(
        review_id="rev_1",
        answers=[
            RecordedAnswer(
                question_reference="Q-1",
                answer_belongs_in=CaseField.EXPECTED_FUTURE_CHANGES,
                recorded_text="A second warehouse arrives next quarter.",
            ),
            RecordedAnswer(
                question_reference="Q-4",
                answer_belongs_in=CaseField.ASSUMPTIONS,
                recorded_text="The two batch sizes are one fact.",
            ),
        ],
    )

    assert answered.skipped_references(["Q-1", "Q-2", "Q-3", "Q-4", "Q-5"]) == [
        "Q-2",
        "Q-3",
        "Q-5",
    ]
    # Order follows the questions as asked, not the answers, so a reader sees them in the
    # order they walked past them.
    assert answered.skipped_references(["Q-5", "Q-2"]) == ["Q-5", "Q-2"]
    assert answered.skipped_references(["Q-1", "Q-4"]) == []


def test_a_revision_answers_each_question_once() -> None:
    """Two answers to one question is a shape with no meaning, so it is not representable."""

    with pytest.raises(ValidationError, match="repeats"):
        AnsweredQuestions(
            review_id="rev_1",
            answers=[
                RecordedAnswer(
                    question_reference="Q-1",
                    answer_belongs_in=CaseField.NON_GOALS,
                    recorded_text="One answer.",
                ),
                RecordedAnswer(
                    question_reference="Q-1",
                    answer_belongs_in=CaseField.NON_GOALS,
                    recorded_text="A different answer to the same question.",
                ),
            ],
        )
