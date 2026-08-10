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
from typing import Any, cast

import pytest
from tests.reasoning_support import candidate, review, reviewed_boundary

from archcompass.adapters.models.structured import (
    ChatMessage,
    StructuredReasoningProvider,
    ThinkLevel,
    review_answer_schema,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.atlas import (
    FindingMeasurement,
    FindingPattern,
    SourceLocation,
)
from archcompass.domain.atlas_map import AtlasMap, AtlasMapModule, AtlasMapRelation
from archcompass.domain.case import ArchitectureCase, CaseField
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.review import (
    AnsweredQuestion,
    BoundaryExcerpt,
    OpenQuestion,
    OverviewStatement,
    ReviewEvidence,
    ReviewOverview,
    ReviewStatus,
)
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
        think: ThinkLevel,
        temperature: float | None,
    ) -> str:
        del schema, task, think, temperature
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


CASE = ArchitectureCase(
    title="Voices",
    problem_statement="Decide which boundaries earn their place.",
    desired_outcome="A verdict per boundary.",
    technical_constraints=["Speech synthesis runs on the local machine only."],
    non_goals=["Streaming audio to a browser."],
)


#: The lines two of these boundaries were measured from. The stage receives these because a
#: reader asking "show me the code" is asking for exactly them, and without them a live
#: conversation answered that the review "does not include the specific lines of code".
EXCERPTS = [
    BoundaryExcerpt(
        reference="BR-002",
        qualified_name="package.Voices",
        role="States BUILT_IN_VOICES at this location.",
        location=SourceLocation(path="preflight/voices.py", start_line=9, end_line=9),
        text='    9 | BUILT_IN_VOICES = ["serena", "ryan"]',
    ),
    BoundaryExcerpt(
        reference="BR-003",
        qualified_name="package.Clock",
        role="Declares the abstraction.",
        location=SourceLocation(path="timing/clock.py", start_line=4, end_line=6),
        unavailable="This repository has changed since the review ran.",
    ),
]


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
        ReviewEvidence(case=CASE, excerpts=EXCERPTS),
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


def test_the_whole_pinned_case_reaches_the_stage_not_a_restatement_of_it() -> None:
    """The case travels with the review everywhere the review goes.

    This stage used to receive `problem_and_desired_outcome` — two sentences composed for
    the report — and none of the fields a verdict was actually weighed against. So "why was
    this condemned?" was answered by something that could not see the constraints and
    non-goals the judging stage had in front of it when it condemned it.
    """

    sent, _ = _request()

    assert CASE.problem_statement in sent
    assert CASE.technical_constraints[0] in sent
    assert CASE.non_goals[0] in sent


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


def test_an_unavailable_corpus_is_stated_in_the_request() -> None:
    """"No policies" and "the policies could not be read" call for different answers, so
    the stage is told which it was handed rather than shown an empty list for both."""

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
        ReviewEvidence(case=CASE, excerpts=EXCERPTS),
        [],
        "Which policies bear on this?",
        MethodKnowledge(
            method="What ArchCompass means by a boundary.",
            policy_corpus_unavailable="The policy corpus could not be read: boom",
        ),
    )

    sent = "\n".join(message["content"] for message in transport.messages)
    payload = json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])
    assert payload["background_policy_corpus"] == (
        "unavailable: The policy corpus could not be read: boom"
    )


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


def test_the_pinned_atlas_map_reaches_the_stage_and_a_missing_atlas_is_stated() -> None:
    """A question about a module no detector flagged is answerable at the structural level
    only if the structure is in the request — and a map that could not be assembled must
    say so rather than read as an empty repository."""

    def _payload(atlas_map: AtlasMap | None) -> Any:
        transport = _RecordingTransport(
            json.dumps(
                {"answer": "As the review has it.", "supported_by": [True, False, False]}
            )
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
            ReviewEvidence(case=CASE, excerpts=EXCERPTS, atlas_map=atlas_map),
            [],
            "What else imports the voices module?",
            MethodKnowledge(method="What ArchCompass means by a boundary.", policies=[]),
        )
        sent = "\n".join(message["content"] for message in transport.messages)
        return json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])

    folded = AtlasMap(
        modules=[
            AtlasMapModule(
                path="preflight/voices.py",
                members=["class package.Voices"],
                members_omitted=2,
            )
        ],
        relations=[
            AtlasMapRelation(
                source_module="planning/schedule.py",
                target_module="preflight/voices.py",
                kinds="imports(1)",
            )
        ],
        modules_omitted=3,
    )
    shown = _payload(folded)["pinned_atlas_map"]
    assert shown["modules"] == [
        {
            "module": "preflight/voices.py",
            "declares": ["class package.Voices"],
            "declarations_omitted": (
                "2 declarations omitted to fit the budget — absence from this list is "
                "not absence from the module"
            ),
        }
    ]
    assert shown["module_relationships"] == [
        "planning/schedule.py depends on preflight/voices.py: imports(1)"
    ]
    assert shown["modules_omitted"] == "3 modules omitted to fit the budget"

    gone = _payload(AtlasMap(unavailable="The atlas this review pinned is gone."))
    assert gone["pinned_atlas_map"] == (
        "unavailable: The atlas this review pinned is gone."
    )

    unassembled = _payload(None)
    assert unassembled["pinned_atlas_map"] == "not assembled for this stage"


def test_each_boundary_carries_its_participants_and_relationships() -> None:
    """What the judging stage always had and the talking stages lacked: which elements
    make the boundary up, and the edges the detector recorded among them, as names."""

    transport = _RecordingTransport(
        json.dumps({"answer": "As the review has it.", "supported_by": [True]})
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
    connected = reviewed_boundary("BR-001", "Formatter", material=True).model_copy(
        update={"candidate": candidate()}
    )

    provider.answer_review_question(
        review([connected]),
        ReviewEvidence(case=CASE, excerpts=[]),
        [],
        "What implements the port?",
        MethodKnowledge(method="What ArchCompass means by a boundary.", policies=[]),
    )

    sent = "\n".join(message["content"] for message in transport.messages)
    payload = json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])
    boundary = payload["boundaries"][0]

    assert boundary["participants"] == [
        {
            "qualified_name": "package.Port",
            "part_played": "Declares the abstraction.",
            "where": "not recorded",
        },
        {
            "qualified_name": "package.Adapter",
            "part_played": "The only implementation of it in this repository.",
            "where": "not recorded",
        },
    ]
    assert boundary["relationships"] == ["package.Adapter —implements→ package.Port"]
    # And the ids the edge was stored with never cross the wire.
    assert '"adapter"' not in sent.rsplit("\n\nInput:\n", maxsplit=1)[1]


def test_a_boundary_with_no_recorded_relationships_says_so_explicitly() -> None:
    """An absent key reads as "not mentioned" and an empty list as "unrelated"; this is
    neither — one detector records edges and the other two do not."""

    sent, _ = _request()
    payload = json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])

    for boundary in payload["boundaries"]:
        assert "none recorded" in boundary["relationships"]
        assert "detector" in boundary["relationships"]


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
            ReviewEvidence(case=CASE, excerpts=EXCERPTS),
            [],
            "Which one first?",
            MethodKnowledge(method="Primer.", policies=[]),
        )


def test_the_schema_fixes_one_flag_per_boundary() -> None:
    """Stated in the grammar, so the common case never reaches the validator."""

    schema = cast(
        dict[str, object],
        review_answer_schema(boundary_count=len(BOUNDARIES)),
    )
    properties = cast(dict[str, object], schema["properties"])
    supported = cast(dict[str, object], properties["supported_by"])

    assert supported["minItems"] == len(BOUNDARIES)
    assert supported["maxItems"] == len(BOUNDARIES)


def test_the_code_a_boundary_was_measured_from_reaches_the_stage() -> None:
    """The failure this exists to fix, asserted at the input.

    Asked to show the problematic code, a live conversation answered that the review "only
    contains the names of these modules and does not include the specific lines". That was
    true of what reached this stage and false of what the review holds — every participant
    carries an exact span. The lines now arrive attached to the boundary they belong to,
    because "which lines are which finding's" is the question being asked.
    """

    sent, _ = _request()
    payload = json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])
    by_reference = {
        item["position"]: item["source"] for item in payload["boundaries"]
    }

    # BR-002 is the second boundary supplied, and it is the one with readable lines.
    assert by_reference[2] == [
        {
            "where": "preflight/voices.py:9",
            "what_it_contributes": "States BUILT_IN_VOICES at this location.",
            "code": '    9 | BUILT_IN_VOICES = ["serena", "ryan"]',
            "why_there_is_no_code": None,
            "note": None,
        }
    ]


def test_a_boundary_whose_code_cannot_be_read_says_why_rather_than_vanishing() -> None:
    """A stated absence is the answer; silence would let the stage conclude there is none.

    "This repository has changed since the review ran" is the honest reply to "show me the
    code", and dropping the entry would leave the stage to report that the review has no
    source at all — which is the defect being fixed.
    """

    sent, _ = _request()
    payload = json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])
    third = next(item for item in payload["boundaries"] if item["position"] == 3)

    assert third["source"] == [
        {
            "where": "timing/clock.py:4",
            "what_it_contributes": "Declares the abstraction.",
            "code": None,
            "why_there_is_no_code": "This repository has changed since the review ran.",
            "note": None,
        }
    ]


def test_a_clipped_or_pinned_excerpt_carries_its_caption_into_the_request() -> None:
    """The caveats travel with the code. A clipped excerpt read as complete answers from
    the half it saw; a pinned copy read as live claims code the repository no longer says."""

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
    captioned = [
        BoundaryExcerpt(
            reference="BR-002",
            qualified_name="package.Voices",
            role="States BUILT_IN_VOICES at this location.",
            location=SourceLocation(path="preflight/voices.py", start_line=9, end_line=200),
            text="    9 | BUILT_IN_VOICES = [",
            truncated_after_line=108,
            provenance="The repository has changed since this review ran; this is the "
            "code as it was when it was reviewed.",
        )
    ]

    provider.answer_review_question(
        review(BOUNDARIES, overview=OVERVIEW),
        ReviewEvidence(case=CASE, excerpts=captioned),
        [],
        "Show me the whole voice list.",
        MethodKnowledge(method="What ArchCompass means by a boundary.", policies=[]),
    )

    sent = "\n".join(message["content"] for message in transport.messages)
    payload = json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])
    entry = next(item for item in payload["boundaries"] if item["position"] == 2)["source"][0]
    assert "changed since this review ran" in entry["note"]
    assert "only lines up to 108 are shown" in entry["note"]
    assert "runs to line 200" in entry["note"]


def test_the_first_boundary_carries_no_source_when_none_was_recorded() -> None:
    """An empty list, not a fabricated entry: nothing was read, and nothing is claimed."""

    sent, _ = _request()
    payload = json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])

    assert next(item for item in payload["boundaries"] if item["position"] == 1)["source"] == []


def _discussion(status: ReviewStatus) -> Any:
    """One discuss-stage request about a question citing only the second boundary."""

    transport = _RecordingTransport(
        json.dumps(
            {"answer": "About that.", "supported_by": [True], "suggested_answer": ""}
        )
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
    pinned = review(BOUNDARIES, overview=OVERVIEW).model_copy(update={"status": status})
    question = OpenQuestion(
        reference="Q-1",
        what_the_review_saw="Four modules state the voice list.",
        unknown="whether the lists are one concept",
        why_it_matters="If confirmed, the duplication is drift; if denied, it is benign.",
        question="Are these the same list?",
        answer_belongs_in=CaseField.CONFIRMED_FACTS,
        supporting_references=["BR-002"],
    )

    provider.discuss_open_question(
        pinned,
        ReviewEvidence(case=CASE, excerpts=EXCERPTS),
        question,
        [],
        "How do I know whether they are the same?",
        MethodKnowledge(method="What ArchCompass means by a boundary.", policies=[]),
    )

    sent = "\n".join(message["content"] for message in transport.messages)
    return json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])


def test_a_concluded_reviews_discussion_sees_the_conclusion_and_counts() -> None:
    """"How does this fit the overall recommendation?" was unanswerable: the stage also
    serves question-scoped conversations about reviews that have since concluded, and it
    had never seen the recommendation already on the reader's page."""

    payload = _discussion(ReviewStatus.SUCCEEDED)

    assert "counts" in payload
    conclusion = payload["conclusion"]
    assert conclusion["situation"] == OVERVIEW.situation
    assert conclusion["limits"] == OVERVIEW.limits
    assert [item["text"] for item in conclusion["themes"]] == [OVERVIEW.themes[0].text]


def test_conclusion_references_outside_the_cited_subset_are_named_not_numbered() -> None:
    """The subset has its own position vocabulary; a full-set position would collide with
    it and invite citing a boundary this discussion was never shown."""

    payload = _discussion(ReviewStatus.SUCCEEDED)

    # The theme rests on BR-001 and BR-002; only BR-002 is cited, and it is position 1
    # of the subset. BR-001 appears by summary, marked as outside this discussion.
    theme = payload["conclusion"]["themes"][0]
    assert theme["rests_on"] == [
        {
            "boundary_not_shown_in_this_discussion": BOUNDARIES[0].candidate.summary
        },
        {"position": 1},
    ]
    assert payload["conclusion"]["recommended_sequence"][0]["rests_on"] == [
        {"position": 1}
    ]


def test_a_superseded_discussion_sees_the_concluding_passes_conclusion() -> None:
    """A review row never changes status — the loop concludes in a new review — so the
    conclusion on the reader's page belongs to the successor. It arrives marked as the
    later pass's, with groundings matched back onto the cited subset by fingerprint and
    boundaries outside it named, not numbered."""

    transport = _RecordingTransport(
        json.dumps(
            {"answer": "About that.", "supported_by": [True], "suggested_answer": ""}
        )
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
    pinned_boundaries = [
        BOUNDARIES[0],
        BOUNDARIES[1].model_copy(update={"fingerprint": "fp-voices"}),
        BOUNDARIES[2],
    ]
    pinned = review(pinned_boundaries, overview=OVERVIEW).model_copy(
        update={"status": ReviewStatus.AWAITING_ANSWERS}
    )
    # The successor judged the same voice-list structure (same fingerprint, its own
    # reference) plus a boundary this thread was never shown.
    successor = review(
        [
            reviewed_boundary("BR-001", "Voices", material=True).model_copy(
                update={"fingerprint": "fp-voices"}
            ),
            reviewed_boundary("BR-002", "Formatter", material=False),
        ],
        overview=ReviewOverview(
            situation="The loop has concluded.",
            themes=[
                OverviewStatement(
                    text="The voice list needs one owner.",
                    supporting_references=["BR-001", "BR-002"],
                )
            ],
            limits="One detector ran.",
        ),
    )
    question = OpenQuestion(
        reference="Q-1",
        what_the_review_saw="Four modules state the voice list.",
        unknown="whether the lists are one concept",
        why_it_matters="If confirmed, the duplication is drift; if denied, it is benign.",
        question="Are these the same list?",
        answer_belongs_in=CaseField.CONFIRMED_FACTS,
        supporting_references=["BR-002"],
    )

    provider.discuss_open_question(
        pinned,
        ReviewEvidence(case=CASE, excerpts=EXCERPTS, concluded_by=successor),
        question,
        [],
        "How does this fit the overall recommendation?",
        MethodKnowledge(method="What ArchCompass means by a boundary.", policies=[]),
    )

    sent = "\n".join(message["content"] for message in transport.messages)
    payload = json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])
    conclusion = payload["conclusion"]

    assert "later pass" in conclusion["reached_by"]
    assert conclusion["situation"] == "The loop has concluded."
    assert "counts" in payload
    # The successor's first grounding resolves by fingerprint to the one shown boundary;
    # its second names a boundary this thread was never shown.
    theme = conclusion["themes"][0]
    assert theme["rests_on"][0] == {"position": 1}
    assert "boundary_not_shown_in_this_discussion" in theme["rests_on"][1]
    # And no BR- reference of either review crosses the wire.
    assert "BR-" not in sent.rsplit("\n\nInput:\n", maxsplit=1)[1]


def test_a_waiting_reviews_discussion_states_the_conclusion_is_withheld() -> None:
    """Mid-elicitation the overview summarises verdicts the reader has deliberately not
    been shown, so it stays out — as a stated absence, not a missing key."""

    payload = _discussion(ReviewStatus.AWAITING_ANSWERS)

    assert "counts" not in payload
    assert isinstance(payload["conclusion"], str)
    assert payload["conclusion"].startswith("withheld")


#: One round as the workspace really keeps it: the question pinned in the first pass, the
#: answer on the case revision that answering produced, and one the reader skipped.
ROUND = [
    AnsweredQuestion(
        question=OpenQuestion(
            reference="Q-1",
            what_the_review_saw="Four modules state the voice list, and one of them disagrees.",
            unknown="whether a second vendor is coming",
            why_it_matters="If confirmed, BR-001 is earning its place; if denied, it is not.",
            question="Is a second speech vendor expected?",
            answer_belongs_in=CaseField.EXPECTED_FUTURE_CHANGES,
            supporting_references=["BR-001"],
        ),
        answer="No. One vendor, and no plan to add another.",
    ),
    AnsweredQuestion(
        question=OpenQuestion(
            reference="Q-2",
            what_the_review_saw="The clock is read in three places.",
            unknown="whether tests need to control time",
            why_it_matters="If confirmed, BR-003 stays; if denied, it should go.",
            question="Do the tests need to freeze the clock?",
            answer_belongs_in=CaseField.ASSUMPTIONS,
            supporting_references=["BR-003"],
        ),
    ),
]


def _round_request(*, recorded: bool = True) -> dict[str, object]:
    """The same request, with the elicitation round attached."""

    transport = _RecordingTransport(
        json.dumps(
            {
                "answer": "You answered one and skipped one.",
                "supported_by": [True, False, False],
            }
        )
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
        ReviewEvidence(
            case=CASE,
            excerpts=EXCERPTS,
            elicitation=ROUND,
            answers_were_recorded=recorded,
        ),
        [],
        "What were the questions and answers again?",
        MethodKnowledge(method="Primer.", policies=[]),
    )
    sent = "\n".join(message["content"] for message in transport.messages)
    return cast(
        dict[str, object], json.loads(sent.rsplit("\n\nInput:\n", maxsplit=1)[1])
    )


def test_the_round_that_produced_this_review_reaches_the_stage() -> None:
    """The regression for "the review does not contain any record of previous questions".

    Both halves were kept and neither could be reached from the other: the questions live in
    the first pass for ever, the answers on the case revision this pass ran against, and the
    stage was handed neither. It reported an absence that was accurate about its input and
    false about the workspace.
    """

    payload = _round_request()

    assert payload["elicitation_round"] == [
        {
            "what_the_review_saw": (
                "Four modules state the voice list, and one of them disagrees."
            ),
            "question": "Is a second speech vendor expected?",
            "why_it_matters": "If confirmed, BR-001 is earning its place; if denied, it is not.",
            "answer": "No. One vendor, and no plan to add another.",
        },
        {
            "what_the_review_saw": "The clock is read in three places.",
            "question": "Do the tests need to freeze the clock?",
            "why_it_matters": "If confirmed, BR-003 stays; if denied, it should go.",
            "answer": "skipped — the reader chose not to answer this one",
        },
    ]


def test_a_skipped_question_is_told_apart_from_an_unrecorded_one() -> None:
    """Two different things to tell a reader, and an absent key would say neither.

    A revision authored by hand answers nothing per question — the lines may well say what
    the reader would have said, and nothing records which line answered what. Reporting that
    as "skipped" would accuse them of ignoring a question they may have answered.
    """

    payload = _round_request(recorded=False)
    answers = [item["answer"] for item in cast(list[dict[str, str]], payload["elicitation_round"])]

    assert answers[1].startswith("not recorded — this case revision was edited by hand")
    # The one that does have text is unaffected: a hand-edited revision cannot produce it.
    assert answers[0] == "No. One vendor, and no plan to add another."


def test_a_first_pass_says_it_asked_nothing_rather_than_showing_an_empty_list() -> None:
    """An empty array reads as "asked and got nothing back", which is a different claim."""

    payload = json.loads(_request()[0].rsplit("\n\nInput:\n", maxsplit=1)[1])

    assert isinstance(payload["elicitation_round"], str)
    assert "asked nothing" in payload["elicitation_round"]
