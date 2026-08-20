"""One real review, run once, so every test below reads from the same spend.

Two live services, and the split is deliberate. Judgement, question generation and the
grounded follow-up go to Google, because that is the path being verified: a real model
returning structured output that ArchCompass then refuses to take identity from. Embedding
goes to a local Ollama model, because it cannot go to Google — the free tier allows 100
*embedded texts* a minute, the shipped corpus chunks into 486 of them, and every candidate
in the fan-out synchronizes the index before it queries. Retrieval would exhaust the minute
before the first verdict. Running the two on different providers is also the sharper test of
an invariant this product actually holds: embedding selection is independent of reasoning
selection, and here they are not even the same vendor.

The tests are marked `google` and are therefore deselected by `make test`; `make test-google`
is what runs them. They are deliberately *not* marked `ollama`, so that `make test-ollama` —
a check on somebody's local models — does not quietly spend Google quota. A missing Ollama
skips with a message instead.

The lifecycle runs in a module-scoped fixture rather than per test because it is the
expensive part: five candidates judged twice, questions asked twice, one conversation. Buying
that once per assertion would put the file out of reach of the tier it is written for.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.presentation.web.app import create_app
from archcompass.reasoning.adapters.providers import (
    GOOGLE_DESCRIPTOR,
    OLLAMA_DESCRIPTOR,
)

#: The cheapest Google model this build offers. Named here rather than left to whatever the
#: workspace would default to, so a change of default cannot quietly move these onto a model
#: somebody has to pay for.
REASONING_MODEL = "gemini-3.5-flash-lite"

#: The local embedding model, and the dimensions it reports. Both are asserted against the
#: provider's own catalogue before anything runs, so a workspace without it is told which
#: model to pull rather than failing somewhere inside a review.
EMBEDDING_PROVIDER = "ollama"
EMBEDDING_MODEL = "embeddinggemma:latest"
EMBEDDING_DIMENSIONS = 768

#: Small on purpose. Five detected candidates is enough for fan-out, for rejudgement, and for
#: a retrieval manifest with more than one entry in it, and few enough that a whole lifecycle
#: fits inside the free tier's reasoning quota.
SUBJECT_REPOSITORY = Path("examples/cases/warehouse-sync/repository")


@dataclass(frozen=True)
class Lifecycle:
    """Every response one review produced, captured once and asserted on many times.

    `resumed` is `None` when the first pass completed outright. That is a legitimate outcome
    and not a flaky one: a review waits for answers only when the model states a hinge on at
    least one finding, and whether it needs human context to judge this repository is its
    call, not the test's. The clarification assertions skip themselves in that case and say
    why, rather than being written to always pass.
    """

    started: dict[str, Any]
    first: dict[str, Any]
    resumed: dict[str, Any] | None
    final: dict[str, Any]
    decision: dict[str, Any]
    conversation: dict[str, Any]
    corpus_policy_ids: frozenset[str]
    repository_root: str


def _require_google() -> None:
    """Skip rather than fail when this machine has no quota to spend.

    Constructing the provider is what fails when a key is missing or refused, so the probe is
    the honest check: it answers unavailable for an absent key, a refused project and an
    unreachable network alike, and its detail is what a reader needs to see.
    """

    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        pytest.skip("GOOGLE_API_KEY is not set; there is nothing to run these against")
    probe = GOOGLE_DESCRIPTOR.probe(GOOGLE_DESCRIPTOR.defaults)
    if not probe.available:
        pytest.skip(f"Google is not reachable with this key: {probe.detail}")
    offered = {model.name for model in probe.models}
    if REASONING_MODEL not in offered:
        pytest.skip(f"this key does not reach {REASONING_MODEL}; it has {sorted(offered)}")


def _require_local_embeddings(runtime: Runtime) -> None:
    """Asked of the discovery service, not of Ollama directly.

    Which is the point: if the workspace's own catalogue cannot see the model, neither can a
    reviewer choosing one in the interface, and a test that reached past it would pass on a
    machine where the product does not work.
    """

    probe = OLLAMA_DESCRIPTOR.probe(OLLAMA_DESCRIPTOR.defaults)
    if not probe.available and "none of the supported" not in (probe.detail or ""):
        pytest.skip(f"Ollama is not running: {probe.detail}")
    offered = {
        (candidate.provider, candidate.model, candidate.dimensions)
        for candidate in runtime.embedding_model_service.catalog().candidates
    }
    if (EMBEDDING_PROVIDER, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS) not in offered:
        pytest.skip(
            f"{EMBEDDING_MODEL} is not an available embedding model "
            f"(`ollama pull {EMBEDDING_MODEL.removesuffix(':latest')}`); "
            f"this workspace offers {sorted(offered)}"
        )


def _run_lifecycle(runtime: Runtime, repository: str) -> Lifecycle:
    corpus = frozenset(
        policy.id
        for policy in runtime.policy_service.catalog(repository_root=Path(repository))
    )
    assert corpus, "the corpus is empty; the retrieval assertions would prove nothing"

    with TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        assert started.status_code == 200, started.text
        case_id = started.json()["case_id"]

        # A case a review can actually be uncertain about. `start` opens an empty one, and an
        # empty case gives the model nothing to hinge on — it judges every candidate on the
        # code alone and the review completes in one pass, leaving the clarification round
        # unexercised. Stating a goal whose decisive fact is deliberately missing is what
        # makes "I would need to know who owns this" the correct judgement rather than a
        # coin toss. The tests still cope with a model that judges anyway.
        revised = client.patch(
            f"/api/cases/{case_id}",
            json={
                "goal": (
                    "Split this service between two teams next quarter without slowing "
                    "either of them down."
                ),
                "constraints": [
                    {
                        "text": (
                            "Which team will own the warehouse integration has not been "
                            "decided, and nobody has committed to owning the shared "
                            "reporting path."
                        )
                    }
                ],
            },
        )
        assert revised.status_code == 200, revised.text

        first = client.post(
            "/api/reviews",
            json={
                "case_id": case_id,
                "repository_root": repository,
            },
        )
        assert first.status_code == 201, first.text
        opened = first.json()

        resumed: dict[str, Any] | None = None
        if opened["status"] == "awaiting_answers":
            # Answered, not skipped. Skipping resumes the graph without ever revising the
            # case, and revising the case is what a second round of judgement is triggered
            # by — so a skipped resume would leave half the flow this exists for unrun.
            answered_questions = [
                {
                    "question_id": question["id"],
                    "status": "answered",
                    "value": (
                        "One team owns this service end to end, and we expect the warehouse "
                        "integration to be replaced within two quarters."
                    ),
                    "actor": "architect",
                }
                for question in opened["questions"]
            ]
            response = client.post(
                f"/api/reviews/{opened['id']}/answers",
                json={"answers": answered_questions, "stop": True},
            )
            assert response.status_code == 200, response.text
            resumed = response.json()

        final = resumed if resumed is not None else opened

        decision = client.post(
            "/api/decisions",
            json={
                "review_id": final["id"],
                "candidate_id": final["findings"][0]["candidate"]["id"],
                "disposition": "accept",
                "author": "architect",
                "reasoning": "This boundary is intentional.",
            },
        )
        assert decision.status_code == 201, decision.text

        conversation = client.post(
            "/api/review-conversations", json={"review_id": final["id"]}
        )
        assert conversation.status_code == 201, conversation.text
        message = client.post(
            f"/api/review-conversations/{conversation.json()['id']}/messages",
            json={"question": "Which finding is the most expensive to leave alone?"},
        )
        assert message.status_code == 200, message.text

        return Lifecycle(
            started=started.json(),
            first=opened,
            resumed=resumed,
            final=final,
            decision=decision.json(),
            conversation=message.json(),
            corpus_policy_ids=corpus,
            repository_root=repository,
        )


@pytest.fixture(scope="module")
def lifecycle(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Lifecycle]:
    before = os.environ.copy()
    # Pinned rather than chosen through the API. A pin is refused by name when the provider
    # is switched off, which is a clearer failure than a review that starts and then cannot
    # find a model; and the embedding variables are read once, when the runtime is built.
    os.environ["ARCHCOMPASS_EMBEDDING_PROVIDER"] = EMBEDDING_PROVIDER
    os.environ["ARCHCOMPASS_EMBEDDING_MODEL"] = EMBEDDING_MODEL
    os.environ["ARCHCOMPASS_EMBEDDING_DIMENSIONS"] = str(EMBEDDING_DIMENSIONS)
    try:
        # `build_runtime` loads the working directory's `.env`, which is where a developer's
        # key lives; the probes after it decide whether there is anything to run.
        runtime = build_runtime(
            tmp_path_factory.mktemp("google-e2e"),
            pin=pinned_model("google", REASONING_MODEL, thinking=False),
        )
        _require_google()
        _require_local_embeddings(runtime)
        try:
            yield _run_lifecycle(runtime, str(SUBJECT_REPOSITORY.resolve()))
        except Exception as error:
            detail = str(error)
            # An exhausted free tier is not a broken build and must not read as one. Any
            # other failure is re-raised untouched.
            if "RESOURCE_EXHAUSTED" not in detail and "429" not in detail:
                raise
            pytest.skip(f"Google free-tier quota is exhausted; retry later. {detail[:300]}")
    finally:
        os.environ.clear()
        os.environ.update(before)
