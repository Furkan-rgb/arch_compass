"""Follow-up questions about a review, and the pins that keep them honest."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archcompass.bootstrap import Runtime
from archcompass.domain.case import ArchitectureCase, RepositoryReference
from archcompass.domain.errors import (
    ConversationNotFoundError,
    ConversationValidationError,
    PolicyFormatError,
    ProviderError,
)
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.review import BoundaryReview, ReviewEvidence
from archcompass.domain.review_conversation import (
    MAX_QUESTION_CHARACTERS,
    ReviewAnswer,
    ReviewMessage,
)
from archcompass.ports.investigation import SourceInvestigator

FIXTURE = Path("eval/cases/boundary-review/repository").resolve()


def _review(runtime: Runtime, root: Path = FIXTURE) -> BoundaryReview:
    atlas = runtime.analyzer.analyze(root)
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
            repository=RepositoryReference(root_path=str(root)),
        ),
        actor="test",
    )
    return runtime.review_service.review(revision.case_id, repository_root=root)


def _copied(tmp_path: Path) -> Path:
    """The fixture somewhere writable, for the tests that have to make it go stale."""

    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository)
    return repository


def _looking(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> list[SourceInvestigator | None]:
    """Make the workspace's reasoner one that actually uses the toolbox it is handed.

    The substitute ignores the investigator — it has no model to offer tools to — so a turn
    against it records nothing, which is correct and asserts nothing about the wiring. This
    stands in for the half a live provider does: one lookup and a closing, through the real
    `RepositoryInvestigator` the service builds. What is under test is everything after
    that: whether the toolbox was built at all, and whether what it was asked reaches the
    message that gets stored.

    What comes back is the list of investigators the stage was handed, one per turn, so a
    test can assert `None` was passed as readily as it can assert a record came out.
    """

    reasoner = runtime.review_conversation_service._reasoner  # pyright: ignore[reportPrivateUsage]
    original = reasoner.answer_review_question
    handed: list[SourceInvestigator | None] = []

    def answer(
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None = None,
    ) -> ReviewAnswer:
        handed.append(investigator)
        if investigator is not None:
            investigator.call("search_source", {"query": "TaskFormatter"})
            investigator.conclude("One module reads it.", "")
        return original(review, evidence, history, question, knowledge)

    monkeypatch.setattr(reasoner, "answer_review_question", answer)
    return handed


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
        # The identity is part of what a reasoner is: the service asks for it when it
        # stores what a turn looked up, and a double without one would fail this test for a
        # reason that has nothing to do with the failed turn it is about.
        type(
            "Refusing",
            (),
            {
                "answer_review_question": staticmethod(refuse),
                "prompt_identity": staticmethod(lambda task: f"{task.value}:v1"),
            },
        )(),
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


def test_the_pinned_atlas_map_reaches_the_answering_stage(runtime: Runtime) -> None:
    """The structural answer to "what else is in this repository?" — counted by the
    substitute, like background, to observe the wiring without model prose."""

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "What other modules import the one you flagged?",
    )

    assert message.answer is not None
    assert "Atlas map: " in message.answer.answer, message.answer.answer
    assert "Atlas map: 0 modules" not in message.answer.answer


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
        def prompt_identity(task: object) -> str:
            return f"{task}:v1"

        @staticmethod
        def stream_review_answer(
            _review_: object,
            _evidence: object,
            _history: object,
            _question: object,
            _knowledge: object,
            _investigator: object,
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
            _investigator: object,
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
        prompt_identity = staticmethod(real.prompt_identity)

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
    """Background is an aid. Losing it must not take a working conversation off a person.

    And the stage is told the corpus was unavailable rather than handed an empty one: "this
    workspace has no policies" and "the policies could not be read" call for different
    answers to a reader asking about policy.
    """

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)

    def broken(*_: object, **__: object) -> None:
        raise PolicyFormatError("a workspace policy collides with a bundled one")

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
    assert "policy corpus unavailable" in message.answer.answer
    assert "a workspace policy collides with a bundled one" in message.answer.answer


def test_an_unexpected_corpus_failure_is_not_swallowed(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Degrading is for the failures a corpus actually has. A bug swallowed into "0
    policies" would spend its whole life disguised as a workspace without policies."""

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("a bug, not a corpus problem")

    monkeypatch.setattr(
        runtime.review_conversation_service._policies,
        "catalog",
        broken,
    )

    with pytest.raises(RuntimeError, match="a bug, not a corpus problem"):
        runtime.review_conversation_service.ask(
            conversation.conversation_id,
            "What did you make of the TaskFormatter boundary?",
        )


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


def test_a_turn_that_looked_before_replying_keeps_what_it_looked_at(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record is per message, because the looking is per message.

    A reader is shown the answer and, beside it, what was asked of their repository to
    reach it — the same disclosure the questions carry, at the grain a conversation
    happens in. Without the contract identity the transcript cannot be compared with a
    later one, and a prompt bump is exactly when an old record stops being comparable.
    """

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)
    _looking(runtime, monkeypatch)

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id,
        "Who else reads the TaskFormatter?",
    )

    investigation = message.investigation
    assert investigation is not None
    assert [item.tool for item in investigation.lookups] == ["search_source"]
    assert investigation.lookups[0].arguments == {"query": "TaskFormatter"}
    assert investigation.closing == "One module reads it."
    assert investigation.abandoned == ""
    # Its own contract, not elicitation's: the two stages hold the same tools under
    # different restraint, and a transcript filed under the wrong identity would compare
    # cleanly against the wrong thing.
    assert investigation.prompt_identity.startswith("investigate-for-answer:")


def test_the_stored_message_carries_the_investigation_the_turn_ran(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the store, because a record that only exists in memory is not a record."""

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)
    _looking(runtime, monkeypatch)
    message = runtime.review_conversation_service.ask(
        conversation.conversation_id, "Who else reads the TaskFormatter?"
    )

    stored = runtime.review_conversation_service.show(conversation.conversation_id)

    assert stored.messages[0].investigation == message.investigation


def test_a_turn_that_failed_after_looking_keeps_the_lookups(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn that read the repository and then lost its model still read the repository.

    The failure and the transcript are both facts about the same turn, and the transcript
    is the only trace that anything was done at all — dropping it would show the reader an
    empty failure where something happened.
    """

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)
    reasoner = runtime.review_conversation_service._reasoner

    def look_then_fail(
        _review: object,
        _evidence: object,
        _history: object,
        _question: object,
        _knowledge: object,
        investigator: SourceInvestigator | None = None,
    ) -> ReviewAnswer:
        assert investigator is not None
        investigator.call("search_source", {"query": "TaskFormatter"})
        raise ProviderError("the model was unreachable")

    monkeypatch.setattr(reasoner, "answer_review_question", look_then_fail)

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id, "Who else reads the TaskFormatter?"
    )

    assert message.answer is None
    assert "unreachable" in message.failure
    assert message.investigation is not None
    assert [item.tool for item in message.investigation.lookups] == ["search_source"]


def test_a_repository_that_has_moved_on_is_never_read(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The same freshness gate live excerpts take, and for the same reason.

    Code on disk that is no longer the code these verdicts were reached against is not
    evidence about this review. The stage answers from the pinned evidence alone, which is
    what every provider without tools does anyway — so there is one behaviour here, not a
    degraded one.
    """

    repository = _copied(tmp_path)
    review = _review(runtime, repository)
    conversation = runtime.review_conversation_service.create(review.review_id)
    handed = _looking(runtime, monkeypatch)
    (repository / "edited_after_the_review.py").write_text(
        "MARKER = 1\n", encoding="utf-8"
    )

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id, "Who else reads the TaskFormatter?"
    )

    assert handed == [None], "a stale repository must not be handed to a stage"
    # And `None` is what gets stored: nothing was checked, which is a different fact from
    # a repository that was checked and had nothing to say.
    assert message.investigation is None


def test_a_provider_that_cannot_look_records_no_investigation(runtime: Runtime) -> None:
    """`None` is not "found nothing". It is "nothing here can look".

    The workspace's substitute has no tool-calling transport under it, which is the
    ordinary case for every provider without the capability. A record of no lookups and no
    note would tell a reader the repository was checked and was silent.
    """

    review = _review(runtime)
    conversation = runtime.review_conversation_service.create(review.review_id)

    message = runtime.review_conversation_service.ask(
        conversation.conversation_id, "What did you make of the TaskFormatter boundary?"
    )

    assert message.answer is not None
    assert message.investigation is None
    stored = runtime.review_conversation_service.show(conversation.conversation_id)
    assert stored.messages[0].investigation is None
