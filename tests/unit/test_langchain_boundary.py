from __future__ import annotations

from typing import Any

import pytest

from archcompass.adapters.models.langchain_boundary import LangChainArchitectureJudge
from archcompass.domain.core import (
    ArchitectureCase,
    Candidate,
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
        assert "POLICIES" in prompt
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
