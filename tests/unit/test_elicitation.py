"""The review asks for the case: hinges on verdicts, questions across them (§6C).

Two stages carry elicitation and neither is new. Judgement says what its verdict assumed
because the case was silent; the overview consolidates those admissions into questions a
person can answer. Every test here defends one of four properties: "nothing was open" is
something the model says rather than something inferred from a blank field, a hinge that
claims to exist must say what it is, a question binds to boundaries by position and never
by a reference the model wrote, and a question grounded on nothing is not recorded.
"""

from __future__ import annotations

import json
from typing import cast

import pytest

from archcompass.adapters.models.structured import (
    ChatMessage,
    ProposedCandidateVerdict,
    StructuredReasoningProvider,
    opening_capital,
)
from archcompass.application.review_rendering import render_report
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.atlas import (
    FindingCandidate,
    FindingMeasurement,
    FindingParticipant,
    FindingPattern,
)
from archcompass.domain.case import ArchitectureCase, CaseField
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.domain.policy import (
    PolicyDocument,
    PolicyScope,
    PolicySource,
    PolicyStrength,
)
from archcompass.domain.review import (
    BoundaryReviewReport,
    OpenQuestion,
    ReviewedBoundary,
    ReviewOverview,
    VerdictHinge,
)
from archcompass.ports.reasoning import ReasoningTask


class _RecordingTransport:
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
        think: object,
        temperature: float | None,
    ) -> str:
        del think, temperature
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


def _case() -> ArchitectureCase:
    return ArchitectureCase(
        title="Scheduler boundaries",
        problem_statement="Decide which boundaries earn their place.",
        desired_outcome="A verdict per boundary.",
    )


def _candidate() -> FindingCandidate:
    return FindingCandidate(
        pattern=FindingPattern.SOLE_IMPLEMENTATION,
        summary="package.Port is implemented only by package.Adapter.",
        participants=[
            FindingParticipant(
                node_id="port",
                qualified_name="package.Port",
                role="Declares the abstraction.",
            )
        ],
        measurements=[FindingMeasurement(name="implementations", value=1)],
        limitations="A static count cannot see runtime registration.",
    )


POLICIES = [
    PolicyDocument(
        id="only-policy",
        title="Only Policy",
        scope=PolicyScope.GENERAL,
        strength=PolicyStrength.PREFERRED,
        tags=["structure"],
        source=PolicySource(author="test"),
        body="Body.",
        source_path="policies/only.md",
        content_hash="hash",
    )
]


def _verdict_reply(hinge: dict[str, str]) -> str:
    return json.dumps(
        {
            "rationale": "Argued from the case.",
            "policy_bearings": [{"bears_on": False, "how": ""}],
            "hinge": hinge,
            "verdict": "leave_as_is",
            "recommended_response": "",
        }
    )


TURNS_ON = {
    "dependence": "turns_on_this_unknown",
    "unknown": "The case does not say whether a second vendor is contracted.",
    "if_confirmed": "The boundary absorbs a change that is coming and should stay.",
    "if_denied": "Nothing arrives to justify the indirection; it should be removed.",
}


def test_a_declared_hinge_is_carried_onto_the_verdict() -> None:
    """What the case did not say is recorded, not spent reaching the verdict and dropped."""

    provider, _ = _provider(_verdict_reply(TURNS_ON))

    verdict = provider.judge_finding_candidate(_case(), _candidate(), POLICIES)

    assert verdict.hinge is not None
    assert verdict.hinge.unknown == TURNS_ON["unknown"]
    assert verdict.hinge.if_confirmed == TURNS_ON["if_confirmed"]
    assert verdict.hinge.if_denied == TURNS_ON["if_denied"]


def test_standing_either_way_is_recorded_as_no_hinge() -> None:
    """The declaration becomes an absence in the domain, and only here.

    The prose fields are deliberately filled in this reply. A verdict that considered an
    unknown and concluded it does not move is still a verdict with no hinge, and reading
    the leftover prose as one would put a question to the reader that the stage had just
    said was not worth asking.
    """

    provider, _ = _provider(
        _verdict_reply({**TURNS_ON, "dependence": "stands_either_way"})
    )

    verdict = provider.judge_finding_candidate(_case(), _candidate(), POLICIES)

    assert verdict.hinge is None


def test_the_working_behind_the_declaration_is_required_by_the_grammar() -> None:
    """The fix, stated in the grammar rather than in the request, which already said it.

    What optional fields cost is written on `ProposedVerdictHinge`.
    """

    schema = ProposedCandidateVerdict.model_json_schema()
    hinge = schema["$defs"]["ProposedVerdictHinge"]

    assert set(hinge["required"]) == {"unknown", "if_confirmed", "if_denied", "dependence"}
    for field in ("unknown", "if_confirmed", "if_denied"):
        assert hinge["properties"][field]["minLength"] == 1


def test_a_hinge_claiming_to_exist_without_saying_what_it_is_is_dropped() -> None:
    """What the grammar cannot require is that the writing says anything.

    `minLength` counts characters and a space is a character, so this is still reachable and
    still read rather than refused. Recording it would tell a reader their verdict rests on
    something and never say what.
    """

    provider, _ = _provider(_verdict_reply({**TURNS_ON, "unknown": "   "}))

    verdict = provider.judge_finding_candidate(_case(), _candidate(), POLICIES)

    assert verdict.hinge is None
    # The rest of the reply is untouched: the argument and the verdict were never in doubt.
    assert verdict.rationale == "Argued from the case."
    assert verdict.material is False


def test_a_partial_hinge_is_dropped_rather_than_half_recorded() -> None:
    """A hinge without both branches cannot say which way the verdict moves."""

    provider, _ = _provider(_verdict_reply({**TURNS_ON, "if_denied": " "}))

    assert provider.judge_finding_candidate(_case(), _candidate(), POLICIES).hinge is None


def test_one_answer_written_under_both_branches_is_dropped() -> None:
    """The door the required fields open, and the one code can shut.

    Three fields that must be filled can be filled with the same sentence twice, which is a
    verdict that does not move however the word beside it reads.
    """

    same = "The boundary stays either way."
    provider, _ = _provider(
        _verdict_reply({**TURNS_ON, "if_confirmed": same, "if_denied": f"  {same} "})
    )

    assert provider.judge_finding_candidate(_case(), _candidate(), POLICIES).hinge is None


def test_a_blank_hinge_costs_no_repair_round_and_no_review() -> None:
    """Dropping rather than raising, and the reasoning for the difference.

    A blank hinge binds nothing — it is the one part of this reply where no position
    attributes anything — so a bad one shifts no other answer onto the wrong thing. Failing
    would discard a whole review's worth of correct verdicts, each already paid for, over
    prose answered with a space. Arity is the opposite case and still fails loudly, which
    the test below this one holds.
    """

    provider, transport = _provider(_verdict_reply({**TURNS_ON, "unknown": " "}))

    provider.judge_finding_candidate(_case(), _candidate(), POLICIES)

    assert len(transport.requests) == 1


def test_a_short_list_of_bearings_still_fails_loudly() -> None:
    """The contrast that makes dropping a hinge safe rather than lax.

    Nothing in a bearing says which policy it answers, so a list one entry short does not
    lose one answer — it shifts every later answer onto the wrong policy and still parses.
    That is a mis-binding, and it is refused after the one sanctioned repair round.
    """

    short = json.dumps(
        {
            "rationale": "Argued from the case.",
            "policy_bearings": [],
            "hinge": {**TURNS_ON, "dependence": "stands_either_way"},
            "verdict": "leave_as_is",
            "recommended_response": "",
        }
    )
    provider, _ = _provider(short, short)

    with pytest.raises(ModelOutputValidationError, match="policy_bearings"):
        provider.judge_finding_candidate(_case(), _candidate(), POLICIES)


def test_the_hinge_is_asked_for_before_the_verdict() -> None:
    """Field order is the contract (§12.0): a hinge is part of the argument.

    Declared after the verdict it would be a justification for a conclusion already
    reached — which is the defect that put `rationale` ahead of `verdict` in the first
    place, and there is no reason it would behave differently here.
    """

    order = list(ProposedCandidateVerdict.model_json_schema()["properties"])

    assert order.index("rationale") < order.index("hinge") < order.index("verdict")


def _boundary(reference: str, name: str, *, hinge: VerdictHinge | None) -> ReviewedBoundary:
    """One judged boundary whose own text never contains its reference."""

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
                )
            ],
            limitations="A static count cannot see runtime registration.",
        ),
        material=False,
        rationale="Argued from the case.",
        hinge=hinge,
    )


SECOND_VENDOR = VerdictHinge(
    unknown="The case does not say whether a second vendor is contracted.",
    if_confirmed="The boundary absorbs a change that is coming.",
    if_denied="Nothing arrives to justify the indirection.",
)

BOUNDARIES = [
    _boundary("BR-001", "Speech", hinge=SECOND_VENDOR),
    _boundary("BR-002", "Clock", hinge=None),
    _boundary("BR-003", "Voice", hinge=SECOND_VENDOR),
]


def _elicitation_reply(*questions: tuple[str, list[bool]]) -> str:
    return json.dumps(
        {
            "open_questions": [
                {
                    "what_the_review_saw": "Speech and Voice both wrap one implementation.",
                    "unknown": "whether a second vendor is contracted",
                    "why_it_matters": f"Two verdicts move: {text}",
                    "supported_by": flags,
                    "question": text,
                    "answer_belongs_in": "expected_future_changes",
                }
                for text, flags in questions
            ],
        }
    )


def test_a_question_resolves_to_the_boundaries_that_occupied_its_slots() -> None:
    """Positional binding, exactly as themes and answers already bind (§12.0)."""

    provider, _ = _provider(
        _elicitation_reply(("Is a second vendor contracted?", [True, False, True]))
    )

    questions = provider.elicit_questions(_case(), BOUNDARIES)

    assert [item.reference for item in questions] == ["Q-1"]
    assert questions[0].supporting_references == ["BR-001", "BR-003"]
    assert questions[0].answer_belongs_in is CaseField.EXPECTED_FUTURE_CHANGES


def test_a_question_carries_what_was_seen_and_a_subject_for_the_answer() -> None:
    """The two fields v2 separated, which v1 had collapsed into one restatement.

    `what_the_review_saw` is the evidence a reader cannot supply for themselves, and `unknown`
    is what the question is about rather than a description of it — which is what lets it title
    a discussion of the question and lets a reader recognise the same subject coming back
    across two passes. A question whose unknown is its own question with the question mark
    removed can do neither job.
    """

    provider, _ = _provider(
        _elicitation_reply(("Is a second vendor contracted?", [True, False, True]))
    )

    questions = provider.elicit_questions(_case(), BOUNDARIES)

    assert questions[0].what_the_review_saw == (
        "Speech and Voice both wrap one implementation."
    )
    # Opened with a capital by the application. The reply said "whether a second vendor is
    # contracted", which is the phrasing the contract asks for and reads as a fragment
    # everywhere it is then printed — under a heading, in a step of the walk, and in the case.
    assert questions[0].unknown == "Whether a second vendor is contracted"


def test_a_question_resting_on_no_boundary_is_discarded() -> None:
    """The same treatment an ungrounded theme receives.

    A question about nothing this review examined is not a question about this repository,
    and recording it would put an unanswerable prompt in front of a reader with no verdict
    behind it to explain why it was asked.
    """

    provider, _ = _provider(
        _elicitation_reply(("Will the requirements change?", [False, False, False]))
    )

    assert provider.elicit_questions(_case(), BOUNDARIES) == []


def test_question_numbering_is_gapless_after_a_discard() -> None:
    """`Q-n` is assigned after the drop, so a reader is never shown a missing number."""

    provider, _ = _provider(
        _elicitation_reply(
            ("Grounded on nothing.", [False, False, False]),
            ("Is a second vendor contracted?", [True, False, True]),
            ("Is the label format fixed?", [False, True, False]),
        )
    )

    questions = provider.elicit_questions(_case(), BOUNDARIES)

    assert [item.reference for item in questions] == ["Q-1", "Q-2"]
    assert questions[0].question == "Is a second vendor contracted?"


def test_the_hinges_are_presented_to_the_stage_that_consolidates_them() -> None:
    """A stage cannot merge admissions it was never shown.

    Both halves matter: the boundary that named an unknown carries it, and the one that
    did not says so in words rather than by omitting the key — an absent field reads as
    "not mentioned", and standing either way is a positive finding.
    """

    provider, transport = _provider(
        _elicitation_reply(("Is a second vendor contracted?", [True, False, True]))
    )

    provider.elicit_questions(_case(), BOUNDARIES)

    sent = cast(list[ChatMessage], transport.requests[0]["messages"])
    request = "\n".join(message["content"] for message in sent)
    assert SECOND_VENDOR.unknown in request
    assert "this verdict stands whichever way" in request
    # And the identifiers still do not cross the wire, questions or no questions.
    for boundary in BOUNDARIES:
        assert boundary.reference not in request


def test_the_schema_fixes_one_flag_per_boundary_inside_a_question() -> None:
    """Arity is the whole binding: a short list re-attributes every flag after the gap."""

    provider, transport = _provider(
        _elicitation_reply(("Is a second vendor contracted?", [True, False, True]))
    )

    provider.elicit_questions(_case(), BOUNDARIES)

    schema = cast(dict[str, object], transport.requests[0]["schema"])
    definitions = cast(dict[str, object], schema["$defs"])
    question = cast(dict[str, object], definitions["ProposedOpenQuestion"])
    flags = cast(dict[str, object], cast(dict[str, object], question["properties"])["supported_by"])
    assert flags["minItems"] == len(BOUNDARIES)
    assert flags["maxItems"] == len(BOUNDARIES)


def test_a_wrong_length_of_flags_is_refused_rather_than_re_attributed() -> None:
    short = _elicitation_reply(("Is a second vendor contracted?", [True, False]))
    provider, _ = _provider(short, short)

    with pytest.raises(ModelOutputValidationError, match="supported_by"):
        provider.elicit_questions(_case(), BOUNDARIES)


def test_the_destination_is_a_closed_set_the_model_chooses_from() -> None:
    """The model picks a slot; it never names a field (§12.0).

    A free-text destination is an identifier written by a model, and it would fail exactly
    as 12.0 predicts: a plausible misspelling routes an answer to a field that does not
    exist, and nothing downstream can tell that from a field the case has not got.
    """

    provider, transport = _provider(
        _elicitation_reply(("Is a second vendor contracted?", [True, False, True]))
    )

    provider.elicit_questions(_case(), BOUNDARIES)

    schema = cast(dict[str, object], transport.requests[0]["schema"])
    definitions = cast(dict[str, object], schema["$defs"])
    assert sorted(cast(dict[str, object], definitions["CaseField"])["enum"]) == sorted(
        field.value for field in CaseField
    )


def test_the_summarising_stage_has_no_way_to_ask_anything() -> None:
    """What terminates the loop, held in the grammar rather than in prose.

    A second pass runs against a case the reader has just answered, and a reply that could
    open a fresh round would leave the flow with no way to end. Stating that as an
    instruction would leave it to a model to obey; removing the field means a reply carrying
    a question does not parse at all.
    """

    from archcompass.adapters.models.structured import ProposedReviewOverview

    assert "open_questions" not in ProposedReviewOverview.model_json_schema()["properties"]


def _report(questions: list[OpenQuestion]) -> BoundaryReviewReport:
    return BoundaryReviewReport(
        case_title="Scheduler boundaries",
        problem_and_desired_outcome="Decide.\n\nA verdict per boundary.",
        reviewed=BOUNDARIES,
        overview=ReviewOverview(
            situation="One operator, one server.",
            limits="A static count cannot see runtime registration.",
            open_questions=questions,
        ),
    )


def _question(reference: str, *references: str) -> OpenQuestion:
    return OpenQuestion(
        reference=reference,
        what_the_review_saw="Speech and Voice both wrap one implementation.",
        unknown="whether a second vendor is contracted",
        why_it_matters="Two verdicts move.",
        question="Is a second vendor contracted?",
        answer_belongs_in=CaseField.EXPECTED_FUTURE_CHANGES,
        supporting_references=list(references),
    )


def test_a_report_refuses_a_question_citing_a_boundary_it_does_not_contain() -> None:
    """The last line of defence, independent of any adapter."""

    with pytest.raises(ValueError, match="cites boundaries this review lacks"):
        _report([_question("Q-1", "BR-404")])


def test_a_report_refuses_two_questions_sharing_one_reference() -> None:
    with pytest.raises(ValueError, match="Open question references must be unique"):
        _report([_question("Q-1", "BR-001"), _question("Q-1", "BR-003")])


def test_a_pass_that_is_asking_renders_its_questions_and_withholds_its_verdicts() -> None:
    """The document a first pass produces: what it needs to know, and no findings.

    Each question prints once with the boundaries it would settle and the field an answer
    lands in. The verdicts behind those citations are deliberately absent — they exist and
    are stored, but four of five moved on the bundled example once its questions were
    answered, so printing them under "what should change" would report as findings a set
    that is more likely wrong than right (ADR 0010).
    """

    markdown = render_report(
        _report([_question("Q-1", "BR-001", "BR-003")]), awaiting_answers=True
    )

    assert "## What it needs to know" in markdown
    assert "**Q-1. Is a second vendor contracted?**" in markdown
    # The observation, as prose under the question. It is the part of a question a reader
    # cannot work out for themselves, so it is not filed as one bullet among three.
    assert "Speech and Voice both wrap one implementation." in markdown
    assert "(BR-001, BR-003)" in markdown
    assert "`expected_future_changes`" in markdown
    # No findings, and the reader is told that is a choice rather than a gap.
    assert "## What should change" not in markdown
    assert "Examined and left alone" not in markdown
    assert "*This verdict turns on an open question.*" not in markdown
    assert "waiting on answers" in markdown


def test_a_concluded_review_prints_each_hinge_against_its_own_boundary() -> None:
    """A verdict that still rests on something says so where it is acted on.

    The reader was asked and did not answer, so the contingency survives into the findings.
    It is repeated per boundary for the same reason detection limits are: someone deciding
    whether to act on one verdict needs to know what it rested on at the point of deciding,
    not in a footer they have already scrolled past.
    """

    markdown = render_report(_report([]))

    # Against each boundary that carries one, and not against the one that does not.
    assert markdown.count("*This verdict turns on an open question.*") == 2


def test_a_review_with_nothing_open_renders_no_question_section() -> None:
    """Empty is the good outcome, and it must not read as a missing section."""

    markdown = render_report(_report([]))

    assert "What it needs to know" not in markdown


def test_a_question_is_opened_with_a_capital_and_not_otherwise_touched() -> None:
    """The whole of the normalization, including everything it deliberately will not do.

    A model writes these fields as fragments — "is there a requirement for a second sink?" —
    because that is how the contract asks for them, and by the time a reader sees one it is a
    sentence: under a heading, in a step of the walk, and in the case as the question half of a
    clarification. So the application raises the first letter and stops there.

    Stopping there is the point. What people write in these fields is full of identifiers, and
    anything more ambitious mangles them: lower-casing would turn `SQLite` into `sQLite` and
    `BUILT_IN_VOICES` into something nobody can grep for, and title-casing would wreck a
    sentence. A string that does not open on a lower-case letter is left exactly as it is,
    because there is no first letter to raise and guessing where the sentence really begins is
    how a fix like this starts damaging text it was never about.
    """

    assert opening_capital("is a second vendor contracted?") == (
        "Is a second vendor contracted?"
    )
    # Already a sentence, so nothing to do — and nothing done, byte for byte.
    assert opening_capital("Is a second vendor contracted?") == (
        "Is a second vendor contracted?"
    )
    # No first letter to raise. A digit, a quote and a backtick all open strings these fields
    # really carry, and each is left alone rather than searched past for a letter.
    assert opening_capital("3 of 5 verdicts move on this.") == "3 of 5 verdicts move on this."
    assert opening_capital("`AudioSink` has one implementation.") == (
        "`AudioSink` has one implementation."
    )
    assert opening_capital('"only one caller reads it" is the claim.') == (
        '"only one caller reads it" is the claim.'
    )
    # The rest of the string is untouched, which is what keeps an identifier readable.
    assert opening_capital("the SQLite choice is settled; BUILT_IN_VOICES is not.") == (
        "The SQLite choice is settled; BUILT_IN_VOICES is not."
    )
    assert opening_capital("") == ""
