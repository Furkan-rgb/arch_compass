"""An answer's prose, reported while it is still being written.

Streaming changes when text reaches a reader and nothing else. Every test here defends one
half of that sentence: the prose really does arrive in fragments as the reply grows, and the
answer that gets returned is the same validated object the non-streaming call returns, from
the same validation, with grounding still derived from flags that do not exist until the last
token has arrived.

The partial-JSON reader gets most of the attention, because it is the one piece with no
second chance: a structured reply is not parseable until it is complete, so reading a prefix
of it is a decision made without the JSON decoder's help — except for escapes, which are
handed back to the decoder rather than reimplemented.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

import pytest
from tests.reasoning_support import review, reviewed_boundary

from archcompass.adapters.models.structured import (
    ChatMessage,
    StreamingChatTransport,
    StructuredReasoningProvider,
    ThinkLevel,
    prose_prefix,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.errors import ModelOutputValidationError, ProviderError
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.review import BoundaryReview, ReviewEvidence
from archcompass.ports.reasoning import ReasoningTask, StreamingAnswerReasoner


class _StreamingTransport:
    """Returns scripted replies, in scripted fragments, and remembers which call was used."""

    provider_label = "Fake"

    def __init__(self, *replies: list[str]) -> None:
        self._replies = list(replies)
        self.streamed = 0
        self.completed = 0

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        is_fast: bool,
        think: ThinkLevel,
        temperature: float | None,
    ) -> str:
        del messages, schema, task, is_fast, think, temperature
        self.completed += 1
        return "".join(self._replies.pop(0))

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        is_fast: bool,
        think: ThinkLevel,
        temperature: float | None,
    ) -> Iterator[str]:
        del messages, schema, task, is_fast, think, temperature
        self.streamed += 1
        yield from self._replies.pop(0)


class _CompleteOnlyTransport:
    """A vendor that cannot stream: the capability is absent, not switched off."""

    provider_label = "Fake"

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.completed = 0

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        is_fast: bool,
        think: ThinkLevel,
        temperature: float | None,
    ) -> str:
        del messages, schema, task, is_fast, think, temperature
        self.completed += 1
        return self._reply


def _config() -> ReasoningModelConfig:
    return ReasoningModelConfig(
        provider="fake",
        model="fake-answerer",
        timeout_seconds=30,
        context_window_tokens=131072,
        max_output_tokens=8192,
    )


BOUNDARIES = [
    reviewed_boundary("BR-001", "Formatter", material=True),
    reviewed_boundary("BR-002", "Clock", material=False),
]


def _review() -> BoundaryReview:
    return review(BOUNDARIES)


def _case() -> ArchitectureCase:
    """The pinned revision, which now travels with the review into the answering stage."""

    return ArchitectureCase(title="Boundaries", problem_statement="Judge them.")


def _background() -> MethodKnowledge:
    """Background is required and irrelevant here: these tests are about arrival, not content."""

    return MethodKnowledge(method="What ArchCompass means by a boundary.", policies=[])


def _answer_reply(answer: str, flags: list[bool]) -> str:
    return json.dumps({"answer": answer, "supported_by": flags})


def _fragments(answer: str, flags: list[bool], *, pieces: int = 8) -> list[str]:
    """One reply cut into arbitrary pieces, the way a transport delivers it.

    Cut by character count rather than on token or field boundaries: a real chunk lands
    mid-word and mid-escape, and a reader that only works on tidy boundaries would pass here
    and fail against a live model.
    """

    reply = _answer_reply(answer, flags)
    size = max(1, len(reply) // pieces)
    return [reply[index : index + size] for index in range(0, len(reply), size)]


ANSWER = "The Formatter boundary stands in front of a format the contract fixes."


def test_nothing_is_read_before_the_field_has_opened() -> None:
    for partial in ('{"ans', '{"answer"', '{"answer":', '{"answer": '):
        assert prose_prefix("answer", partial) == ""


def test_a_prefix_grows_as_the_field_arrives() -> None:
    reply = _answer_reply(ANSWER, [True, False])
    lengths = [len(prose_prefix("answer", reply[:cut])) for cut in range(len(reply) + 1)]

    # Monotone, which is what lets a caller treat the difference as the new fragment.
    assert lengths == sorted(lengths)
    assert prose_prefix("answer", reply) == ANSWER


def test_escapes_are_decoded_by_the_json_decoder_rather_than_by_hand() -> None:
    answer = 'The "TaskFormatter" port,\nas judged, costs €0 — see \\ below.'
    reply = _answer_reply(answer, [True, False])

    assert prose_prefix("answer", reply) == answer
    # And every prefix of it is a prefix of the answer: an escape cut in half is dropped and
    # returns with the chunk that completes it, never as a stray backslash on the page.
    for cut in range(len(reply) + 1):
        assert answer.startswith(prose_prefix("answer", reply[:cut]))


def test_a_field_that_is_not_a_string_is_not_guessed_at() -> None:
    """The name may appear in another field's text, or belong to a non-string value."""

    assert prose_prefix("answer", '{"supported_by": [true], "answer": null') == ""
    assert prose_prefix("answer", '{"note": "the answer is elsewhere"') == ""


def test_the_prose_arrives_in_fragments_and_the_answer_is_still_validated() -> None:
    transport = _StreamingTransport(_fragments(ANSWER, [True, False]))
    provider = StructuredReasoningProvider(_config(), transport)
    seen: list[str] = []

    answer = provider.stream_review_answer(
        _review(),
        ReviewEvidence(case=_case()),
        [],
        "What about the Formatter?",
        _background(),
        seen.append,
    )

    assert transport.streamed == 1
    assert transport.completed == 0
    # More than one fragment, and they join into exactly the answer that was returned.
    assert len(seen) > 1
    assert "".join(seen) == ANSWER
    assert answer.answer == ANSWER
    # Grounding is unchanged: it comes from flags that only exist once the reply is whole.
    assert answer.supporting_references == ["BR-001"]


def test_a_transport_that_cannot_stream_answers_anyway() -> None:
    """The capability is asked of the transport, not configured, and its absence is not an error."""

    transport = _CompleteOnlyTransport(_answer_reply(ANSWER, [False, True]))
    provider = StructuredReasoningProvider(_config(), transport)
    seen: list[str] = []

    answer = provider.stream_review_answer(
        _review(),
        ReviewEvidence(case=_case()),
        [],
        "What about the Clock?",
        _background(),
        seen.append,
    )

    assert not isinstance(transport, StreamingChatTransport)
    assert transport.completed == 1
    assert seen == []
    assert answer.answer == ANSWER
    assert answer.supporting_references == ["BR-002"]


def test_the_repair_round_is_not_streamed() -> None:
    """A reader part-way through one answer must not watch it be rewritten underneath them.

    The first reply is short a flag, which is the failure arity checks exist for. The repair
    round is a whole second answer to the same question, and there is no honest way to narrate
    a replacement as a stream of fragments — so it lands whole and nothing more is emitted.
    """

    transport = _StreamingTransport(
        _fragments("A first attempt, one flag short.", [True]),
        _fragments(ANSWER, [True, False]),
    )
    provider = StructuredReasoningProvider(_config(), transport)
    seen: list[str] = []

    answer = provider.stream_review_answer(
        _review(),
        ReviewEvidence(case=_case()),
        [],
        "What about the Formatter?",
        _background(),
        seen.append,
    )

    assert transport.streamed == 1
    assert transport.completed == 1
    assert "".join(seen) == "A first attempt, one flag short."
    # What was shown is not what was returned, which is why the caller must treat fragments as
    # provisional and the returned answer as the text.
    assert answer.answer == ANSWER


def test_a_streamed_answer_is_refused_on_the_same_terms_as_any_other() -> None:
    short = _fragments("Still one flag short.", [True])
    transport = _StreamingTransport(short, short)
    provider = StructuredReasoningProvider(_config(), transport)

    with pytest.raises(ModelOutputValidationError, match="supported_by"):
        provider.stream_review_answer(
            _review(), ReviewEvidence(case=_case()), [], "Formatter?", _background(), lambda _: None
        )


def test_an_answer_answered_with_json_is_refused_rather_than_shown_as_prose() -> None:
    """The same defect the conclusion had, on the field a reader watches arrive."""

    document = json.dumps({"statement": "Leaked identifiers.", "supported_by": [True, False]})
    bad = _fragments(document, [True, False])
    transport = _StreamingTransport(bad, bad)
    provider = StructuredReasoningProvider(_config(), transport)

    with pytest.raises(ModelOutputValidationError, match="must be prose"):
        provider.stream_review_answer(
            _review(), ReviewEvidence(case=_case()), [], "Formatter?", _background(), lambda _: None
        )


def test_a_mid_stream_failure_is_not_retried_into_repeated_text() -> None:
    """Once a fragment has been shown, replaying the request would replay the text.

    A streamed request is not retried at all — a second attempt would repeat text already
    shown, and the transport leaves its retry on `complete`, where nothing has been seen yet.
    This asserts the stage adds no attempt of its own either: a failure after the first
    fragment surfaces as the provider error it is.
    """

    class _FailsMidStream(_StreamingTransport):
        attempts = 0

        def stream(self, *_: object, **__: object) -> Iterator[str]:
            _FailsMidStream.attempts += 1
            yield '{"answer": "Half an ans'
            raise ProviderError("the connection dropped")

    provider = StructuredReasoningProvider(_config(), _FailsMidStream())
    seen: list[str] = []

    with pytest.raises(ProviderError, match="connection dropped"):
        provider.stream_review_answer(
            _review(),
        ReviewEvidence(case=_case()),
        [],
        "Formatter?",
        _background(),
        seen.append,
        )

    assert _FailsMidStream.attempts == 1
    assert "".join(seen) == "Half an ans"


def test_the_real_provider_satisfies_the_streaming_port() -> None:
    """The capability check the application makes has to actually pass here."""

    provider = StructuredReasoningProvider(
        _config(), _CompleteOnlyTransport(_answer_reply(ANSWER, [True, False]))
    )

    assert isinstance(provider, StreamingAnswerReasoner)
