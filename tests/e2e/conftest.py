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
expensive part: every candidate judged once per clarification round, questions generated for
each, a synopsis written for each, and one conversation at the end. Buying that once per
assertion would put the file out of reach of the tier it is written for.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
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

#: Chosen because the model asks about it, which is the half of the lifecycle a cheaper
#: repository leaves unrun.
#:
#: This was `warehouse-sync` — five candidates, the smallest thing that still exercises
#: fan-out — and against an empty case the model judged every one of them outright and never
#: stated a hinge. Nothing failed: the clarification assertions skip themselves when no
#: question was asked, and they did, every time, so the round this file exists to verify was
#: never once verified. `speech-vendor` is a service that has run on a single speech vendor
#: since it was written, and whether its six sole-implementation ports are deliberate is a
#: question the repository genuinely cannot answer — so the model asks, and the clarification
#: round runs. Eight candidates over up to three rounds is more quota than five judged once,
#: and it is what the coverage costs.
SUBJECT_REPOSITORY = Path("examples/cases/speech-vendor/repository")


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
    #: Why each hinge that was investigated and lost was lost, in the order they were lost.
    #: Empty is the passing shape. See `_dropped_investigations` for why the responses above
    #: cannot answer this on their own.
    dropped_investigations: tuple[BaseException | None, ...]


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


#: The node that investigates hinges, and the message it logs when one is lost.
#:
#: Named here because the graph is deliberately built to survive this: an investigation is an
#: improvement to a question, so `investigate_hinges` catches everything, logs, and lets the
#: unimproved hinge go on to the person it was always going to reach. That is right for a
#: running review and blinding for a test — a run where every investigation failed produces
#: the same empty manifest as a run where the model was confident throughout, and the
#: assertions on that manifest skip themselves in both.
INVESTIGATION_LOGGER = "archcompass.workflow.nodes"
INVESTIGATION_LOST = "was not investigated"


@contextmanager
def _dropped_investigations(losses: list[BaseException | None]) -> Iterator[None]:
    """Collect the exceptions `investigate_hinges` swallows, without changing what it does.

    A handler rather than `caplog`, because the review runs once in a module-scoped fixture
    and `caplog` is per test. The exception is kept rather than the message: an exhausted
    quota and a model that cannot honour its output schema are both a lost investigation
    here, and only one of them is a defect the suite should fail on.
    """

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if INVESTIGATION_LOST not in record.getMessage():
                return
            losses.append(record.exc_info[1] if record.exc_info else None)

    logger = logging.getLogger(INVESTIGATION_LOGGER)
    handler = _Collector(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)


def _run_lifecycle(runtime: Runtime, repository: str) -> Lifecycle:
    corpus = frozenset(
        policy.id
        for policy in runtime.policy_service.catalog(repository_root=Path(repository))
    )
    assert corpus, "the corpus is empty; the retrieval assertions would prove nothing"

    losses: list[BaseException | None] = []
    with _dropped_investigations(losses), TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        assert started.status_code == 200, started.text
        case_id = started.json()["case_id"]

        # The case is left as `start` opened it: empty.
        #
        # This used to state a goal and a constraint whose decisive fact was deliberately
        # missing, so that the model had something to be uncertain about and the
        # clarification round would run. That was the test arranging the conditions the
        # product is supposed to create on its own, and it hid the real behaviour: on an
        # empty case the model judged everything on the policy corpus and never asked.
        #
        # Nothing can state a constraint any more, and the judgement contract now says an
        # empty case out loud and gives asking first-class standing. So an empty case is the
        # honest input, and whether a round happens is the model's call — which is what
        # `Lifecycle.resumed` being optional has always documented.

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
        rounds: list[dict[str, Any]] = []
        waiting = opened
        while waiting["status"] == "awaiting_answers":
            # Answered, not skipped, and resumed without `stop`. Both halves matter and only
            # one of them used to be here: skipping resumes the graph without revising the
            # case, and `stop` routes the revised case straight to the composer, so either
            # one on its own leaves the rejudgement this file exists to exercise unrun. It
            # did, silently, for as long as the flag was set — the second review came back
            # with round one's findings copied verbatim and every assertion below still
            # passed, because none of them compared the two rounds.
            #
            # A loop rather than one resume, because answering is not guaranteed to end the
            # review: a model that still cannot judge on what it now knows may ask again,
            # and the graph allows it up to three rounds. Two of those are a real shape this
            # has to survive, so the fixture answers until the review stops asking rather
            # than asserting that one answer was enough.
            answered_questions = [
                {
                    "question_id": question["id"],
                    "status": "answered",
                    # Chosen from what the model offered wherever it offered anything, which
                    # is the path a person takes: the options are the product's answer to
                    # "never make someone type what they could pick". Typed prose is the
                    # fallback for a question asked with a blank box.
                    "value": (
                        question["options"][0]
                        if question["options"]
                        else (
                            "One team owns this service end to end, and we expect a second "
                            "provider behind these boundaries within two quarters."
                        )
                    ),
                    "actor": "architect",
                }
                for question in waiting["questions"]
            ]
            response = client.post(
                f"/api/reviews/{waiting['id']}/answers",
                json={"answers": answered_questions, "stop": False},
            )
            assert response.status_code == 200, response.text
            waiting = response.json()
            rounds.append(waiting)
            if resumed is None:
                resumed = waiting

        final = rounds[-1] if rounds else opened

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
            dropped_investigations=tuple(losses),
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
            # Thinking on, because it is what this model is actually run with — and because
            # the hinge pass asks it to choose lookups and then honour a JSON schema in
            # the same breath, which is the combination a non-thinking small model is
            # least reliable at.
            pin=pinned_model("google", REASONING_MODEL, thinking=True),
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
