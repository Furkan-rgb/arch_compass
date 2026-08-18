from __future__ import annotations

from typing import Any

import pytest

from archcompass.adapters.models.langchain_boundary import (
    LangChainArchitectureJudge,
    LangChainQuestionGenerator,
)
from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Finding,
    Participant,
    Policy,
    PolicyScope,
    PolicyStrength,
    RetrievalProvenance,
    Verdict,
)
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet


class StructuredReply:
    def __init__(self, schema: type[Any], document: dict[str, object]) -> None:
        self._schema = schema
        self._document = document

    def invoke(self, prompt: str) -> object:
        assert prompt
        return self._schema.model_validate(self._document)


class StructuredModel:
    def __init__(self, document: dict[str, object]) -> None:
        self._document = document

    def with_structured_output(self, schema: type[Any]) -> StructuredReply:
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
        ArchitectureCase.create("Keep changes local"),
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

    with pytest.raises(ValueError, match="uncertainty hinge"):
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
