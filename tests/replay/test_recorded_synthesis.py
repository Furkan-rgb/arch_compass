"""Replay real model answers through the real pipeline, with no model running.

The hand-authored payloads in `payloads.py` prove the contracts reject what they should.
These prove something the author of a fixture cannot: that the pipeline still accepts
what a real model actually produced. The two are complementary — a hand-written fixture
encodes what someone believed the code expects, a recording encodes what happened.

Absent recordings skip: a checkout that has never captured one is not broken. A recording
that exists but was captured under a different prompt FAILS, because a changed prompt
means the recorded answer is no longer evidence about the current one.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from archcompass.application.evidence import (
    canonicalize_report_findings,
    repair_report_evidence_with_history,
    validate_report_evidence,
)
from archcompass.application.synthesis import (
    build_claim_pool,
    compose_recommendation,
    validate_proposal,
)
from archcompass.domain.proposals import ProposedRecommendation
from archcompass.ports.reasoning import ReasoningTask
from tests.replay.recorded import Recording, available_recordings

RECORDINGS = available_recordings()
requires_recording = pytest.mark.skipif(
    not RECORDINGS,
    reason="No captured recordings; run `make capture-recordings` against a live model.",
)


def _ids(items: list[Recording]) -> list[str]:
    return [item.name for item in items]


class ReplayOutcome(NamedTuple):
    """What the validate/repair/re-validate cycle made of a recorded answer."""

    initial_errors: list[str]
    repair_actions: list[str]
    final_errors: list[str]


def _replay(recording: Recording) -> ReplayOutcome:
    """Drive a recorded answer through the same stages `consultation.py` drives.

    Kept deliberately parallel to the workflow's validation block: a replay that
    diverges from the pipeline tests a pipeline that does not exist.
    """

    proposal = ProposedRecommendation.model_validate_json(
        recording.response(ReasoningTask.SYNTHESIZE_RECOMMENDATION)
    )
    analyses = recording.analyses()
    pool = build_claim_pool(
        case=recording.case(),
        clusters=recording.clusters(),
        analyses=analyses,
    )

    assert validate_proposal(proposal, pool=pool) == []

    packets = recording.packets()
    composition = compose_recommendation(
        proposal,
        pool=pool,
        forces=recording.design_forces(),
        alternatives=recording.alternatives(),
        scenarios=recording.scenarios(),
        analyses=analyses,
        packets=packets,
    )
    canonical = canonicalize_report_findings(
        composition.report,
        packets=packets,
        analyses=analyses,
    )
    allowed_nodes = recording.allowed_nodes()
    allowed_policy_ids = {
        item.policy.id for packet in packets for item in packet.policies
    }
    initial_errors = validate_report_evidence(
        canonical.report,
        allowed_nodes=allowed_nodes,
        allowed_policy_ids=allowed_policy_ids,
        finding_evidence_by_cluster=canonical.evidence_by_cluster,
    )
    if not initial_errors:
        return ReplayOutcome(initial_errors=[], repair_actions=[], final_errors=[])

    repaired = repair_report_evidence_with_history(
        canonical.report,
        allowed_nodes=allowed_nodes,
        allowed_policy_ids=allowed_policy_ids,
        finding_evidence_by_cluster=canonical.evidence_by_cluster,
    )
    recanonicalized = canonicalize_report_findings(
        repaired.report,
        packets=packets,
        analyses=analyses,
    )
    return ReplayOutcome(
        initial_errors=initial_errors,
        repair_actions=repaired.actions,
        final_errors=validate_report_evidence(
            recanonicalized.report,
            allowed_nodes=allowed_nodes,
            allowed_policy_ids=allowed_policy_ids,
            finding_evidence_by_cluster=canonical.evidence_by_cluster,
        ),
    )


@requires_recording
@pytest.mark.parametrize("recording", RECORDINGS, ids=_ids(RECORDINGS))
def test_recorded_prompts_still_match_the_current_contracts(recording: Recording) -> None:
    """A prompt edit invalidates every answer recorded under the previous wording.

    This is the whole staleness mechanism. Prompt identities carry a content
    fingerprint, so this cannot be satisfied by editing a prompt and leaving the
    recording alone — which is exactly the silent drift a recorded corpus invites.
    """

    stale = recording.stale_prompts()

    assert stale == [], (
        f"Recording '{recording.name}' predates the current prompts:\n  "
        + "\n  ".join(stale)
        + "\nRe-capture it with `make capture-recordings`."
    )


@requires_recording
@pytest.mark.parametrize("recording", RECORDINGS, ids=_ids(RECORDINGS))
def test_a_real_synthesis_answer_composes_into_a_valid_report(
    recording: Recording,
) -> None:
    """The composed-synthesis path accepts a genuine model response end to end.

    This exercises the parse, the handle allowlists, composition, finding
    canonicalisation and evidence validation against bytes a model really produced —
    the combination that no deterministic substitute can vouch for.

    The assertion mirrors the product's actual contract, which is *valid after at most
    one deterministic repair* — `consultation.py` validates, repairs once, then
    re-validates and only fails on what survives. Asserting a clean first pass here
    would hold the recording to a stricter rule than the pipeline it is replaying.
    """

    outcome = _replay(recording)

    assert outcome.final_errors == []


@requires_recording
@pytest.mark.parametrize("recording", RECORDINGS, ids=_ids(RECORDINGS))
def test_a_real_synthesis_answer_needs_no_evidence_repair(
    recording: Recording,
) -> None:
    """Contract achievability: did a real answer satisfy the rules unaided?

    Separated from the contract test above so a regression here is legible as what it
    is. A repair is the pipeline overriding the model, and every override is either a
    model that cannot meet the contract or a contract that asks for the impossible —
    both worth knowing about, neither worth failing the run over. This is the signal
    the harness plan wanted and nothing else measures.
    """

    outcome = _replay(recording)

    assert outcome.initial_errors == [], (
        f"Recording '{recording.name}' validated only after repair:\n  "
        + "\n  ".join(outcome.initial_errors)
        + "\nThe run still succeeded, so this is an evidence-discipline signal rather "
        "than a broken pipeline."
    )


@requires_recording
@pytest.mark.parametrize("recording", RECORDINGS, ids=_ids(RECORDINGS))
def test_a_recording_describes_one_real_consultation(recording: Recording) -> None:
    """Guard the bundle's own integrity, so a broken capture fails here not later."""

    manifest = recording.manifest

    assert manifest.reasoning_model.startswith("ollama:"), (
        "A recording must come from a live provider; a deterministic run proves nothing "
        "about what a real model produces."
    )
    assert {call.task for call in manifest.calls} >= {
        ReasoningTask.DISCOVER_DESIGN_FORCES,
        ReasoningTask.CLUSTER_DESIGN_FORCES,
        ReasoningTask.SYNTHESIZE_RECOMMENDATION,
    }
    for call in manifest.calls:
        assert (recording.directory / "responses" / call.response_file).is_file()
