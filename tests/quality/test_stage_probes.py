"""Tier 2: call one reasoning stage against a live model, assert typed properties.

Tier 1 replays recorded answers with no model running, which proves the pipeline still
accepts what a model once produced. It cannot say whether a model can satisfy the
contracts *now*, because nothing is generated. That is what these probes measure.

Each probe loads a recorded stage input — the context and packet a real consultation
actually built — and makes one live call. Assertions are on the *structured* output, so
they survive model variation: a claim's classification, the IDs it cites, whether the
workflow's own validation accepts it. Never on prose.

Two assertion classes, deliberately kept apart:

- **Evidence discipline** is binary. A packet surfacing no repository evidence must
  yield no repository observation; a single violation is a fabricated claim, not a bad
  day. These fail on one occurrence.
- **Contract achievability** asks whether the output satisfies the pipeline *unaided*.
  The pipeline recovers from a good deal, so a failure here is a signal about the
  contract rather than a broken product — but it is the signal nothing else measures,
  and today it is the one that predicted two dead captures.

Deselected by default: these need a running Ollama and cost real calls. Run them with
`pytest -m "ollama and architectural_quality"`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.models.ollama import OllamaReasoningProvider
from archcompass.application.synthesis import build_claim_pool, validate_proposal
from archcompass.configuration import AppConfig, load_config
from archcompass.domain.consultation import (
    ClaimClassification,
    ConcernAnalysis,
    FocusedAnalysisPacket,
)
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.workflows.consultation import ConsultationWorkflow
from tests.replay.recorded import Recording, available_recordings

pytestmark = [pytest.mark.ollama, pytest.mark.architectural_quality]

RECORDINGS = available_recordings()
requires_recording = pytest.mark.skipif(
    not RECORDINGS,
    reason="No captured recordings; run `make capture-recordings` against a live model.",
)


@pytest.fixture(scope="module")
def live_config() -> AppConfig:
    config = load_config(Path("config/models.yaml").resolve())
    assert config.models.reasoning.provider == "ollama"
    return config


@pytest.fixture(scope="module")
def provider(live_config: AppConfig) -> OllamaReasoningProvider:
    return OllamaReasoningProvider(live_config.models.reasoning)


@pytest.fixture(scope="module")
def recording() -> Recording:
    return RECORDINGS[0]


@pytest.fixture(scope="module")
def packet(recording: Recording) -> FocusedAnalysisPacket:
    packets = recording.packets()
    assert packets, "The recording surfaced no focused packet to probe with"
    return packets[0]


def _strip_repository_evidence(packet: FocusedAnalysisPacket) -> FocusedAnalysisPacket:
    """The same concern and policies, with every repository artifact removed.

    Derived from a recorded packet rather than hand-authored so the concern, cluster and
    policy corpus stay realistic — only the repository evidence is gone. This is the
    shape a greenfield consultation produces, and the one where a repository observation
    can only have been invented.
    """

    return packet.model_copy(
        update={
            "node_summaries": [],
            "node_evidence": [],
            "metrics": [],
            "relationships": [],
            "relationship_evidence": [],
            "test_ids": [],
            "test_evidence": [],
            "excerpts": [],
        }
    )


@requires_recording
def test_analysis_of_an_evidence_free_packet_makes_no_repository_observation(
    provider: OllamaReasoningProvider,
    recording: Recording,
    packet: FocusedAnalysisPacket,
) -> None:
    """With nothing surfaced, a repository observation can only be fabricated.

    The adapter states this in a runtime instruction — "When no atlas IDs are allowed,
    do not classify a finding as a repository observation" — but prose is not a
    constraint, so whether it holds is a question about the model, not the code. The
    workflow would drop such a claim later; this probe asks whether it is made at all.
    """

    analysis = provider.analyze_concern_cluster(
        recording.global_context(),
        _strip_repository_evidence(packet),
    )

    fabricated = [
        finding.text
        for finding in analysis.findings
        if finding.classification == ClaimClassification.REPOSITORY_OBSERVATION
    ]

    assert fabricated == [], (
        "A packet with no repository evidence produced repository observations:\n  "
        + "\n  ".join(fabricated)
    )


@requires_recording
def test_analysis_cites_only_evidence_its_packet_surfaced(
    provider: OllamaReasoningProvider,
    recording: Recording,
    packet: FocusedAnalysisPacket,
) -> None:
    """Every cited node and policy must come from this packet.

    Both allowlists reach the model as prose rather than as schema enums, so this is the
    probe that says whether that is sufficient. The live capture already showed it is
    not for policies — two invented policy IDs were dropped by repair — so a failure
    here is a measurement, and the fix is to constrain the schema rather than to ask
    more firmly.
    """

    analysis = provider.analyze_concern_cluster(recording.global_context(), packet)

    allowed_nodes = set(packet.surfaced_node_ids)
    allowed_policies = {item.policy.id for item in packet.policies}
    invented_nodes = sorted(
        {
            reference.node_id
            for finding in analysis.findings
            for reference in finding.atlas_references
            if reference.node_id not in allowed_nodes
        }
    )
    invented_policies = sorted(
        {
            policy_id
            for finding in analysis.findings
            for policy_id in finding.policy_ids
            if policy_id not in allowed_policies
        }
    )

    assert (invented_nodes, invented_policies) == ([], []), (
        f"Analysis cited evidence the packet never surfaced.\n"
        f"  nodes:    {invented_nodes}\n"
        f"  policies: {invented_policies}"
    )


@requires_recording
def test_analysis_of_a_recorded_packet_satisfies_workflow_validation(
    provider: OllamaReasoningProvider,
    recording: Recording,
    packet: FocusedAnalysisPacket,
) -> None:
    """Achievability: does a live analysis survive the workflow that consumes it?

    Mirrors `advise` exactly — prepare, then validate — because the product's contract
    is what survives preparation, not what the model emits raw. This is the stage that
    killed two of three captures before spans were projected, so it is the one worth
    watching.
    """

    analysis = provider.analyze_concern_cluster(recording.global_context(), packet)
    metadata: dict[str, object] = {"model_output_repairs": []}

    prepared = ConsultationWorkflow._prepare_concern_analysis(
        analysis,
        packet=packet,
        metadata=metadata,
    )
    try:
        ConsultationWorkflow._validate_concern_analysis(prepared, packet)
    except ModelOutputValidationError as error:  # pragma: no cover - reported, not caught
        repairs = metadata["model_output_repairs"]
        pytest.fail(f"Live analysis failed workflow validation: {error}\nRepairs: {repairs}")

    assert prepared.findings, "Preparation removed every finding the analysis produced"


@requires_recording
def test_synthesis_of_a_recorded_pool_needs_no_proposal_repair(
    provider: OllamaReasoningProvider,
    recording: Recording,
) -> None:
    """Achievability: does synthesis satisfy its handle contract on the first attempt?

    Synthesis is the stage where the schema does the work — claim handles and cluster
    references are enum-constrained, so invalid references are unrepresentable rather
    than instructed. If that difference matters, it should show here as a clean first
    pass where the prose-constrained analysis stage does not.
    """

    analyses: list[ConcernAnalysis] = recording.analyses()
    clusters = recording.clusters()
    pool = build_claim_pool(
        case=recording.case(),
        clusters=clusters,
        analyses=analyses,
    )
    # Built the way `advise` builds it, so the probe constrains the same handle set the
    # product does rather than one invented here.
    cluster_refs = {
        pool.cluster_ref_by_id[cluster.cluster_id]: cluster.title for cluster in clusters
    }

    proposal = provider.propose_recommendation(
        recording.case(),
        recording.global_context(),
        recording.design_forces(),
        clusters,
        analyses,
        recording.alternatives(),
        recording.scenarios(),
        recording.packets(),
        available_claims=pool.available,
        cluster_refs=cluster_refs,
    )

    errors = validate_proposal(proposal, pool=pool)

    assert errors == [], "Live synthesis needed repair:\n  " + "\n  ".join(errors)
