"""The judgement stage binds policies by position, never by anything the model writes.

Every test here defends one property: no policy identifier crosses the wire in either
direction. The model sees a numbered list and answers slot by slot, so a mistyped or
recalled-from-memory policy ID has no route into a verdict (master plan 12.0).

That makes arity the whole contract. A reply one entry short does not lose one answer —
it shifts every answer after the gap onto the wrong policy and still validates, which is
why the count is stated in the grammar and checked again after parsing.
"""

from __future__ import annotations

import json
from typing import cast

import pytest

from archcompass.adapters.models.structured import (
    ChatMessage,
    ProposedCandidateVerdict,
    StructuredReasoningProvider,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.atlas import (
    FindingCandidate,
    FindingMeasurement,
    FindingParticipant,
    FindingPattern,
)
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.domain.policy import (
    PolicyDocument,
    PolicyScope,
    PolicySource,
    PolicyStrength,
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
        model="fake-judge",
        timeout_seconds=30,
        context_window_tokens=131072,
        max_output_tokens=8192,
    )
    return StructuredReasoningProvider(config, transport), transport


def _policy(policy_id: str, title: str) -> PolicyDocument:
    return PolicyDocument(
        id=policy_id,
        title=title,
        scope=PolicyScope.GENERAL,
        strength=PolicyStrength.PREFERRED,
        tags=["structure"],
        source=PolicySource(author="test"),
        body=f"{title} body.",
        source_path=f"policies/{policy_id}.md",
        content_hash=f"hash-{policy_id}",
    )


POLICIES = [
    _policy("first-policy", "First Policy"),
    _policy("second-policy", "Second Policy"),
    _policy("third-policy", "Third Policy"),
]


def _candidate() -> FindingCandidate:
    return FindingCandidate(
        pattern=FindingPattern.SOLE_IMPLEMENTATION,
        summary="package.Port is implemented only by package.Adapter.",
        participants=[
            FindingParticipant(
                node_id="port",
                qualified_name="package.Port",
                role="Declares the abstraction.",
            ),
            FindingParticipant(
                node_id="adapter",
                qualified_name="package.Adapter",
                role="The only implementation of it in this repository.",
            ),
        ],
        measurements=[FindingMeasurement(name="implementations", value=1, unit="implementations")],
        limitations="Counted from one static snapshot.",
    )


def _case() -> ArchitectureCase:
    return ArchitectureCase(
        title="Keep the storage seam",
        problem_statement="Decide whether the persistence boundary earns its place.",
        desired_outcome="A defensible answer either way.",
    )


def _reply(
    *bearings: tuple[bool, str],
    material: bool = False,
    response: str = "",
    hinge: dict[str, str] | None = None,
) -> str:
    return json.dumps(
        {
            "verdict": "should_change" if material else "leave_as_is",
            "rationale": "The boundary is the process edge this case names.",
            "policy_bearings": [{"bears_on": flag, "how": how} for flag, how in bearings],
            # The ordinary answer, so a test about policy binding does not have to say
            # anything about elicitation to be a well-formed reply.
            "hinge": hinge or {"dependence": "stands_either_way"},
            "recommended_response": response,
        }
    )


def test_no_policy_identifier_is_ever_sent_to_the_model() -> None:
    """The premise of the whole design: a model cannot copy back what it never saw."""

    provider, transport = _provider(_reply((False, ""), (False, ""), (False, "")))

    provider.judge_finding_candidate(_case(), _candidate(), POLICIES)

    sent = json.dumps(transport.requests[0]["messages"])
    for policy in POLICIES:
        assert policy.id not in sent
        assert policy.title in sent


def test_a_bearing_resolves_to_the_policy_that_occupied_its_slot() -> None:
    provider, _ = _provider(
        _reply((False, ""), (True, "The seam is exactly what this policy asks for."), (False, ""))
    )

    verdict = provider.judge_finding_candidate(_case(), _candidate(), POLICIES)

    assert [bearing.policy_id for bearing in verdict.policy_bearings] == ["second-policy"]
    assert verdict.policy_bearings[0].policy_title == "Second Policy"


def test_the_schema_fixes_one_entry_per_supplied_policy() -> None:
    """Stated in the grammar, so the common case never reaches the check below."""

    provider, transport = _provider(_reply((False, ""), (False, ""), (False, "")))

    provider.judge_finding_candidate(_case(), _candidate(), POLICIES)

    schema = cast(
        "dict[str, dict[str, dict[str, int]]]",
        transport.requests[0]["schema"],
    )

    bearings = schema["properties"]["policy_bearings"]
    assert bearings["minItems"] == len(POLICIES)
    assert bearings["maxItems"] == len(POLICIES)


def test_a_short_reply_is_repaired_rather_than_re_attributed() -> None:
    """The failure this stage exists to prevent, and it is silent without the check.

    Two bearings for three policies parses cleanly. Zipped without a count check, the
    second policy's answer would be recorded against the third.
    """

    provider, transport = _provider(
        _reply((False, ""), (True, "Bears on the second policy.")),
        _reply((False, ""), (True, "Bears on the second policy."), (False, "")),
    )

    verdict = provider.judge_finding_candidate(_case(), _candidate(), POLICIES)

    assert len(transport.requests) == 2
    assert [bearing.policy_id for bearing in verdict.policy_bearings] == ["second-policy"]


def test_a_reply_that_stays_the_wrong_length_fails_loudly() -> None:
    provider, _ = _provider(_reply((False, "")), _reply((False, "")))

    with pytest.raises(ModelOutputValidationError, match="exactly 3 entries"):
        provider.judge_finding_candidate(_case(), _candidate(), POLICIES)


def test_a_bearing_asserted_without_saying_how_is_not_recorded() -> None:
    """A policy name with no explanation is not evidence a reader can check."""

    provider, _ = _provider(_reply((True, "   "), (False, ""), (False, "")))

    verdict = provider.judge_finding_candidate(_case(), _candidate(), POLICIES)

    assert verdict.policy_bearings == []


def test_an_immaterial_verdict_carries_no_recommended_response() -> None:
    """An advisor that always has a next action has not answered the question."""

    provider, _ = _provider(
        _reply((False, ""), (False, ""), (False, ""), response="Remove the interface.")
    )

    verdict = provider.judge_finding_candidate(_case(), _candidate(), POLICIES)

    assert verdict.material is False
    assert verdict.recommended_response == ""


def test_the_verdict_is_a_word_the_model_chooses_rather_than_a_polarity_it_sets() -> None:
    """The inversion this replaced, and why a better field name would not have been enough.

    `material` was a bare `bool`, so the schema constraining generation carried nothing about
    which way it pointed — and read as ordinary English the name asks whether the boundary
    matters, which is the opposite of the finding it recorded. Three live runs argued a
    boundary was justified and recorded "should change", one of them writing "Retain the
    abstraction as it fulfills a mandatory technical constraint" into `recommended_response`
    beside it. The report, the summary and every question about them inherited that.

    A boolean named anything still has to be read for polarity, so the check that matters is
    the one below: the two values are words in the grammar, and nothing else is representable.
    """

    schema = cast(
        dict[str, object],
        ProposedCandidateVerdict.model_json_schema()["properties"],
    )
    verdict_field = cast(dict[str, object], schema["verdict"])

    assert sorted(cast(list[str], verdict_field["enum"])) == ["leave_as_is", "should_change"]
    assert "material" not in schema
    assert verdict_field.get("type") != "boolean"

    changed, _ = _provider(_reply((False, ""), (False, ""), (False, ""), material=True))
    kept, _ = _provider(_reply((False, ""), (False, ""), (False, ""), material=False))

    assert changed.judge_finding_candidate(_case(), _candidate(), POLICIES).material is True
    assert kept.judge_finding_candidate(_case(), _candidate(), POLICIES).material is False


def test_a_verdict_answered_with_the_old_boolean_is_refused() -> None:
    """`extra="forbid"` plus a required word: a stale flag cannot be read as a verdict.

    Worth stating rather than assuming. Silently defaulting a missing verdict would put the
    inversion back with no way to see it, and the fail-safe direction for a field this
    consequential is to refuse the reply and repair it.
    """

    stale = json.dumps(
        {
            "material": True,
            "rationale": "The boundary is the process edge this case names.",
            "policy_bearings": [{"bears_on": False, "how": ""} for _ in range(3)],
            "recommended_response": "Remove the interface.",
        }
    )
    provider, _ = _provider(stale, stale)

    with pytest.raises(ModelOutputValidationError):
        provider.judge_finding_candidate(_case(), _candidate(), POLICIES)


def test_the_verdict_carries_the_candidate_id_the_application_already_held() -> None:
    """Composed, never echoed: the request names one candidate, so it cannot be wrong."""

    provider, _ = _provider(_reply((False, ""), (False, ""), (False, "")))
    candidate = _candidate()

    verdict = provider.judge_finding_candidate(_case(), candidate, POLICIES)

    assert verdict.candidate_id == candidate.candidate_id
