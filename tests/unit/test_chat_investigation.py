"""The two conversation stages looking at the repository before they reply.

Same toolbox as elicitation and the same loop, under a different contract and one changed
rule: the first turn is not forced. Elicitation runs once per review and proved it would skip
looking when it was allowed to; a conversation turn runs once per message and is usually
about text already in front of the stage, so a forced call there buys a search for something
the input already says.

The tests here are about the seam rather than about the looking, which `test_elicitation`
already covers in full: that both stages reach the loop at all, that what it finds arrives in
the payload under the one key `elicit_questions` uses, that a stage with no toolbox sends the
request it always sent, and that a streamed reply still begins with the first word of the
answer — the investigation is over before a single fragment leaves.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from typing import cast

from tests.reasoning_support import review, reviewed_boundary

from archcompass.adapters.models.structured import (
    ChatMessage,
    InvestigationMessage,
    StructuredReasoningProvider,
    ThinkLevel,
    ToolCall,
    ToolExchange,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.case import ArchitectureCase, CaseField
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.review import (
    BoundaryReview,
    OpenQuestion,
    ReviewEvidence,
)
from archcompass.ports.investigation import RecordedLookup, ToolSpec
from archcompass.ports.reasoning import ReasoningTask

BOUNDARIES = [
    reviewed_boundary("BR-001", "Formatter", material=True),
    reviewed_boundary("BR-002", "Clock", material=False),
]

ANSWER = json.dumps(
    {"answer": "Both copies are read by the planning module.", "supported_by": [True, False]}
)
DISCUSSION = json.dumps(
    {
        "answer": "Both copies are read by the planning module.",
        "supported_by": [True],
        "suggested_answer": "",
    }
)


class _Investigator:
    """A toolbox with one canned answer, recording as the real one does."""

    def __init__(self, answer: str = "planning/sink.py:12: RETRY_LIMIT = 5") -> None:
        self._answer = answer
        self.transcript: list[RecordedLookup] = []
        self.closing = ""
        self.abandoned = ""

    @property
    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="search_source",
                description="Find text.",
                parameters={"type": "object", "properties": {}},
            )
        ]

    def call(self, name: str, arguments: Mapping[str, object]) -> str:
        self.transcript.append(
            RecordedLookup(tool=name, arguments=dict(arguments), result=self._answer)
        )
        return self._answer

    def conclude(self, closing: str, abandoned: str) -> None:
        self.closing = closing
        self.abandoned = abandoned


class _ChatTransport:
    """A transport that can complete, stream and carry tools, recording each of the three.

    All three capabilities on one double deliberately. Whether a reply is previewed and
    whether the stage may look are independent of each other, and a test that had to pick a
    transport per combination could not assert the one property that matters here: that the
    looking finishes before the first fragment is emitted.
    """

    provider_label = "Fake"

    def __init__(self, reply: str, *exchanges: ToolExchange) -> None:
        self._reply = reply
        self._exchanges = list(exchanges)
        self.messages: list[ChatMessage] = []
        self.required: list[bool] = []
        self.tasks: list[ReasoningTask] = []
        #: What had been emitted at the moment each lookup was asked for, so "the
        #: investigation runs first" is checked against the reader's own timeline rather
        #: than against the order of two calls in this file.
        self.emitted_when_looking: list[list[str]] = []
        self.emitted: list[str] = []

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> str:
        del schema, think, temperature
        self.messages = messages
        self.tasks.append(task)
        return self._reply

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> Iterator[str]:
        del schema, think, temperature
        self.messages = messages
        self.tasks.append(task)
        for index in range(0, len(self._reply), 20):
            yield self._reply[index : index + 20]

    def complete_with_tools(
        self,
        messages: list[InvestigationMessage],
        *,
        tools: Sequence[ToolSpec],
        require_call: bool,
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> ToolExchange:
        del messages, tools, think, temperature
        self.required.append(require_call)
        self.tasks.append(task)
        self.emitted_when_looking.append(list(self.emitted))
        return self._exchanges.pop(0)


class _CompleteOnlyTransport:
    """A vendor with no function-calling API, which is most of them."""

    provider_label = "Fake"

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.messages: list[ChatMessage] = []

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> str:
        del schema, task, think, temperature
        self.messages = messages
        return self._reply


def _provider(transport: object) -> StructuredReasoningProvider:
    config = ReasoningModelConfig(
        provider="fake",
        model="fake-answerer",
        timeout_seconds=30,
        context_window_tokens=131072,
        max_output_tokens=8192,
    )
    return StructuredReasoningProvider(config, transport)  # pyright: ignore[reportArgumentType]


def _looked_then_spoke() -> tuple[ToolExchange, ToolExchange]:
    return (
        ToolExchange(
            text="Let me see who reads it.",
            calls=(ToolCall(name="search_source", arguments={"query": "RETRY_LIMIT"}),),
        ),
        ToolExchange(text="One module reads both copies.", calls=()),
    )


def _review() -> BoundaryReview:
    return review(BOUNDARIES)


def _case() -> ArchitectureCase:
    return ArchitectureCase(title="Boundaries", problem_statement="Judge them.")


def _background() -> MethodKnowledge:
    return MethodKnowledge(method="What ArchCompass means by a boundary.", policies=[])


def _question() -> OpenQuestion:
    return OpenQuestion(
        reference="Q-1",
        what_the_review_saw="Two modules state the same retry limit.",
        unknown="Whether the two copies are one fact.",
        why_it_matters="If they are one fact, the duplication is a defect.",
        question="Are these the same constant?",
        answer_belongs_in=CaseField.TECHNICAL_CONSTRAINTS,
        supporting_references=["BR-001"],
    )


def _payload(transport: _ChatTransport | _CompleteOnlyTransport) -> dict[str, object]:
    user = next(item for item in transport.messages if item["role"] == "user")
    return cast(dict[str, object], json.loads(user["content"].split("Input:\n", 1)[1]))


def test_the_answering_stage_looks_before_it_answers() -> None:
    """The findings reach the answer under the one key elicitation already uses.

    One key rather than a shape of its own, because nothing downstream reads it: it is text
    the stage is shown, and a second representation of it would be a second thing to keep in
    step with the rendering the loop produces.
    """

    transport = _ChatTransport(ANSWER, *_looked_then_spoke())
    investigator = _Investigator()

    answer = _provider(transport).answer_review_question(
        _review(),
        ReviewEvidence(case=_case()),
        [],
        "Who else reads the retry limit?",
        _background(),
        investigator,
    )

    assert [item.tool for item in investigator.transcript] == ["search_source"]
    findings = cast(str, _payload(transport)["investigation"])
    assert "RETRY_LIMIT" in findings
    assert "One module reads both copies." in findings
    # The looking ran under its own contract, so a stored transcript says which of the two
    # kinds of investigation produced it.
    assert transport.tasks[0] is ReasoningTask.INVESTIGATE_FOR_ANSWER
    assert transport.tasks[-1] is ReasoningTask.ANSWER_REVIEW_QUESTION
    # And nothing about the answer itself changed shape.
    assert answer.supporting_references == ["BR-001"]


def test_the_discussion_stage_looks_before_it_discusses() -> None:
    """The stage a reader most often asks a question of the code gets the same loop."""

    transport = _ChatTransport(DISCUSSION, *_looked_then_spoke())
    investigator = _Investigator()

    _provider(transport).discuss_open_question(
        _review(),
        ReviewEvidence(case=_case()),
        _question(),
        [],
        "How would I know whether these are the same constant?",
        _background(),
        investigator,
    )

    assert [item.tool for item in investigator.transcript] == ["search_source"]
    assert "RETRY_LIMIT" in cast(str, _payload(transport)["investigation"])
    assert transport.tasks[0] is ReasoningTask.INVESTIGATE_FOR_ANSWER
    assert transport.tasks[-1] is ReasoningTask.DISCUSS_OPEN_QUESTION


def test_a_turn_with_no_toolbox_sends_the_request_it_always_sent() -> None:
    """`None` is the default and the ordinary case, and it must cost nothing.

    Asserted as the absence of the key rather than as an empty one: a stage shown
    `"investigation": ""` has been told an investigation happened and found nothing, which
    is the one thing the record must never imply.
    """

    transport = _CompleteOnlyTransport(ANSWER)

    _provider(transport).answer_review_question(
        _review(),
        ReviewEvidence(case=_case()),
        [],
        "What did you make of the Formatter?",
        _background(),
    )

    assert "investigation" not in _payload(transport)


def test_a_transport_that_cannot_carry_tools_answers_from_the_pinned_evidence() -> None:
    """The capability is the transport's, so its absence is not a failed turn.

    Most providers are this one. A toolbox handed to a stage with no way to offer it is
    simply never touched, which is also what makes the recorded investigation `None`.
    """

    transport = _CompleteOnlyTransport(ANSWER)
    investigator = _Investigator()

    _provider(transport).answer_review_question(
        _review(),
        ReviewEvidence(case=_case()),
        [],
        "What did you make of the Formatter?",
        _background(),
        investigator,
    )

    assert investigator.transcript == []
    assert "investigation" not in _payload(transport)


def test_a_conversation_turn_is_never_forced_to_look() -> None:
    """The one rule that differs from elicitation, and the reason both contracts exist.

    Most messages here are about the review's own reasoning, the case or the method, all of
    which are already in the input. A forced first call would spend a lookup on "why was
    this boundary condemned?" and put its result in front of the reply.
    """

    transport = _ChatTransport(ANSWER, ToolExchange(text="", calls=()))
    investigator = _Investigator()

    _provider(transport).answer_review_question(
        _review(),
        ReviewEvidence(case=_case()),
        [],
        "Why was the Formatter condemned?",
        _background(),
        investigator,
    )

    assert transport.required == [False]
    # Returning immediately is a real outcome and the common one: nothing was looked up and
    # nothing was said about it, so the stage answers from what it was already given and the
    # payload gains no key. Where such a turn does say something, that sentence is the whole
    # of what the key holds — the same rendering elicitation gets.
    assert investigator.transcript == []
    assert "investigation" not in _payload(transport)


def test_a_streamed_reply_still_begins_with_the_first_word_of_the_answer() -> None:
    """No fragment of an investigation is ever previewed, because it is over first.

    This is what makes the parameter safe on the streaming path. A reader watching a reply
    being written must see the reply — a preview that carried a search result would be
    showing them working they never asked for, and one that interleaved the two would be
    showing them prose that is not the answer.
    """

    transport = _ChatTransport(ANSWER, *_looked_then_spoke())
    investigator = _Investigator()
    seen: list[str] = []

    def emit(fragment: str) -> None:
        seen.append(fragment)
        transport.emitted.append(fragment)

    answer = _provider(transport).stream_review_answer(
        _review(),
        ReviewEvidence(case=_case()),
        [],
        "Who else reads the retry limit?",
        _background(),
        investigator,
        emit,
    )

    assert [item.tool for item in investigator.transcript] == ["search_source"]
    # Nothing had reached the reader by the time either investigation turn was requested.
    assert transport.emitted_when_looking == [[], []]
    assert len(seen) > 1
    assert "".join(seen) == answer.answer


def test_a_streamed_discussion_investigates_before_it_previews_anything() -> None:
    """The other streamed stage, held to the same order for the same reason."""

    transport = _ChatTransport(DISCUSSION, *_looked_then_spoke())
    investigator = _Investigator()
    seen: list[str] = []

    def emit(fragment: str) -> None:
        seen.append(fragment)
        transport.emitted.append(fragment)

    answer = _provider(transport).stream_open_question_discussion(
        _review(),
        ReviewEvidence(case=_case()),
        _question(),
        [],
        "How would I know whether these are the same constant?",
        _background(),
        investigator,
        emit,
    )

    assert transport.emitted_when_looking == [[], []]
    assert "".join(seen) == answer.answer
    assert "RETRY_LIMIT" in cast(str, _payload(transport)["investigation"])
