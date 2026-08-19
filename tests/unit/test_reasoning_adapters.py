from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

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
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet
from archcompass.reasoning.adapters.langchain import (
    LangChainArchitectureJudge,
    LangChainQuestionGenerator,
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
