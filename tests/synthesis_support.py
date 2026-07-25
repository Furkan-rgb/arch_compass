"""Compose a report from a provider proposal the way the workflow does.

Synthesis is two steps now: a provider returns a `ProposedRecommendation`, and the
application composes the persisted `RecommendationReport` from it plus the canonical
artifacts. Tests that need a report to inspect or corrupt should go through the same
path as production rather than constructing one directly.
"""

from __future__ import annotations

from archcompass.application.synthesis import (
    build_claim_pool,
    compose_recommendation,
)
from archcompass.domain.case import ArchitectureCase, CaseAlternative
from archcompass.domain.consultation import (
    ConcernAnalysis,
    ConcernCluster,
    DesignForce,
    FocusedAnalysisPacket,
    GlobalContext,
    RecommendationReport,
    ScenarioEvaluation,
)
from archcompass.ports.reasoning import FocusedReasoningProvider


def synthesize_report(
    provider: FocusedReasoningProvider,
    case: ArchitectureCase,
    context: GlobalContext,
    forces: list[DesignForce],
    clusters: list[ConcernCluster],
    analyses: list[ConcernAnalysis],
    alternatives: list[CaseAlternative],
    scenarios: list[ScenarioEvaluation],
    packets: list[FocusedAnalysisPacket],
) -> RecommendationReport:
    """Propose and compose, mirroring `ConsultationWorkflow.advise`."""

    pool = build_claim_pool(case=case, clusters=clusters, analyses=analyses)
    cluster_refs = {
        pool.cluster_ref_by_id[cluster.cluster_id]: cluster.title for cluster in clusters
    }
    proposal = provider.propose_recommendation(
        case,
        context,
        forces,
        clusters,
        analyses,
        alternatives,
        scenarios,
        packets,
        available_claims=pool.available,
        cluster_refs=cluster_refs,
    )
    return compose_recommendation(
        proposal,
        pool=pool,
        forces=forces,
        alternatives=alternatives,
        scenarios=scenarios,
        analyses=analyses,
        packets=packets,
    ).report
