"""Follow-up questions about a review, and the pins that keep them honest."""

from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.bootstrap import Runtime
from archcompass.domain.case import ArchitectureCase, RepositoryReference
from archcompass.domain.errors import (
    ConversationNotFoundError,
    ConversationValidationError,
    ProviderError,
)
from archcompass.domain.review import BoundaryReview
from archcompass.domain.review_conversation import MAX_QUESTION_CHARACTERS

FIXTURE = Path("eval/cases/boundary-review/repository").resolve()


def _review(runtime: Runtime) -> BoundaryReview:
    atlas = runtime.analyzer.analyze(FIXTURE)
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_repository.create(
        ArchitectureCase(
            title="Boundary review",
            problem_statement="Decide which boundaries earn their place.",
            desired_outcome="An honest verdict per boundary.",
            repository=RepositoryReference(root_path=str(FIXTURE)),
        ),
        actor="test",
    )
    return runtime.review_service.review(revision.case_id, repository_root=FIXTURE)


def test_a_question_is_answered_and_grounded_in_reviewed_boundaries(
    runtime: Runtime,
) -> None:
    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "What did you make of the TaskFormatter boundary?",
    )

    assert message.answer is not None
    report = review.report
    assert report is not None
    known = {item.reference for item in report.reviewed}
    # Every citation resolves. References come from position, so an unknown one would mean
    # the application invented it rather than the model.
    assert set(message.answer.supporting_references) <= known
    assert message.answer.grounded


def test_the_conversation_pins_the_review_and_its_case_revision(runtime: Runtime) -> None:
    review = _review(runtime)

    conversation = runtime.review_conversation_service.create(review.review_id)

    assert conversation.review_id == review.review_id
    assert conversation.case_id == review.case_id
    assert conversation.case_revision == review.case_revision


def test_history_accumulates_in_order(runtime: Runtime) -> None:
    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)

    runtime.review_conversation_service.ask(conversation.conversation_id, "First question?")
    runtime.review_conversation_service.ask(conversation.conversation_id, "Second question?")

    stored = runtime.review_conversation_service.show(conversation.conversation_id)
    assert [item.ordinal for item in stored.messages] == [1, 2]
    assert [item.question for item in stored.messages] == [
        "First question?",
        "Second question?",
    ]


def test_a_failed_turn_is_recorded_rather_than_dropped(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A question that produced nothing is still part of the history.

    Dropping it makes the conversation read as though it was never asked, which is the
    one thing a reader cannot recover from the record.
    """

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)

    def refuse(*_: object, **__: object) -> None:
        raise ProviderError("the model was unreachable")

    monkeypatch.setattr(
        runtime.review_conversation_service,
        "_reasoner",
        type("Refusing", (), {"answer_review_question": staticmethod(refuse)})(),
    )

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "Does this survive a provider failure?",
    )

    assert message.answer is None
    assert "unreachable" in message.failure
    stored = runtime.review_conversation_service.show(conversation.conversation_id)
    assert len(stored.messages) == 1


def test_a_blank_or_oversized_question_is_refused(runtime: Runtime) -> None:
    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)

    with pytest.raises(ConversationValidationError, match="must not be blank"):
        runtime.review_conversation_service.ask(conversation.conversation_id, "   ")

    with pytest.raises(ConversationValidationError, match="at most"):
        runtime.review_conversation_service.ask(
            conversation.conversation_id,
            "x" * (MAX_QUESTION_CHARACTERS + 1),
        )


def test_an_unknown_review_cannot_be_discussed(runtime: Runtime) -> None:
    with pytest.raises(Exception, match="not found"):
        runtime.review_conversation_service.create("rev_missing")


def test_a_conversation_refuses_to_lose_a_concurrent_message(runtime: Runtime) -> None:
    """Two turns answered at once must not silently discard one another."""

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)
    runtime.review_conversation_service.ask(conversation.conversation_id, "First?")

    stale = conversation.model_copy(
        update={
            "messages": [
                *conversation.messages,
                runtime.review_conversation_service.show(
                    conversation.conversation_id
                ).messages[0],
            ]
        }
    )

    with pytest.raises(ConversationNotFoundError, match="changed while"):
        runtime.review_conversation_service._conversations.append(stale)
