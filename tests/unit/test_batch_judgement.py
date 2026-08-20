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
from archcompass.reasoning.adapters.google_batch import (
    BatchPolling,
    BatchUnavailableError,
    GoogleBatchEmbeddings,
    GoogleBatchJudge,
)


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


# ── embedding the corpus ──────────────────────────────────────────────────────────────────


@dataclass
class FakeEmbeddingBatches:
    """The embeddings half of the batch service, which answers with vectors."""

    vectors: list[list[float]]
    submitted: Any = None
    polls: int = 0

    def create_embeddings(self, *, model: str, src: Any, config: Any) -> SimpleNamespace:
        del model, config
        self.submitted = src
        return SimpleNamespace(name="batches/emb", state=SimpleNamespace(name="JOB_STATE_PENDING"))

    def get(self, *, name: str) -> SimpleNamespace:
        self.polls += 1
        return SimpleNamespace(
            name=name,
            state=SimpleNamespace(name="JOB_STATE_SUCCEEDED"),
            dest=SimpleNamespace(
                inlined_embed_content_responses=[
                    SimpleNamespace(
                        error=None,
                        response=SimpleNamespace(embedding=SimpleNamespace(values=vector)),
                    )
                    for vector in self.vectors
                ]
            ),
        )


def _embeddings(batches: FakeEmbeddingBatches) -> GoogleBatchEmbeddings:
    return GoogleBatchEmbeddings(
        api_key="not-used",
        model="gemini-embedding-2",
        dimensions=3,
        polling=BatchPolling(first_interval_seconds=1, multiplier=1, deadline_seconds=60),
        sleep=lambda _: None,
        client=SimpleNamespace(batches=batches),  # type: ignore[arg-type]
    )


def test_the_whole_corpus_is_submitted_as_one_batch() -> None:
    batches = FakeEmbeddingBatches(vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    vectors = _embeddings(batches).embed_documents_batched(["first chunk", "second chunk"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    # One submission holding both chunks, not one submission per chunk.
    assert len(batches.submitted.inlined_requests.contents) == 2


def test_a_short_embedding_batch_is_refused() -> None:
    """A chunk with no vector is a policy that can never be retrieved."""

    batches = FakeEmbeddingBatches(vectors=[[1.0, 0.0, 0.0]])
    with pytest.raises(ProviderError, match="1 of 2"):
        _embeddings(batches).embed_documents_batched(["first chunk", "second chunk"])


def test_an_empty_corpus_asks_the_provider_nothing() -> None:
    batches = FakeEmbeddingBatches(vectors=[])
    assert _embeddings(batches).embed_documents_batched([]) == []
    assert batches.submitted is None


# ── a key the Batch API will not take ─────────────────────────────────────────────────────


class Refused(Exception):
    """What the API answers a key without billing: a status, and nothing to act on."""

    def __init__(self) -> None:
        super().__init__(
            "400 FAILED_PRECONDITION. {'error': {'code': 400, 'message': "
            "'Precondition check failed.', 'status': 'FAILED_PRECONDITION'}}"
        )
        self.code = 400


@dataclass
class RefusingBatches:
    def create(self, *, model: str, src: Any, config: Any) -> SimpleNamespace:
        del model, src, config
        raise Refused()

    def create_embeddings(self, *, model: str, src: Any, config: Any) -> SimpleNamespace:
        del model, src, config
        raise Refused()


def test_a_refused_batch_says_what_to_do_about_it() -> None:
    """`Precondition check failed.` on its own is a useless thing to fail a review with."""

    case = ArchitectureCase.create(goal="Keep the domain independent.")
    judge = GoogleBatchJudge(
        api_key="not-used",
        model="gemini-3.5-flash-lite",
        sleep=lambda _: None,
        client=SimpleNamespace(batches=RefusingBatches()),  # type: ignore[arg-type]
    )
    with pytest.raises(BatchUnavailableError) as refusal:
        judge.judge_all((_request("ports.Clock", case),), model_identity="google:x")

    message = str(refusal.value)
    assert "billing enabled" in message
    assert "ARCHCOMPASS_GOOGLE_BATCH=0" in message
    # And it keeps what the provider actually said, for anyone who needs to quote it.
    assert "FAILED_PRECONDITION" in message


def test_an_ordinary_failure_is_not_dressed_up_as_a_missing_facility() -> None:
    class Broken:
        def create(self, *, model: str, src: Any, config: Any) -> SimpleNamespace:
            del model, src, config
            raise ValueError("the prompt was too long")

    case = ArchitectureCase.create(goal="Keep the domain independent.")
    judge = GoogleBatchJudge(
        api_key="not-used",
        model="gemini-3.5-flash-lite",
        sleep=lambda _: None,
        client=SimpleNamespace(batches=Broken()),  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="prompt was too long"):
        judge.judge_all((_request("ports.Clock", case),), model_identity="google:x")


def test_a_refused_embedding_batch_is_named_the_same_way() -> None:
    embeddings = GoogleBatchEmbeddings(
        api_key="not-used",
        model="gemini-embedding-2",
        dimensions=3,
        sleep=lambda _: None,
        client=SimpleNamespace(batches=RefusingBatches()),  # type: ignore[arg-type]
    )
    with pytest.raises(BatchUnavailableError, match="billing enabled"):
        embeddings.embed_documents_batched(["a chunk"])


def test_a_refused_batch_degrades_to_judging_one_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Losing a review the interactive path could have produced is the worse outcome."""

    from archcompass.configuration import ReasoningModelConfig
    from archcompass.reasoning.adapters import selected as selected_module

    monkeypatch.setenv("GOOGLE_API_KEY", "not-a-real-key")

    class Selection:
        def current(self) -> ReasoningModelConfig:
            return ReasoningModelConfig(
                provider="google",
                model="gemini-3.5-flash-lite",
                api_key_env="GOOGLE_API_KEY",
                timeout_seconds=30,
            )

    class RefusingJudge:
        def __init__(self, **_: Any) -> None:
            pass

        def judge_all(self, requests: Any, *, model_identity: str) -> Any:
            del requests, model_identity
            raise BatchUnavailableError("no batch for this key")

    monkeypatch.setattr(selected_module, "GoogleBatchJudge", RefusingJudge)

    judge = selected_module.SelectedLangChainJudge(
        selected_module.SelectedLangChainChatModel(Selection())  # type: ignore[arg-type]
    )
    interactive: list[str] = []
    monkeypatch.setattr(
        judge,
        "judge",
        lambda candidate, case, policies: interactive.append(candidate.summary) or None,
    )

    case = ArchitectureCase.create(goal="Keep the domain independent.")
    requests = (_request("ports.Clock", case), _request("ports.Store", case))

    assert judge.supports_batch() is True
    judge.judge_all(requests)

    # Both candidates were judged the slow way rather than the review being lost.
    assert len(interactive) == 2
    # And the key is not asked again for the life of this process.
    assert judge.supports_batch() is False
