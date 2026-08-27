"""The values the frontend hard-codes that only the backend knows are still right.

The API's *shapes* are already guarded: `make api-types-check` regenerates the OpenAPI
types and fails on a diff, so a field the server adds or drops breaks the frontend build.
Nothing guarded the *values*. Two kinds of drift got through:

A stage name that no `STAGE_LABELS` entry covers falls through `stageLabel`'s `??` to
`humanise(stage)`, so a missing label is not an error — it is a raw graph node name printed
to somebody watching their review run. `rejudge_investigated` reached the screen as
"Rejudge investigated" from the day it was added.

And the landing page renders the real finding surface from a written-out review, so every
identity in that specimen is a claim about what this build produces. It printed
`google:gemini-3.6` for months after the direct Google integration was deleted — a provider
prefix no build can produce, in a shape the product does not use.

Both are the same test: something the backend decides, copied into TypeScript by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

from archcompass.policies.retrieval import DENSE_RETRIEVER_RELEASE_TOP_K, FUSION_STRATEGY
from archcompass.reasoning.adapters.deep_judge import DeepArchitectureJudge
from archcompass.reasoning.adapters.deterministic import (
    DETERMINISTIC_MODEL_IDENTITY,
    DeterministicJudge,
)
from archcompass.reasoning.adapters.tool_loop import INVESTIGATION_PROMPT_IDENTITY

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"

#: LangGraph's own name for the pause it raises `interrupt()` from. It is not a node this
#: repository registers, and it is labelled because it arrives in the stage list beside ours.
_NOT_OURS = frozenset({"__interrupt__"})


def _registered_nodes() -> set[str]:
    """Every node name `build_review_graph` adds, read off the source that adds them.

    Off the text rather than off a built graph: building one needs a full set of
    capabilities, and what is being guarded is the list a person maintains by hand.
    """

    graph = (Path(__file__).resolve().parents[2] / "src/archcompass/workflow/graph.py").read_text(
        encoding="utf-8"
    )
    return set(re.findall(r'add_node\(\s*"([a-z_]+)"', graph))


def _stage_labels() -> set[str]:
    """The keys of the `STAGE_LABELS` object literal in `run-progress.tsx`."""

    source = (FRONTEND / "features/start/run-progress.tsx").read_text(encoding="utf-8")
    body = source.split("STAGE_LABELS: Record<string, string> = {", 1)[1].split("\n};", 1)[0]
    return set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*):", body, flags=re.MULTILINE))


def test_every_graph_node_has_a_sentence_a_person_can_read() -> None:
    """A node with no label is its own raw name, printed on the run page.

    `stageLabel` is `STAGE_LABELS[stage] ?? humanise(stage)`, and that fallback is what makes
    the omission silent: adding a node ships a working page that says "Rejudge investigated"
    to whoever is watching. Three surfaces render it — the run page, the revision rail and the
    reviews listing — so there is nowhere the omission is invisible except in a test suite.
    """

    unlabelled = _registered_nodes() - _stage_labels()
    assert not unlabelled, (
        f"these graph nodes reach the screen as their own node names: {sorted(unlabelled)}. "
        "Add a sentence for each to STAGE_LABELS in frontend/src/features/start/run-progress.tsx."
    )


def test_no_label_survives_the_node_it_described() -> None:
    """The other direction: a label for a node that no longer exists is dead weight.

    Not an assertion about correctness on screen — nothing renders it — but a stage that was
    renamed leaves both halves wrong, and only this half is findable.
    """

    orphans = _stage_labels() - _registered_nodes() - _NOT_OURS
    assert not orphans, f"labels for nodes that are no longer registered: {sorted(orphans)}"


def test_the_landing_specimen_is_attributed_to_a_build_that_exists() -> None:
    """The public page renders the real finding surface, so its identities are claims.

    `case-file.ts` is `Review` and `Finding` off the wire, and the compiler checks that. It
    cannot check that `model_identity` names a provider this product registers, that the
    prompt id is the one in use, or that the retriever version is the one shipping — and all
    three drifted at once while the types stayed green.
    """

    case_file = (FRONTEND / "features/landing/case-file.ts").read_text(encoding="utf-8")
    bearings = (FRONTEND / "features/landing/bearings.ts").read_text(encoding="utf-8")

    identities = re.findall(r'model_identity: "([^"]+)"', case_file)
    assert identities, "the specimen attributes nothing, which is its own defect"
    # Three producers write this field, and the two regexes below claimed to be exhaustive
    # while only covering two of them. A finding judged by a real provider is
    # `provider:model:thinking=…` (`reasoning/records.py:model_identity`); a retrieval
    # provenance is the embedding store's namespace,
    # `provider:model:dimensions[:task-prompted]` (`reasoning/adapters/factory.py`); and the
    # stand-in writes one flat string with neither a thinking mode nor a dimension in it,
    # because it has no provider to have either. `fake:deterministic-architecture-v4` matched
    # neither pattern, so a specimen depicting an offline review — the one every developer
    # without a key sees — would have been rejected as a shape the product does not write.
    judged = re.compile(r"^[a-z]+:.+:thinking=.+$")
    embedded = re.compile(r"^[a-z]+:.+:\d+(:task-prompted)?$")
    for identity in identities:
        provider = identity.split(":", 1)[0]
        assert provider in {"ollama", "openrouter", "fake"}, (
            f"the landing page attributes a judgement to {provider!r}, "
            "which is not a provider this build registers"
        )
        assert (
            judged.match(identity)
            or embedded.match(identity)
            or identity == DETERMINISTIC_MODEL_IDENTITY
        ), f"{identity!r} is none of the three shapes the product writes into model_identity"

    # Asked of the judges rather than written out, because the point of the assertion is that
    # it tracks what the build produces without anybody remembering to widen it. There is a
    # prompt identity per judge — `reasoning/records.py` argues why they are not one constant
    # — and `SelectedLangChainJudge.in_force` is what chooses between them.
    #
    # `LangChainArchitectureJudge` is deliberately not here. `bootstrap` builds
    # `review_toolbox` unconditionally, so `in_force` can only ever name the deep judge or the
    # stand-in, and `judge:v3` is reachable from a test and from nothing a deployment runs.
    # Admitting it widened this set to three and *weakened* it: a specimen attributed to a
    # prompt no build sends would have passed, which is the exact drift the test exists for.
    offered = {
        DeepArchitectureJudge.identity,
        DeterministicJudge.identity,
        # Not a judge. A judgement's lookups are a record of their own, stamped by the tool
        # loop that made them, and the specimen shows one.
        INVESTIGATION_PROMPT_IDENTITY,
    }
    for prompt in set(re.findall(r'prompt_identity: "([^"]+)"', case_file)):
        assert prompt in offered, (
            f"the specimen cites prompt {prompt!r}; this build sends "
            f"{', '.join(sorted(repr(item) for item in offered))}"
        )

    shipped = f"2-{FUSION_STRATEGY}-k{DENSE_RETRIEVER_RELEASE_TOP_K}"
    for version in set(re.findall(r'version: "([^"]+)"', case_file)):
        assert version == shipped, (
            f"the specimen's retrieval provenance says {version!r}; the shipped retriever "
            f"reports {shipped!r}"
        )

    assert "google:gemini" not in bearings, (
        "the hero's specimen still names the deleted direct Google integration"
    )
