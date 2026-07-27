"""What the answering stage is shown, and what it must never be shown.

A follow-up question is answered from the review alone, so what reaches this stage decides
which questions are answerable at all. The tests here are about that boundary in both
directions: everything a reader has on their page has to be in the request, and nothing
ArchCompass owns as an identifier may be.

The asymmetry is deliberate and is the whole of master plan 12.0. The conclusion's statements
each know which boundaries they rest on, and those `BR-nnn` references are exactly what stays
out — the model answers by position and the application attaches identity afterwards.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

import pytest
from tests.reasoning_support import review, reviewed_boundary

from archcompass.adapters.models.structured import (
    ChatMessage,
    StructuredReasoningProvider,
    ThinkLevel,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.atlas import FindingMeasurement, FindingPattern
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.review import OverviewStatement, ReviewOverview
from archcompass.ports.reasoning import ReasoningTask


class _RecordingTransport:
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
        is_fast: bool,
        think: ThinkLevel,
        temperature: float | None,
    ) -> str:
        del schema, task, is_fast, think, temperature
        self.messages = messages
        return self._reply


BOUNDARIES = [
    reviewed_boundary("BR-001", "Formatter", material=True),
    reviewed_boundary(
        "BR-002",
        "Voices",
        material=True,
        pattern=FindingPattern.DUPLICATED_KNOWLEDGE,
        measurements=[
            FindingMeasurement(name="modules_stating_it", value=4, unit="modules"),
            FindingMeasurement(name="distinct_values", value=2),
        ],
    ),
    reviewed_boundary("BR-003", "Clock", material=False),
]

OVERVIEW = ReviewOverview(
    situation="A second vendor is coming and three boundaries stand in its way.",
    themes=[
        OverviewStatement(
            text="Two boundaries absorb variation this case rules out.",
            supporting_references=["BR-001", "BR-002"],
        )
    ],
    recommended_sequence=[
        OverviewStatement(
            text="Give the voice list one owner before touching anything else.",
            supporting_references=["BR-002"],
        )
    ],
    limits="A static count cannot see runtime registration.",
)


def _request() -> tuple[str, _RecordingTransport]:
    transport = _RecordingTransport(
        json.dumps({"answer": "As the review has it.", "supported_by": [True, False, False]})
    )
    provider = StructuredReasoningProvider(
        ReasoningModelConfig(
            provider="fake",
            model="fake-answerer",
            timeout_seconds=30,
            context_window_tokens=131072,
            max_output_tokens=8192,
        ),
        transport,
    )

    provider.answer_review_question(
        review(BOUNDARIES, overview=OVERVIEW),
        [],
        "What should I do first, and how many copies of the voice list are there?",
        MethodKnowledge(method="What ArchCompass means by a boundary.", policies=[]),
    )

    return "\n".join(message["content"] for message in transport.messages), transport


def test_every_boundary_reaches_the_stage_with_its_reasoning_and_verdict() -> None:
    """Cleared ones included: "that was checked and is fine" is a complete answer."""

    sent, _ = _request()

    for boundary in BOUNDARIES:
        assert boundary.candidate.summary in sent
        assert boundary.rationale in sent
    assert "earning its place" in sent
    assert "NOT earning its place" in sent


def test_the_conclusion_the_reader_sees_is_in_the_request() -> None:
    """The most prominent thing on the page used to be the one thing this stage lacked.

    Only the counts sentence went, so "why does it say to start with the voice list?" was
    answered by a stage that had never seen the recommendation being asked about.
    """

    sent, _ = _request()

    assert OVERVIEW.situation in sent
    assert OVERVIEW.themes[0].text in sent
    assert OVERVIEW.recommended_sequence[0].text in sent
    assert OVERVIEW.limits in sent


def test_the_detectors_own_numbers_are_in_the_request() -> None:
    """A question about how many copies there are has a factual answer, or none at all."""

    sent, _ = _request()

    assert "modules_stating_it" in sent
    assert "distinct_values" in sent
    assert "duplicated_knowledge" in sent


def test_each_conclusion_entry_says_which_boundaries_it_was_built_from() -> None:
    """By position, so "tell me more about recommendation 3" has somewhere to go.

    Without it the conclusion is the only place a recommendation exists, and the boundaries
    carry no link back — so a question about one can only be answered by matching its words
    against the boundary list. A live conversation showed what that costs: three turns
    answered out of the conclusion's own summary while citing a boundary whose record was
    never opened.
    """

    sent, _ = _request()
    payload = json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])
    conclusion = payload["conclusion"]

    # BR-001 and BR-002 are the first two boundaries supplied; the theme rests on both.
    assert conclusion["themes"] == [
        {
            "text": OVERVIEW.themes[0].text,
            "rests_on_boundary_positions": [1, 2],
        }
    ]
    # Numbered as the page numbers them, and pointing at BR-002 alone.
    assert conclusion["recommended_sequence"] == [
        {
            "number": 1,
            "text": OVERVIEW.recommended_sequence[0].text,
            "rests_on_boundary_positions": [2],
        }
    ]
    # Positions index the boundaries actually supplied, so they resolve to a record.
    positions = {item["position"] for item in payload["boundaries"]}
    assert {1, 2} <= positions


def test_no_boundary_reference_crosses_into_the_request() -> None:
    """Including the conclusion's, which is where they would most easily have slipped in.

    Every statement in the overview carries the references it rests on, and only the text is
    sent. A code in the input is a code the model can quote back, and position is already a
    complete and unforgeable binding (12.0).
    """

    sent, _ = _request()
    # The payload only. The instructions above it say "never write a BR- code", which is the
    # rule rather than a reference, and asserting over both would test the wrong text.
    payload = sent.rsplit("\n\nInput:\n", maxsplit=1)[1]

    for boundary in BOUNDARIES:
        assert boundary.reference not in payload
    assert "BR-" not in payload


def test_the_answer_still_binds_by_position() -> None:
    """The flags are the only thing tying an answer to a boundary, so arity is the contract."""

    transport = _RecordingTransport(
        json.dumps({"answer": "Only the first.", "supported_by": [True, False]})
    )
    provider = StructuredReasoningProvider(
        ReasoningModelConfig(
            provider="fake",
            model="fake-answerer",
            timeout_seconds=30,
            context_window_tokens=131072,
            max_output_tokens=8192,
        ),
        transport,
    )

    # Two flags for three boundaries: refused rather than shifted onto the wrong ones.
    with pytest.raises(ModelOutputValidationError, match="supported_by"):
        provider.answer_review_question(
            review(BOUNDARIES, overview=OVERVIEW),
            [],
            "Which one first?",
            MethodKnowledge(method="Primer.", policies=[]),
        )


def test_the_schema_fixes_one_flag_per_boundary() -> None:
    """Stated in the grammar, so the common case never reaches the validator."""

    schema = cast(
        dict[str, object],
        StructuredReasoningProvider._review_answer_schema(boundary_count=len(BOUNDARIES)),
    )
    properties = cast(dict[str, object], schema["properties"])
    supported = cast(dict[str, object], properties["supported_by"])

    assert supported["minItems"] == len(BOUNDARIES)
    assert supported["maxItems"] == len(BOUNDARIES)
