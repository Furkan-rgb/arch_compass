"""The runtimes the end-to-end reviews run on, one per provider that can drive a whole one.

Two of them, and the difference between them is the point. `lifecycle` judges on Google and
embeds on a local Ollama, because the free tier allows 100 embedded texts a minute and the
shipped corpus chunks into 486 of them — retrieval would exhaust the minute before the first
verdict. `local_lifecycle` does both halves on Ollama, which is the deployment a company
evaluating this product on its own code actually gets: nothing leaves the machine, and there
is no key to obtain before the first review runs.

Neither is in `make check`. `make test-openrouter` runs the first, `make test-ollama` the second,
and each skips with a message rather than failing when the machine it is on cannot serve it.
The lifecycles run in module-scoped fixtures because they are the expensive part: every
candidate judged once per clarification round, questions generated for each, a synopsis
written for each, and one conversation at the end.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.configuration import EmbeddingModelConfig
from archcompass.policies.adapters import prebuilt
from archcompass.policies.adapters.bundled import bundled_corpus
from archcompass.reasoning.adapters.openrouter import DESCRIPTOR as OPENROUTER_DESCRIPTOR
from archcompass.reasoning.adapters.providers import (
    OLLAMA_DESCRIPTOR,
)
from tests.e2e.lifecycle import Lifecycle, run_lifecycle

#: The cheapest Google model this build offers. Named here rather than left to whatever the
#: workspace would default to, so a change of default cannot quietly move these onto a model
#: somebody has to pay for.
REASONING_MODEL = "google/gemini-3.5-flash-lite"

#: The local reasoning model, and whether it is asked to think.
#:
#: Thinking is off. It is not free here the way it is on a hosted tier — a local card spends
#: real seconds on it, and the whole point of this suite is that a company can run it on the
#: machine in front of them. What it buys is reliability on the structured calls, and the
#: two schemas that were losing to a non-thinking model were losing to a rule the prompt had
#: never stated rather than to a lack of depth; the prompt says it now.
LOCAL_REASONING_MODEL = "qwen3.8:27b"
LOCAL_THINKING = False

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

#: The repository the local review runs on, chosen for the one thing that is hard to get.
#:
#: Not the same choice as above, and the reason is worth writing down because it is not the
#: obvious one. What a clarification round needs is a hinge the repository cannot settle —
#: and the lookups are good at settling them. Measured on this model: `speech-vendor` hinged
#: twice and the second judgement cleared both, `warehouse-sync` hinged once and it cleared
#: that, and both reviews completed in one pass with nothing to answer. That is the product
#: working, and it leaves the resume path unrun.
#:
#: `boundary-review` is six boundaries with one implementation each, and the question it
#: raises is whether that is deliberate. Intent is not in the source, so the lookups come
#: back having established what is there and settled nothing — the hinge survives, the
#: review asks, and the round this suite exists to drive runs. Six candidates over two
#: rounds is around three minutes on one card; the sibling suite's eight over three would be
#: nearer ten.
LOCAL_SUBJECT_REPOSITORY = Path("examples/cases/boundary-review/repository")


def _local_embedding_config() -> EmbeddingModelConfig:
    return EmbeddingModelConfig(
        provider=EMBEDDING_PROVIDER,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSIONS,
    )


def _require_openrouter() -> None:
    """Skip rather than fail when this machine has no quota to spend.

    Constructing the provider is what fails when a key is missing or refused, so the probe is
    the honest check: it answers unavailable for an absent key, a refused project and an
    unreachable network alike, and its detail is what a reader needs to see.
    """

    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        pytest.skip("OPENROUTER_API_KEY is not set; there is nothing to run these against")
    probe = OPENROUTER_DESCRIPTOR.probe(OPENROUTER_DESCRIPTOR.defaults)
    if not probe.available:
        pytest.skip(f"Google is not reachable with this key: {probe.detail}")
    offered = {model.name for model in probe.models}
    if REASONING_MODEL not in offered:
        pytest.skip(f"this key does not reach {REASONING_MODEL}; it has {sorted(offered)}")


def _require_local_reasoning() -> None:
    """Skip unless this machine's Ollama offers the model the local suite judges with.

    Asked of the descriptor's own probe, which is what the interface asks: a model this
    answers with is a model somebody could have chosen in the workspace, and a test that
    pinned past the probe would pass on a machine where the picker is empty.
    """

    probe = OLLAMA_DESCRIPTOR.probe(OLLAMA_DESCRIPTOR.defaults)
    offered = {model.name for model in probe.models}
    if LOCAL_REASONING_MODEL in offered:
        return
    if not probe.available:
        pytest.skip(
            f"Ollama is not serving {LOCAL_REASONING_MODEL} "
            f"(`ollama pull {LOCAL_REASONING_MODEL}`): {probe.detail}"
        )
    pytest.skip(
        f"{LOCAL_REASONING_MODEL} is not installed "
        f"(`ollama pull {LOCAL_REASONING_MODEL}`); this machine offers {sorted(offered)}"
    )


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


@pytest.fixture(scope="session")
def local_policy_index(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """An index of the shipped corpus embedded by the local model, built once per session.

    Both suites need it, not only the local one: they pin the same local embedder, and the
    index this package ships is Google's.

    Necessary, not a convenience. The index this package ships was built with Google's
    embedder at 3,072 dimensions, and vectors from two models are not comparable — so a
    workspace that embeds with EmbeddingGemma finds nothing in it. Production retrieval
    refuses to embed on the fly rather than spend a review's time doing it, so without this
    the first review answers `PolicyEmbeddingsMissingError` and nothing downstream runs.

    That refusal is the right behaviour and this is the documented way past it: the same
    `build` the shipped file is made with, over the same corpus, for this embedder. It costs
    about forty seconds against a local EmbeddingGemma and is bought once per session.

    The module constant is repointed rather than the shipped file replaced, because the
    shipped file is committed, read-only, and correct for the model it was built for.
    """

    # Before the build, not after. Indexing the corpus takes about forty seconds, and doing
    # it first on a machine with no Ollama meant the skip a reader saw was "the local
    # embedder could not index the corpus" with a raw connection error attached — while the
    # two messages naming the exact `ollama pull` sat further down, unreachable.
    _require_local_reasoning()
    path = tmp_path_factory.mktemp("local-policy-index") / "policy-index.sqlite3"
    corpus = bundled_corpus()
    config = _local_embedding_config()
    with pytest.MonkeyPatch.context() as patch:
        # Set before the build, because `embedding_config_from_environment` is what any
        # other reader of this index will resolve, and the two must agree on the identity.
        patch.setenv("ARCHCOMPASS_EMBEDDING_PROVIDER", EMBEDDING_PROVIDER)
        patch.setenv("ARCHCOMPASS_EMBEDDING_MODEL", EMBEDDING_MODEL)
        patch.setenv("ARCHCOMPASS_EMBEDDING_DIMENSIONS", str(EMBEDDING_DIMENSIONS))
        try:
            prebuilt.build(path, corpus, config)
        except Exception as error:
            pytest.skip(f"the local embedder could not index the corpus: {error}")
        patch.setattr(prebuilt, "PREBUILT_INDEX", path)
        yield path


@pytest.fixture(scope="module")
def lifecycle(
    tmp_path_factory: pytest.TempPathFactory, local_policy_index: Path
) -> Iterator[Lifecycle]:
    """One review judged on Google and embedded on this machine.

    It needs the locally-built index for the same reason the Ollama suite does, and for
    longer than anybody noticed: this fixture has always pinned EmbeddingGemma, the shipped
    index has always been Google's at 3,072 dimensions, and since production retrieval
    stopped embedding on the fly the first review has answered `PolicyEmbeddingsMissingError`
    rather than running. The quota catch below does not match that message, so it re-raised
    and every test in the file errored — on a suite that is outside `make check` and only run
    by hand.
    """

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
            tmp_path_factory.mktemp("hosted-e2e"),
            # Thinking on, because it is what this model is actually run with — and because
            # the hinge pass asks it to choose lookups and then honour a JSON schema in
            # the same breath, which is the combination a non-thinking small model is
            # least reliable at.
            pin=pinned_model("openrouter", REASONING_MODEL),
        )
        _require_openrouter()
        _require_local_embeddings(runtime)
        try:
            yield run_lifecycle(runtime, str(SUBJECT_REPOSITORY.resolve()))
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


@pytest.fixture(scope="module")
def local_runtime(
    tmp_path_factory: pytest.TempPathFactory, local_policy_index: Path
) -> Iterator[Runtime]:
    """A workspace whose every model is on this machine, and which can reach nothing else.

    `ARCHCOMPASS_PROVIDERS` is narrowed to `ollama` so that a `.env` holding a Google key —
    which the machine running `make test-openrouter` has by definition — cannot make this suite
    quietly reach the network. If anything here judged on Google the run would still pass,
    and it would be measuring the wrong thing entirely.

    Hinge investigation is off, and that is the one deliberate departure from what a
    workspace does by default. With the lookups on, whether a person is ever asked is the
    model's call: measured on this model, `boundary-review` hinged and the lookups settled
    it about half the time, so the clarification round — the loop this product is built
    around — ran or did not run depending on how a tool loop went that morning, and the
    tests for it skipped themselves saying nothing was asked. Off, the hinge reaches the
    person every time, which is what makes the round assertable.

    It is not a shape invented for the test. `ReviewWorkflowCapabilities.investigator`
    defaults to `NoHingeInvestigation`, and a workspace on a model that cannot call tools
    runs exactly this. `test_a_hinge_is_checked_against_this_repository_by_this_model` then
    runs the pass this switch skips directly, against the same live model and the same
    atlas — so what goes uncovered here is the graph dispatching on `supports_tools`, not
    the lookups themselves.

    The environment is restored on teardown rather than through `monkeypatch`, which is
    function-scoped and would put it back before the first test read anything.
    """

    before = os.environ.copy()
    os.environ["ARCHCOMPASS_PROVIDERS"] = "ollama"
    os.environ["ARCHCOMPASS_HINGE_INVESTIGATION"] = "0"
    os.environ["ARCHCOMPASS_EMBEDDING_PROVIDER"] = EMBEDDING_PROVIDER
    os.environ["ARCHCOMPASS_EMBEDDING_MODEL"] = EMBEDDING_MODEL
    os.environ["ARCHCOMPASS_EMBEDDING_DIMENSIONS"] = str(EMBEDDING_DIMENSIONS)
    try:
        _require_local_reasoning()
        runtime = build_runtime(
            tmp_path_factory.mktemp("ollama-e2e"),
            pin=pinned_model(
                "ollama", LOCAL_REASONING_MODEL, thinking=LOCAL_THINKING
            ),
        )
        _require_local_embeddings(runtime)
        yield runtime
    finally:
        os.environ.clear()
        os.environ.update(before)


@pytest.fixture(scope="module")
def local_subject(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The example repository, copied somewhere it can be edited.

    The bundled one is read as a fixture by half the suite and is under version control, so
    a test that changed it would change what every other test is looking at. A copy is also
    the honest shape: what is being demonstrated is a repository that moves between reviews,
    and the ones this product is pointed at do.
    """

    assert LOCAL_SUBJECT_REPOSITORY.is_dir(), (
        f"{LOCAL_SUBJECT_REPOSITORY} is not there; run pytest from the repository root"
    )
    destination = tmp_path_factory.mktemp("ollama-subject") / "repository"
    # Both ignored names are gitignored, so neither would ever show up in `git status` as
    # something the copy had picked up. `__pycache__` the analyser skips anyway; a copied
    # `.archcompass/` would be read as a policy source belonging to the repository under
    # review, which is a different corpus in the prompt with nothing to say it changed.
    shutil.copytree(
        LOCAL_SUBJECT_REPOSITORY,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".archcompass"),
    )
    return destination


@pytest.fixture(scope="module")
def local_lifecycle(local_runtime: Runtime, local_subject: Path) -> Lifecycle:
    """The same review the sibling suite drives, on models that never leave the machine.

    And two more steps than the sibling suite drives, because there is no quota here to
    ration — only a card already committed for three minutes. After the answers are in, it
    asks for a review of the unchanged repository, which should be refused rather than
    charged for; then it changes the repository and asks again, which is the shape a second
    demonstration actually has. Between them they cover the half of this product a first
    review cannot show: the delta, the lineage, and whether answering a question changed
    what the next review is judged against.
    """

    def change() -> None:
        """One new boundary with one implementation, which is a new candidate and not a
        rewrite of an old one — so the delta has something to call new and everything else
        stays comparable."""

        (local_subject / "audit.py").write_text(
            '''"""Audit trail for scheduled work."""

from __future__ import annotations

from typing import Protocol


class AuditSink(Protocol):
    """Where a completed task is written down."""

    def record(self, task_id: str, outcome: str) -> None: ...


class StdoutAuditSink:
    """The only sink there has ever been."""

    def record(self, task_id: str, outcome: str) -> None:
        print(f"{task_id}: {outcome}")
''',
            encoding="utf-8",
        )

    return run_lifecycle(local_runtime, str(local_subject.resolve()), change=change)
