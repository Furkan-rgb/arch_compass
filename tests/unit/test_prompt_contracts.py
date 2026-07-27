"""The two stages that remain, and the contracts that make them checkable."""

from __future__ import annotations

from dataclasses import replace

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.adapters.models.prompt_contracts import (
    ANSWER_REVIEW_QUESTION,
    JUDGE_FINDING_CANDIDATE,
    STAGE_PROMPTS,
    SUMMARISE_REVIEW,
)
from archcompass.domain.base import canonical_json
from archcompass.ports.reasoning import ReasoningTask


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def test_canonical_json_uses_one_serializer_for_models_and_mappings() -> None:
    payload = {"case_id": "case-test", "revision": 1}

    assert canonical_json(payload) == canonical_json(dict(payload))
    assert "'case_id': 'case-test'" not in canonical_json({"outer": payload})


def test_every_reasoning_task_has_a_contract_and_every_contract_a_task() -> None:
    """The enum and the registry must not drift; a gap surfaces as a runtime KeyError."""

    expected_versions = {
        ReasoningTask.JUDGE_FINDING_CANDIDATE: 5,
        ReasoningTask.SUMMARISE_REVIEW: 4,
        ReasoningTask.ANSWER_REVIEW_QUESTION: 4,
    }

    assert set(STAGE_PROMPTS) == set(ReasoningTask)
    assert set(STAGE_PROMPTS) == set(expected_versions)
    identities = []
    for task, version in expected_versions.items():
        contract = STAGE_PROMPTS[task]
        assert contract.identity.startswith(f"{contract.name}:v{version}:")
        assert len(contract.content_fingerprint) == 12
        identities.append(contract.identity)
    assert len(identities) == len(set(identities))


def test_a_changed_prompt_changes_its_identity_without_a_version_bump() -> None:
    """Otherwise an audit trail names a prompt that was not the one actually run."""

    changed = replace(
        JUDGE_FINDING_CANDIDATE,
        request=JUDGE_FINDING_CANDIDATE.request + " Materially changed.",
    )

    assert changed.version == JUDGE_FINDING_CANDIDATE.version
    assert changed.identity != JUDGE_FINDING_CANDIDATE.identity


def test_the_shared_contract_still_carries_the_evidence_rules() -> None:
    shared = _normalized(JUDGE_FINDING_CANDIDATE.system_prompt)

    assert "evidence hierarchy" in shared
    assert "absence of evidence is not evidence of absence" in shared
    assert "minimum architecture" in shared


def test_the_judgement_contract_treats_both_errors_as_errors() -> None:
    """A stage that names one verdict as the default gets that verdict.

    Measured rather than assumed: while the contract said "not material is the ordinary
    answer", every error across four fixture runs was a false clear and none was a false
    condemn.
    """

    contract = _normalized(JUDGE_FINDING_CANDIDATE.stage_contract)

    assert "two errors are equally wrong" in contract
    assert "neither verdict is the safe one" in contract
    assert "condemning a shape that is earning what it costs" in contract
    assert "clearing one that is not" in contract
    assert "clearing reads as approval" in contract


def test_the_judgement_request_puts_the_argument_before_the_verdict() -> None:
    """Field order is the reasoning order; the request must not contradict the schema."""

    request = _normalized(JUDGE_FINDING_CANDIDATE.request)

    assert "answer the fields in the order they appear" in request
    assert request.index("first, in rationale") < request.index("only then set verdict")
    assert "never write a policy's name, number or identifier" in request


def test_the_answer_contract_forbids_writing_a_reference_code() -> None:
    """Grounding is positional; a code in model text would be a key the model authored."""

    request = _normalized(ANSWER_REVIEW_QUESTION.request)

    assert "never write a br- code" in request
    assert "in the order the boundaries were supplied" in request


def test_the_answer_contract_says_what_the_conclusion_is_and_is_not() -> None:
    """It is shown so a reader's question is answerable, not as a second source of fact.

    The conclusion is composed from the same verdicts, so a stage that read it as evidence
    could ground an answer in a synthesis of the thing it was meant to be citing.
    """

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)

    assert "adds no fact about the repository" in contract
    assert "cite boundaries, never the conclusion" in contract
    assert "the boundaries are what happened" in contract


def test_the_answer_contract_sends_a_question_to_the_boundary_it_is_about() -> None:
    """v3 said what to cite and nothing about what to read, and got the difference.

    Shown the conclusion, a live conversation answered three escalating "why"s out of it —
    each turn longer, none carrying a measurement, a policy or the case — and said so in as
    many words while citing a boundary whose record it had never opened. Naming the
    conclusion an index is the half of the fix that lives in the contract; the positions it
    now carries are the half that lives in the payload.
    """

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)
    request = _normalized(ANSWER_REVIEW_QUESTION.request)

    assert "an index, not a source" in contract
    assert "positions of the boundaries it was built from" in contract
    assert "never write that something is so according to the conclusion" in contract
    # Saying less than the record holds is a failure too, which v3 never said anywhere.
    assert 'restating the verdict is not an answer to "why"' in request


def test_the_answer_contract_reports_a_verdict_at_odds_with_its_reasoning() -> None:
    """Resolving it silently is what produced a fabricated rationale.

    Asked why a boundary was condemned when its stored reasoning argued the opposite, the
    stage invented a reason that fit the verdict and stated it as the review's finding.
    Nothing had told it the two could disagree, so there was no sanctioned answer but to
    make them agree.
    """

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)

    assert "reasoning and its verdict can disagree" in contract
    assert "that contradiction is the answer" in contract


def test_the_judgement_request_names_which_word_means_which_verdict() -> None:
    """The polarity has to be stated where the choice is made, not only downstream.

    It was already spelled out in three consuming places — the answer stage, the summary
    stage and the report headline — and in none of them could it prevent the flag being
    recorded backwards in the first place.
    """

    request = _normalized(JUDGE_FINDING_CANDIDATE.request)

    assert "should_change when that argument concluded the pattern is a problem" in request
    assert "leave_as_is when it concluded the shape is earning what it costs" in request
    assert "read your own rationale back before you choose" in request
    # The exact sentence one live run wrote into `recommended_response` beside "should change".
    assert "the current abstraction is appropriate" in request


def test_the_summary_contract_separates_prose_fields_from_grounded_ones() -> None:
    """v3 said "every statement carries one supported_by flag", of four fields.

    Two of those fields are prose, and one of them — `situation` — reads exactly like a
    statement, so a live run wrote `{"statement": ..., "supported_by": [...]}` into it as
    text. The contract now names which fields carry grounding and which are sentences.
    """

    request = _normalized(SUMMARISE_REVIEW.request)

    assert "situation and limits are prose" in request
    assert "never write an object or a list into either of them" in request
    assert "every entry in those two lists — and nothing else in the reply —" in request


def test_the_substitute_names_the_same_prompts_as_the_real_registry() -> None:
    """A stage the substitute cannot identify is one the test suite never really ran."""

    substitute = DeterministicReasoningProvider()

    for task in ReasoningTask:
        assert substitute.prompt_identity(task)
