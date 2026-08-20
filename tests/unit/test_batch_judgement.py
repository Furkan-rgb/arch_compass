"""Judging a whole review in one submission, and refusing to compose half of one."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Participant,
    Policy,
    PolicyScope,
    PolicyStrength,
    RetrievalProvenance,
    Verdict,
)
from archcompass.domain.errors import ModelOutputValidationError, ProviderError
from archcompass.ports.capabilities import JudgementRequest
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet
from archcompass.reasoning.adapters.google_batch import BatchPolling, GoogleBatchJudge


def _request(name: str, case: ArchitectureCase) -> JudgementRequest:
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary=f"{name} is implemented once.",
        participants=(Participant(name, "interface"),),
    )
    policy = Policy(
        "policy-1",
        "A boundary owns its persistence",
        "Two boundaries sharing a mapper share a deployment.",
        PolicyScope.GENERAL,
        PolicyStrength.GUIDANCE,
        "hash-1",
    )
    provenance = RetrievalProvenance(candidate.id, "test", "1", "corpus", (policy.id,))
    policies = RetrievedPolicySet(
        str(candidate.id), (PolicySelection(policy),), provenance
    )
    return JudgementRequest(candidate=candidate, case=case, policies=policies)


def _answer(document: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(error=None, response=SimpleNamespace(text=json.dumps(document)))


@dataclass
class FakeBatches:
    """A batch service that is pending for a while and then succeeds."""

    responses: list[Any]
    pending_polls: int = 2
    state: str = "JOB_STATE_PENDING"
    created: list[dict[str, Any]] | None = None
    polls: int = 0

    def create(self, *, model: str, src: Any, config: Any) -> SimpleNamespace:
        self.created = list(src)
        del model, config
        return SimpleNamespace(name="batches/abc", state=SimpleNamespace(name=self.state))

    def get(self, *, name: str) -> SimpleNamespace:
        self.polls += 1
        if self.polls >= self.pending_polls:
            return SimpleNamespace(
                name=name,
                state=SimpleNamespace(name="JOB_STATE_SUCCEEDED"),
                dest=SimpleNamespace(inlined_responses=self.responses),
            )
        return SimpleNamespace(name=name, state=SimpleNamespace(name="JOB_STATE_RUNNING"))


def _judge(batches: FakeBatches) -> GoogleBatchJudge:
    waits: list[float] = []
    judge = GoogleBatchJudge(
        api_key="not-used",
        model="gemini-3.5-flash-lite",
        polling=BatchPolling(first_interval_seconds=1, multiplier=2, deadline_seconds=100),
        sleep=waits.append,
        client=SimpleNamespace(batches=batches),  # type: ignore[arg-type]
    )
    return judge


def test_every_candidate_is_submitted_once_and_answered_in_order() -> None:
    case = ArchitectureCase.create(goal="Keep the domain independent.")
    requests = (_request("ports.Clock", case), _request("ports.Store", case))
    batches = FakeBatches(
        responses=[
            _answer({"material": False, "reasoning": "The port is fine.", "hinge": None}),
            _answer(
                {
                    "material": True,
                    "reasoning": "The store is shared across boundaries.",
                    "policy_bearings": [{"policy_position": 1, "reasoning": "Shared mapper."}],
                    "recommended_response": "Split the mapper.",
                }
            ),
        ]
    )
    findings = _judge(batches).judge_all(requests, model_identity="google:flash-lite")

    # One submission holding both, not two submissions.
    assert batches.created is not None and len(batches.created) == 2
    # Answers are returned against the candidate that asked, in the caller's order.
    assert [finding.candidate.summary for finding in findings] == [
        item.candidate.summary for item in requests
    ]
    assert findings[0].verdict is Verdict.CLEARED
    assert findings[1].verdict is Verdict.MATERIAL
    assert findings[1].policies[0].policy.id == "policy-1"
    assert findings[1].model_identity == "google:flash-lite"


def test_a_short_batch_is_refused_rather_than_composed() -> None:
    """A missing verdict would read as a cleared one, which is the dangerous default."""

    case = ArchitectureCase.create(goal="Keep the domain independent.")
    requests = (_request("ports.Clock", case), _request("ports.Store", case))
    batches = FakeBatches(
        responses=[_answer({"material": False, "reasoning": "Only one answer."})]
    )
    with pytest.raises(ProviderError, match="1 of 2"):
        _judge(batches).judge_all(requests, model_identity="google:flash-lite")


def test_a_refused_judgement_fails_the_batch() -> None:
    case = ArchitectureCase.create(goal="Keep the domain independent.")
    requests = (_request("ports.Clock", case),)
    batches = FakeBatches(
        responses=[SimpleNamespace(error="RESOURCE_EXHAUSTED", response=None)]
    )
    with pytest.raises(ProviderError, match="refused one judgement"):
        _judge(batches).judge_all(requests, model_identity="google:flash-lite")


def test_output_that_does_not_match_the_schema_is_named_as_such() -> None:
    case = ArchitectureCase.create(goal="Keep the domain independent.")
    requests = (_request("ports.Clock", case),)
    batches = FakeBatches(responses=[_answer({"material": "yes"})])
    with pytest.raises(ModelOutputValidationError, match="did not match the required"):
        _judge(batches).judge_all(requests, model_identity="google:flash-lite")


def test_a_job_that_never_finishes_is_given_up_on() -> None:
    case = ArchitectureCase.create(goal="Keep the domain independent.")
    batches = FakeBatches(responses=[], pending_polls=10_000)
    judge = GoogleBatchJudge(
        api_key="not-used",
        model="gemini-3.5-flash-lite",
        polling=BatchPolling(first_interval_seconds=1, multiplier=1, deadline_seconds=3),
        sleep=lambda _: None,
        client=SimpleNamespace(batches=batches),  # type: ignore[arg-type]
    )
    with pytest.raises(ProviderError, match="stopped waiting"):
        judge.judge_all((_request("ports.Clock", case),), model_identity="google:x")


def test_an_empty_selection_asks_the_provider_nothing() -> None:
    batches = FakeBatches(responses=[])
    assert _judge(batches).judge_all((), model_identity="google:x") == ()
    assert batches.created is None
