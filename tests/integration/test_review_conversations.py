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
            # Stated so this review finishes rather than stopping to ask. A first pass whose
            # verdicts hinge on an unwritten case ends in `awaiting_answers` and has nothing
            # settled enough to hold a conversation about, which is a different subject from
            # the one these tests are about.
            expected_future_changes=["A second scheduler backend is contracted for Q3"],
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


def test_the_whole_corpus_and_primer_reach_the_answering_stage(
    runtime: Runtime,
) -> None:
    """A reader can ask what a boundary *is*, not only what this review found.

    Background is assembled by the application and handed to the stage, so the model never
    chooses its own evidence. The substitute counts what it was given, which is how the
    wiring is observed without asserting on a real model's prose.

    The count is the point. Presented whole means every policy, every turn — an index that
    returned the nearest handful was built and measured first, and it missed the primer's
    own "what the detector cannot see" section when asked exactly that question.
    """

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)
    presented = len(runtime.policy_service.catalog())
    assert presented > 0

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "What is a boundary, and what can the detector not see?",
    )

    assert message.answer is not None
    assert (
        f"the method primer and {presented} policies, whole" in message.answer.answer
    ), message.answer.answer


def test_prose_arrives_before_the_answer_does_and_matches_it(runtime: Runtime) -> None:
    """The preview is a window onto the same turn, not a different one.

    Asserted against the stored record rather than against the fragments: what a reader was
    shown has to be the answer that was appended, or the two can drift and only one of them is
    the review's.
    """

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)
    seen: list[str] = []

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "What did you make of the TaskFormatter boundary?",
        on_prose=seen.append,
    )

    assert message.answer is not None
    assert len(seen) > 1
    assert "".join(seen) == message.answer.answer
    stored = runtime.review_conversation_service.show(conversation.conversation_id)
    assert stored.messages[-1].answer is not None
    assert stored.messages[-1].answer.answer == message.answer.answer


def test_a_preview_never_becomes_the_stored_record(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A turn that emits text and then fails is a failed turn, with no answer in it.

    This is the property that makes a preview safe: fragments are prose on its way to being
    checked, so text a reader has already seen cannot promote itself into the history.
    """

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)
    seen: list[str] = []

    class _FailsAfterSpeaking:
        @staticmethod
        def stream_review_answer(
            _review_: object,
            _evidence: object,
            _history: object,
            _question: object,
            _knowledge: object,
            on_prose: object,
        ) -> None:
            assert callable(on_prose)
            on_prose("A half-written answer that")
            raise ProviderError("the model stopped mid-answer")

        # Present so this double still satisfies `StreamingAnswerReasoner`, which is checked
        # by `isinstance` and therefore by which method names exist. Without it the double
        # stops being a streaming reasoner, the service quietly takes the unstreamed path,
        # and the test passes or fails for a reason that has nothing to do with previews.
        @staticmethod
        def stream_open_question_discussion(
            _review_: object,
            _evidence: object,
            _question_: object,
            _history: object,
            _asked: object,
            _knowledge: object,
            _on_prose: object,
        ) -> None:
            raise AssertionError("This conversation is not about an open question")

    monkeypatch.setattr(
        runtime.review_conversation_service, "_reasoner", _FailsAfterSpeaking()
    )

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "Does a preview ever become the record?",
        on_prose=seen.append,
    )

    assert seen == ["A half-written answer that"]
    assert message.answer is None
    assert "stopped mid-answer" in message.failure
    stored = runtime.review_conversation_service.show(conversation.conversation_id)
    assert [item.answer for item in stored.messages] == [None]


def test_a_reasoner_that_cannot_stream_still_answers(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming is a capability of the provider, so its absence is not a failed turn."""

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)
    real = runtime.review_conversation_service._reasoner
    seen: list[str] = []

    class _CannotStream:
        """Everything a reasoner needs, minus the streaming method."""

        answer_review_question = staticmethod(real.answer_review_question)

    monkeypatch.setattr(runtime.review_conversation_service, "_reasoner", _CannotStream())

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "What did you make of the TaskFormatter boundary?",
        on_prose=seen.append,
    )

    assert seen == []
    assert message.answer is not None
    assert message.answer.answer


def test_background_never_grounds_an_answer(runtime: Runtime) -> None:
    """Only a boundary can support a claim about this repository.

    Background explains the method. If it could ground an answer, "the review says so" and
    "a policy document says so" would be indistinguishable in the record — and the second
    is not a finding about any repository at all.
    """

    review = _review(runtime)
    report = review.report
    assert report is not None
    conversation = runtime.review_conversation_service.create(review.review_id)

    # A question the review cannot answer, whose words are all over the primer and the
    # corpus: whatever background comes back, none of it may become a citation.
    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "In general, when is an abstraction with one implementation premature?",
    )

    assert message.answer is not None
    known = {item.reference for item in report.reviewed}
    assert set(message.answer.supporting_references) <= known


def test_a_question_is_still_answered_when_the_corpus_cannot_be_read(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Background is an aid. Losing it must not take a working conversation off a person."""

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("the policy corpus could not be read")

    monkeypatch.setattr(
        runtime.review_conversation_service._policies,
        "catalog",
        broken,
    )

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "What did you make of the TaskFormatter boundary?",
    )

    assert message.answer is not None
    # The primer is bundled and still there, so background degrades to it rather than
    # vanishing; what must not happen is the turn failing.
    assert "the method primer and 0 policies, whole" in message.answer.answer


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
