from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Evidence,
    Finding,
    Participant,
    Policy,
    PolicyBearing,
    PolicyScope,
    PolicyStrength,
    RepositoryAtlas,
    RepositoryRef,
    RetrievalProvenance,
    Review,
    ReviewDelta,
    ReviewStatus,
    SourceLocation,
    Verdict,
)
from archcompass.domain._support import utc_now
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet
from archcompass.reasoning.adapters.langchain import (
    CONVERSATION_CONTRACT,
    LangChainArchitectureJudge,
    LangChainQuestionGenerator,
    LangChainReviewAnswerer,
    conversation_prompt,
)


class StructuredReply:
    """What `with_structured_output(..., include_raw=True)` actually answers with.

    A mapping of `parsed`, `raw` and `parsing_error` — never the schema, and never an
    exception. A double that returned the validated model instead would let the adapter cast
    the result straight to its schema and still pass here, which is the bug that reached a
    real provider once already.
    """

    def __init__(self, schema: type[Any], document: dict[str, object]) -> None:
        self._schema = schema
        self._document = document

    def invoke(self, prompt: str) -> dict[str, object]:
        assert prompt
        raw = SimpleNamespace(content=json.dumps(self._document))
        try:
            parsed = self._schema.model_validate(self._document)
        except ValidationError as error:
            return {"raw": raw, "parsed": None, "parsing_error": error}
        return {"raw": raw, "parsed": parsed, "parsing_error": None}


class StructuredModel:
    def __init__(self, document: dict[str, object]) -> None:
        self._document = document

    def with_structured_output(
        self, schema: type[Any], method: str = "json_schema", *, include_raw: bool = False
    ) -> StructuredReply:
        assert method == "json_schema"
        assert include_raw, "the adapter needs the raw response to explain a refusal"
        return StructuredReply(schema, self._document)


def _input() -> tuple[Candidate, ArchitectureCase, RetrievedPolicySet]:
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    policy = Policy(
        "policy-a",
        "Delay abstraction",
        "Keep a boundary only when it hides meaningful variation.",
        PolicyScope.GENERAL,
        PolicyStrength.GUIDANCE,
        "hash-a",
    )
    provenance = RetrievalProvenance(
        candidate.id, "test", "1", "corpus", (policy.id,)
    )
    return (
        candidate,
        ArchitectureCase.create(),
        RetrievedPolicySet(
            str(candidate.id), (PolicySelection(policy),), provenance
        ),
    )


def test_model_policy_positions_are_resolved_before_finding_construction() -> None:
    candidate, case, policies = _input()
    judge = LangChainArchitectureJudge(
        StructuredModel(
            {
                "material": True,
                "reasoning": "The port hides no expected variation.",
                "policy_bearings": [
                    {"policy_position": 1, "reasoning": "This policy bears directly."}
                ],
                "recommended_response": "Remove the pass-through port.",
            }
        ),  # type: ignore[arg-type]
        model_identity="test:model",
    )

    finding = judge.judge(candidate, case, policies)

    assert finding.verdict is Verdict.MATERIAL
    assert finding.policies[0].policy is policies.policies[0]
    assert finding.retrieval_identity == policies.provenance.identity


def test_unknown_model_policy_position_is_rejected() -> None:
    candidate, case, policies = _input()
    judge = LangChainArchitectureJudge(
        StructuredModel(
            {
                "material": False,
                "reasoning": "No conflict.",
                "policy_bearings": [
                    {"policy_position": 2, "reasoning": "Unknown policy."}
                ],
            }
        ),  # type: ignore[arg-type]
        model_identity="test:model",
    )

    with pytest.raises(ValueError, match="only 1 policies"):
        judge.judge(candidate, case, policies)


def test_hinge_and_recommendation_are_rejected_at_structured_boundary() -> None:
    candidate, case, policies = _input()
    judge = LangChainArchitectureJudge(
        StructuredModel(
            {
                "material": True,
                "reasoning": "Ownership could change the verdict.",
                "hinge": "the owning team",
                "recommended_response": "Move the module.",
            }
        ),  # type: ignore[arg-type]
        model_identity="test:model",
    )

    # The schema rejects the pairing, and `include_raw=True` turns that rejection into a
    # `parsing_error` rather than a raise — so what reaches the caller is ArchCompass's
    # own error naming the model, not a Pydantic traceback from inside the runnable.
    with pytest.raises(ModelOutputValidationError, match="test:model"):
        judge.judge(candidate, case, policies)


def test_question_position_without_a_hinge_is_structurally_rejected() -> None:
    candidate, case, _ = _input()
    settled = Finding(candidate, Verdict.CLEARED, "No conflict.", (), ())
    uncertain_candidate = Candidate.identified(
        pattern="dependency_direction",
        summary="Ownership is unclear",
        participants=(Participant("domain.order", "source"),),
    )
    uncertain = Finding(
        uncertain_candidate,
        Verdict.HELD,
        "Ownership could change the verdict.",
        (),
        (),
        hinge="the owning team",
    )
    generator = LangChainQuestionGenerator(
        StructuredModel(
            {
                "questions": [
                    {
                        "text": "Who owns this?",
                        "facet": "decision",
                        "candidate_positions": [1],
                    }
                ]
            }
        )  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="finding without a hinge"):
        generator.generate(
            case,
            (settled, uncertain),
            round=1,
            excluded_equivalence_keys=frozenset(),
        )


def test_proposed_answers_survive_but_escape_hatches_do_not() -> None:
    """The interface already offers writing your own answer and skipping the question.

    A model that proposes "Other" is spending one of a handful of choices on something the
    reviewer has anyway, so it is dropped here rather than shown twice.
    """

    candidate, case, _ = _input()
    uncertain = Finding(
        candidate,
        Verdict.HELD,
        "Ownership could change the verdict.",
        (),
        (),
        hinge="the owning team",
    )
    generator = LangChainQuestionGenerator(
        StructuredModel(
            {
                "questions": [
                    {
                        "text": "Who owns this?",
                        "facet": "decision",
                        "candidate_positions": [1],
                        "options": [
                            "The domain team owns it",
                            "The platform team owns it",
                            "Other",
                            "Not sure",
                        ],
                    }
                ]
            }
        )  # type: ignore[arg-type]
    )

    questions = generator.generate(
        case, (uncertain,), round=1, excluded_equivalence_keys=frozenset()
    )

    assert questions[0].options == (
        "The domain team owns it",
        "The platform team owns it",
    )


def test_a_choice_of_one_is_not_offered_as_a_choice() -> None:
    candidate, case, _ = _input()
    uncertain = Finding(
        candidate,
        Verdict.HELD,
        "Ownership could change the verdict.",
        (),
        (),
        hinge="the owning team",
    )
    generator = LangChainQuestionGenerator(
        StructuredModel(
            {
                "questions": [
                    {
                        "text": "Who owns this?",
                        "facet": "decision",
                        "candidate_positions": [1],
                        "options": ["The domain team owns it", "None of these"],
                    }
                ]
            }
        )  # type: ignore[arg-type]
    )

    questions = generator.generate(
        case, (uncertain,), round=1, excluded_equivalence_keys=frozenset()
    )

    assert questions[0].options == ()


def _answered_review(tmp_path: Path) -> Review:
    """A review whose material finding already says what to do about it."""

    candidate = Candidate.identified(
        pattern="leaky_abstraction",
        summary="Provider named outside its boundary",
        participants=(Participant("audiobook.synthesis.providers.qwen", "adapter"),),
        evidence=(
            Evidence(
                "'qwen' is named in 5 modules outside its package",
                SourceLocation("src/audiobook/synthesis/pipeline.py", 42, 48),
            ),
        ),
    )
    policy = Policy(
        "policy-a",
        "Keep a provider behind its port",
        "An implementation name outside its package is a boundary that is not holding.",
        PolicyScope.GENERAL,
        PolicyStrength.REQUIRED,
        "hash-a",
    )
    finding = Finding(
        candidate,
        Verdict.MATERIAL,
        "Five modules reach past the port.",
        (PolicyBearing(policy, "The port is named around, not through."),),
        (),
        recommended_response="Resolve the provider through a factory at composition time.",
    )
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    now = utc_now()
    return Review(
        "review-1",
        1,
        repository,
        RepositoryAtlas("atlas", repository),
        ArchitectureCase.create(),
        (finding,),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
    )


def test_a_conversation_is_shown_what_the_review_says_to_do(tmp_path: Path) -> None:
    # "How would it be fixed?" was answered with "the review does not contain any
    # information on how to fix the identified issues" while the finding it was about
    # carried a recommended response the prompt never included. What a fix has to respect —
    # the policy wording — and where the evidence sits were missing for the same reason.
    prompt = conversation_prompt(_answered_review(tmp_path), (), "How would it be fixed?")

    assert "Resolve the provider through a factory at composition time." in prompt
    assert "An implementation name outside its package" in prompt
    assert "src/audiobook/synthesis/pipeline.py:42-48" in prompt


def test_a_conversation_may_reason_past_what_the_review_records() -> None:
    # Asking what to do about a finding is not a question the review is missing the facts
    # for; it is the question the reader came with. The contract has to permit an answer
    # and still pin every fact in it to the review.
    assert "how a finding would be fixed" in CONVERSATION_CONTRACT
    assert "Facts about this codebase come only from the review." in CONVERSATION_CONTRACT


def test_a_cited_finding_is_returned_as_the_candidate_it_belongs_to(tmp_path: Path) -> None:
    review = _answered_review(tmp_path)
    answerer = LangChainReviewAnswerer(
        StructuredModel(
            {
                "answer": "Resolve it through a factory; the review recommends as much.",
                "candidate_positions": [1],
            }
        )  # type: ignore[arg-type]
    )

    answer = answerer.answer(review, (), "How would it be fixed?")

    assert answer.supporting_candidate_ids == (str(review.findings[0].candidate.id),)
