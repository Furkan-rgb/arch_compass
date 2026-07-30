"""The overview says what the verdicts amount to, and may not exceed them.

Every test here defends one of three properties: no boundary reference crosses the wire in
either direction, a statement that rests on nothing is not recorded, and the overview cannot
carry a verdict of its own. The first two are §12.0 applied to a stage whose whole output is
prose; the third is why a summary cannot quietly overrule the judgement that produced it.
"""

from __future__ import annotations

import json
from typing import cast

import pytest

from archcompass.adapters.models.structured import ChatMessage, StructuredReasoningProvider
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.atlas import (
    FindingCandidate,
    FindingParticipant,
    FindingPattern,
)
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.domain.review import (
    BoundaryReviewReport,
    OverviewStatement,
    ReviewedBoundary,
    ReviewOverview,
)
from archcompass.ports.reasoning import ReasoningTask


class _RecordingTransport:
    """A transport that returns scripted replies and remembers what it was asked."""

    provider_label = "Fake"

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.requests: list[dict[str, object]] = []

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: object,
        task: ReasoningTask,
        is_fast: bool,
        think: object,
        temperature: float | None,
    ) -> str:
        del is_fast, think, temperature
        self.requests.append({"messages": messages, "schema": schema, "task": task})
        return self._replies.pop(0)


def _provider(*replies: str) -> tuple[StructuredReasoningProvider, _RecordingTransport]:
    transport = _RecordingTransport(*replies)
    config = ReasoningModelConfig(
        provider="fake",
        model="fake-summariser",
        timeout_seconds=30,
        context_window_tokens=131072,
        max_output_tokens=8192,
    )
    return StructuredReasoningProvider(config, transport), transport


def _case() -> ArchitectureCase:
    return ArchitectureCase(
        title="Scheduler boundaries",
        problem_statement="Decide which boundaries earn their place.",
        desired_outcome="A verdict per boundary.",
        non_goals=["A second label format."],
    )


def _boundary(reference: str, name: str, *, material: bool) -> ReviewedBoundary:
    """One reviewed boundary whose own text never contains its reference.

    Named separately from the reference on purpose: a fixture that embedded `BR-001` in the
    abstraction's name would make the assertion below pass or fail for the wrong reason.
    """

    return ReviewedBoundary(
        reference=reference,
        candidate=FindingCandidate(
            pattern=FindingPattern.SOLE_IMPLEMENTATION,
            summary=f"package.{name} is implemented only by package.{name}Adapter.",
            participants=[
                FindingParticipant(
                    node_id=name.lower(),
                    qualified_name=f"package.{name}",
                    role="Declares the abstraction.",
                ),
                FindingParticipant(
                    node_id=f"{name.lower()}-adapter",
                    qualified_name=f"package.{name}Adapter",
                    role="The only implementation of it in this repository.",
                ),
            ],
            limitations="A static count cannot see runtime registration.",
        ),
        material=material,
        rationale="Argued from the case.",
        recommended_response="Call the implementation directly." if material else "",
    )


BOUNDARIES = [
    _boundary("BR-001", "Formatter", material=True),
    _boundary("BR-002", "Clock", material=False),
    _boundary("BR-003", "Store", material=True),
]


def _reply(
    *,
    themes: list[tuple[str, list[bool]]] | None = None,
    sequence: list[tuple[str, list[bool]]] | None = None,
) -> str:
    return json.dumps(
        {
            "situation": "One operator, one server, a fixed label format.",
            "themes": [
                {"text": text, "supported_by": flags} for text, flags in (themes or [])
            ],
            "recommended_sequence": [
                {"text": text, "supported_by": flags} for text, flags in (sequence or [])
            ],
            "limits": "One detector ran.",
        }
    )


def test_the_boundaries_are_presented_without_their_references() -> None:
    """A reference in the input is a reference the model can quote back (§12.0)."""

    provider, transport = _provider(
        _reply(themes=[("Two absorb ruled-out variation.", [True, False, True])])
    )

    provider.summarise_review(_case(), BOUNDARIES)

    sent = cast(list[ChatMessage], transport.requests[0]["messages"])
    request = "\n".join(message["content"] for message in sent)
    for boundary in BOUNDARIES:
        assert boundary.reference not in request
    # The substance is there; only the identifier is withheld.
    assert "package.Formatter" in request


def test_positions_become_references_the_application_owns() -> None:
    provider, _ = _provider(
        _reply(
            themes=[("Two absorb ruled-out variation.", [True, False, True])],
            sequence=[("Remove the first.", [True, False, False])],
        )
    )

    overview = provider.summarise_review(_case(), BOUNDARIES)

    assert overview.themes[0].supporting_references == ["BR-001", "BR-003"]
    assert overview.recommended_sequence[0].supporting_references == ["BR-001"]
    assert overview.situation
    assert overview.limits


def test_a_statement_resting_on_no_boundary_is_not_recorded() -> None:
    """Dropped rather than kept as unsupported prose — and the rest still stands."""

    provider, _ = _provider(
        _reply(
            themes=[
                ("Grounded in the first boundary.", [True, False, False]),
                ("A general remark about software.", [False, False, False]),
            ],
            sequence=[("Do something unspecified.", [False, False, False])],
        )
    )

    overview = provider.summarise_review(_case(), BOUNDARIES)

    assert [statement.text for statement in overview.themes] == [
        "Grounded in the first boundary."
    ]
    assert overview.recommended_sequence == []


def test_a_short_flag_list_is_refused_rather_than_silently_shifted() -> None:
    """Arity is the whole binding: a missing flag re-maps every flag after it."""

    short = _reply(themes=[("Two of them.", [True, False])])
    provider, transport = _provider(short, short)

    with pytest.raises(ModelOutputValidationError):
        provider.summarise_review(_case(), BOUNDARIES)

    # One repair round was offered, and the second failure is recorded rather than accepted.
    assert len(transport.requests) == 2


def test_the_response_grammar_states_the_flag_count() -> None:
    """Stated in the schema so the common case never reaches the validator."""

    provider, transport = _provider(
        _reply(themes=[("Two of them.", [True, False, True])])
    )

    provider.summarise_review(_case(), BOUNDARIES)

    schema = cast(dict[str, object], transport.requests[0]["schema"])
    definitions = cast(dict[str, object], schema["$defs"])
    statement = cast(dict[str, object], definitions["ProposedOverviewStatement"])
    supported = cast(
        dict[str, object], cast(dict[str, object], statement["properties"])["supported_by"]
    )
    assert supported["minItems"] == len(BOUNDARIES)
    assert supported["maxItems"] == len(BOUNDARIES)


def _reply_with_situation(situation: str) -> str:
    document = json.loads(_reply(themes=[("Two of them.", [True, False, True])]))
    document["situation"] = situation
    return json.dumps(document)


#: What a live run actually returned in `situation`: the stage's arity note said "every
#: statement carries one supported_by flag", `situation` reads like a statement, and a JSON
#: document is a perfectly valid string — so this validated, persisted, and printed verbatim
#: as the conclusion at the top of the review page.
JSON_AS_PROSE = json.dumps(
    {
        "statement": "Leaked identifiers prevent a second vendor being added.",
        "supported_by": [True, True, False],
    }
)


def test_a_conclusion_answered_with_json_is_refused_rather_than_printed() -> None:
    """A prose field holds sentences. A string that is a document is not prose.

    The schema cannot express this: `situation` is a string, and structure written inside a
    string satisfies every constraint a string can carry. So it is checked after validation,
    where the one sanctioned repair round can ask for prose — and a second refusal fails the
    review rather than storing JSON in a record that is immutable once written.
    """

    bad = _reply_with_situation(JSON_AS_PROSE)
    provider, transport = _provider(bad, bad)

    with pytest.raises(ModelOutputValidationError, match="must be prose"):
        provider.summarise_review(_case(), BOUNDARIES)

    assert len(transport.requests) == 2


def test_the_repair_round_is_told_what_prose_means() -> None:
    provider, transport = _provider(
        _reply_with_situation(JSON_AS_PROSE),
        _reply_with_situation("Two vendors are coming and three boundaries block them."),
    )

    overview = provider.summarise_review(_case(), BOUNDARIES)

    assert overview.situation == "Two vendors are coming and three boundaries block them."
    complaint = cast(list[ChatMessage], transport.requests[1]["messages"])[-1]["content"]
    assert "situation must be prose" in complaint


def test_prose_that_merely_opens_with_a_bracket_is_left_alone() -> None:
    """Both conditions are required, or the guard would refuse sentences.

    A leading brace or bracket is not evidence of anything on its own — a conclusion may
    reasonably open with a bracketed aside — so nothing is refused unless the whole field also
    parses as a JSON document.
    """

    aside = "[in short] three boundaries block the vendor the case says is coming."
    provider, _ = _provider(_reply_with_situation(aside))

    assert provider.summarise_review(_case(), BOUNDARIES).situation == aside


def test_the_stage_tells_the_model_which_fields_carry_flags() -> None:
    """The instruction that produced the defect said "every statement", of four fields."""

    provider, transport = _provider(
        _reply(themes=[("Two of them.", [True, False, True])])
    )

    provider.summarise_review(_case(), BOUNDARIES)

    sent = cast(list[ChatMessage], transport.requests[0]["messages"])
    request = "\n".join(message["content"] for message in sent)
    assert "situation and limits are prose and carry no flags" in request
    assert "Every entry in themes and recommended_sequence" in request


def test_the_overview_has_no_field_in_which_to_restate_a_verdict() -> None:
    """The structural half of "a summary may not overrule its own judgement"."""

    fields = set(ReviewOverview.model_fields)

    assert fields == {
        "situation",
        "themes",
        "recommended_sequence",
        "limits",
        "open_questions",
    }
    assert not {"material", "verdict", "confidence"} & fields


def test_a_report_refuses_an_overview_citing_a_boundary_it_does_not_contain() -> None:
    """The last line of defence, independent of any adapter."""

    with pytest.raises(ValueError, match="cites boundaries this review lacks"):
        BoundaryReviewReport(
            case_title="Scheduler boundaries",
            problem_and_desired_outcome="Decide.\n\nA verdict per boundary.",
            reviewed=[_boundary("BR-001", "Formatter", material=True)],
            overview=ReviewOverview(
                situation="One operator.",
                themes=[
                    OverviewStatement(
                        text="Two absorb ruled-out variation.",
                        supporting_references=["BR-001", "BR-009"],
                    )
                ],
                limits="One detector ran.",
            ),
        )
