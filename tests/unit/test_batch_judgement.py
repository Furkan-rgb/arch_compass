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
    case = ArchitectureCase.create()
    requests = (_request("ports.Clock", case), _request("ports.Store", case))
    batches = FakeBatches(
        responses=[
            _answer({"verdict": "cleared", "reasoning": "The port is fine.", "hinge": None}),
            _answer(
                {
                    "verdict": "material",
                    "reasoning": "The store is shared across boundaries.",
                    "policy_bearings": [{"policy_id": "policy-1", "reasoning": "Shared mapper."}],
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

    case = ArchitectureCase.create()
    requests = (_request("ports.Clock", case), _request("ports.Store", case))
    batches = FakeBatches(
        responses=[_answer({"verdict": "cleared", "reasoning": "Only one answer."})]
    )
    with pytest.raises(ProviderError, match="1 of 2"):
        _judge(batches).judge_all(requests, model_identity="google:flash-lite")


def test_a_refused_judgement_fails_the_batch() -> None:
    case = ArchitectureCase.create()
    requests = (_request("ports.Clock", case),)
    batches = FakeBatches(
        responses=[SimpleNamespace(error="RESOURCE_EXHAUSTED", response=None)]
    )
    with pytest.raises(ProviderError, match="refused one judgement"):
        _judge(batches).judge_all(requests, model_identity="google:flash-lite")


def test_output_that_does_not_match_the_schema_is_named_as_such() -> None:
    case = ArchitectureCase.create()
    requests = (_request("ports.Clock", case),)
    batches = FakeBatches(responses=[_answer({"verdict": "probably"})])
    with pytest.raises(ModelOutputValidationError, match="did not match the required"):
        _judge(batches).judge_all(requests, model_identity="google:flash-lite")


def test_a_job_that_never_finishes_is_given_up_on() -> None:
    case = ArchitectureCase.create()
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

    case = ArchitectureCase.create()
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

    case = ArchitectureCase.create()
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

        def judge_all(self, requests: Any, *, model_identity: str, observe: Any = None) -> Any:
            del requests, model_identity, observe
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

    case = ArchitectureCase.create()
    requests = (_request("ports.Clock", case), _request("ports.Store", case))

    assert judge.supports_batch() is True
    seen: list[str] = []
    judge.judge_all(requests, observe=seen.append)

    # Both candidates were judged the slow way rather than the review being lost.
    assert len(interactive) == 2
    # And the refusal was said out loud rather than only logged. `supports_batch` answered
    # true a moment ago, so anything that reported a batch on the strength of that has to
    # be told it did not happen — see `test_nothing_is_told_a_batch_is_queued_until_one_is`.
    assert seen == ["unavailable"]
    # And the key is not asked again for the life of this process.
    assert judge.supports_batch() is False


def test_a_batched_judgement_thinks_as_hard_as_an_interactive_one() -> None:
    """The batch builds its own request, so it has to be told the depth separately.

    A review submitted as a batch is not allowed to be a different review. This path never
    goes through LangChain — it assembles `GenerateContentConfig` itself — so a thinking
    level wired only into the interactive factory would leave every batched run on the
    model's default while the picker said otherwise.
    """

    case = ArchitectureCase.create()
    requests = (_request("ports.Clock", case),)
    batches = FakeBatches(
        responses=[_answer({"verdict": "cleared", "reasoning": "The port is fine."})]
    )
    judge = GoogleBatchJudge(
        api_key="not-used",
        model="gemini-3.5-flash-lite",
        thinking="medium",
        polling=BatchPolling(first_interval_seconds=1, multiplier=2, deadline_seconds=100),
        sleep=lambda _: None,
        client=SimpleNamespace(batches=batches),  # type: ignore[arg-type]
    )

    judge.judge_all(requests, model_identity="google:flash-lite")

    assert batches.created is not None
    thinking = batches.created[0].config.thinking_config
    assert thinking is not None and thinking.thinking_level.name == "MEDIUM"


def test_a_batch_that_was_told_no_depth_asks_for_none() -> None:
    """An unasked-for level is absent, not a default of ours written into the request."""

    case = ArchitectureCase.create()
    batches = FakeBatches(
        responses=[_answer({"verdict": "cleared", "reasoning": "The port is fine."})]
    )
    _judge(batches).judge_all(
        (_request("ports.Clock", case),), model_identity="google:flash-lite"
    )

    assert batches.created is not None
    assert batches.created[0].config.thinking_config is None


def test_nothing_is_told_a_batch_is_queued_until_the_provider_has_taken_one() -> None:
    """The order that makes the run's notice honest: submission first, claim second.

    `supports_batch` is a prediction. It is true for any Google key with batching switched
    on, and the provider is the only thing that knows whether the project behind that key is
    eligible — it says so by accepting the submission or answering `400 FAILED_PRECONDITION`.
    Reporting a queued batch from the routing decision instead meant a run whose key was
    refused told its reader, for the whole of the interactive fallback, that every candidate
    had gone to the provider in one batch at half price, guaranteed within a day.

    So this asserts the sequencing rather than the value: `queued` is emitted after the
    submission is accepted and before the wait for it begins.
    """

    case = ArchitectureCase.create()
    requests = (_request("ports.Clock", case), _request("ports.Store", case))
    batches = FakeBatches(
        [_answer({"verdict": "cleared", "reasoning": "fine", "policy_bearings": []})] * 2
    )
    order: list[str] = []
    original_create = batches.create

    def create(**kwargs: Any) -> Any:
        order.append("submitted")
        return original_create(**kwargs)

    batches.create = create  # type: ignore[method-assign]
    original_get = batches.get

    def get(**kwargs: Any) -> Any:
        order.append("polled")
        return original_get(**kwargs)

    batches.get = get  # type: ignore[method-assign]

    _judge(batches).judge_all(
        requests,
        model_identity="google:gemini-3.5-flash-lite",
        observe=lambda outcome: order.append(outcome),
    )

    assert order[:2] == ["submitted", "queued"]
    assert "queued" not in order[2:]


def test_a_refused_key_is_still_refused_after_a_restart(tmp_path: Any) -> None:
    """A project that cannot batch today cannot batch because the process restarted.

    The refusal used to live on the judge instance, so every session paid one rejected
    submission to learn it again — and every session's first review was routed to the batch
    node and told its reader a batch had been queued. Written down, the second judge never
    asks at all.
    """

    import sqlite3

    from archcompass.persistence.model_selection import SQLiteBatchRefusalRepository

    database = tmp_path / "workspace.db"

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        return connection

    refusals = SQLiteBatchRefusalRepository(connect)
    assert refusals.refused("a-key") is False

    refusals.record("a-key")

    # A second process, reading the same workspace.
    assert SQLiteBatchRefusalRepository(connect).refused("a-key") is True
    # A different key is on a different project, and gets its own answer.
    assert refusals.refused("another-key") is False
    # And the credential itself is not what was written down.
    with connect() as connection:
        stored = [row[0] for row in connection.execute("SELECT key_fingerprint FROM batch_refusal")]
    assert stored and "a-key" not in stored


def test_a_workspace_that_has_been_refused_never_routes_to_a_batch_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The half of the fix the reader actually sees: the notice stops appearing.

    `supports_batch` is what the graph routes on, so a workspace whose key the Batch API has
    already turned away must answer false before it submits anything. Otherwise the first
    review of every session enters the batch node, announces a queued batch, and falls back.
    """

    from archcompass.configuration import ReasoningModelConfig
    from archcompass.reasoning.adapters import selected as selected_module
    from archcompass.reasoning.refusals import InMemoryBatchRefusals

    monkeypatch.setenv("GOOGLE_API_KEY", "a-refused-key")

    class Selection:
        def current(self) -> ReasoningModelConfig:
            return ReasoningModelConfig(
                provider="google",
                model="gemini-3.5-flash-lite",
                api_key_env="GOOGLE_API_KEY",
                timeout_seconds=30,
            )

    refusals = InMemoryBatchRefusals()
    judge = selected_module.SelectedLangChainJudge(
        selected_module.SelectedLangChainChatModel(Selection()),  # type: ignore[arg-type]
        refusals,
    )
    assert judge.supports_batch() is True

    refusals.record("a-refused-key")

    # A fresh judge, as a restart would build: no submission, and no route to the batch node.
    assert (
        selected_module.SelectedLangChainJudge(
            selected_module.SelectedLangChainChatModel(Selection()),  # type: ignore[arg-type]
            refusals,
        ).supports_batch()
        is False
    )

    # A key on a project that is eligible is not punished for another key's refusal.
    monkeypatch.setenv("GOOGLE_API_KEY", "a-different-key")
    assert (
        selected_module.SelectedLangChainJudge(
            selected_module.SelectedLangChainChatModel(Selection()),  # type: ignore[arg-type]
            refusals,
        ).supports_batch()
        is True
    )


def test_a_refusal_stops_holding_once_it_is_old_enough(tmp_path) -> None:
    """A stale refusal stops matching on its own, which is the whole recovery path.

    Eligibility is a property of the project and a project can gain it — somebody enables
    billing — and no event carrying that reaches this process. The row used to be read as
    permanent, `refused_at` written and never looked at, so the workspace judged every
    review interactively for ever and the only way back was SQL by hand.

    The interval is an operational choice and not the point; that a refusal expires at all
    is the point. Asserted by writing the timestamp rather than by waiting a week.
    """

    import sqlite3
    from datetime import timedelta

    from archcompass.persistence.model_selection import (
        _REFUSAL_HOLDS_FOR,
        SQLiteBatchRefusalRepository,
    )
    from archcompass.records import utc_now

    database = tmp_path / "workspace.db"

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        return connection

    def age(key_fingerprint_of: str, *, by: timedelta) -> None:
        from archcompass.reasoning.refusals import fingerprint_key

        with connect() as connection:
            connection.execute(
                "UPDATE batch_refusal SET refused_at = ? WHERE key_fingerprint = ?",
                ((utc_now() - by).isoformat(), fingerprint_key(key_fingerprint_of)),
            )

    refusals = SQLiteBatchRefusalRepository(connect)
    refusals.record("a-key")
    assert refusals.refused("a-key") is True

    age("a-key", by=_REFUSAL_HOLDS_FOR + timedelta(hours=1))
    assert refusals.refused("a-key") is False, "a stale refusal is still being obeyed"

    # Refused again today, and the observation is today's rather than the first one's.
    refusals.record("a-key")
    assert refusals.refused("a-key") is True

    # One row per credential: the refresh replaced it rather than adding to it.
    with connect() as connection:
        rows = connection.execute("SELECT COUNT(*) FROM batch_refusal").fetchone()[0]
    assert rows == 1


def test_one_key_expiring_says_nothing_about_another(tmp_path) -> None:
    """Two credentials are two projects, and one recovering does not speak for the other."""

    import sqlite3
    from datetime import timedelta

    from archcompass.persistence.model_selection import (
        _REFUSAL_HOLDS_FOR,
        SQLiteBatchRefusalRepository,
    )
    from archcompass.reasoning.refusals import fingerprint_key
    from archcompass.records import utc_now

    database = tmp_path / "workspace.db"

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        return connection

    refusals = SQLiteBatchRefusalRepository(connect)
    refusals.record("stale-key")
    refusals.record("fresh-key")
    with connect() as connection:
        connection.execute(
            "UPDATE batch_refusal SET refused_at = ? WHERE key_fingerprint = ?",
            (
                (utc_now() - _REFUSAL_HOLDS_FOR - timedelta(hours=1)).isoformat(),
                fingerprint_key("stale-key"),
            ),
        )

    assert refusals.refused("stale-key") is False
    assert refusals.refused("fresh-key") is True
    # Neither credential is recoverable from what was written down.
    with connect() as connection:
        stored = [
            row[0] for row in connection.execute("SELECT key_fingerprint FROM batch_refusal")
        ]
    assert len(stored) == 2
    assert not any(key in stored for key in ("stale-key", "fresh-key"))
