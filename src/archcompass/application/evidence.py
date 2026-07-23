"""Evidence-reference validation for final reports."""

from __future__ import annotations

from archcompass.domain.atlas import AtlasNode
from archcompass.domain.consultation import Claim, ClaimClassification, RecommendationReport


def validate_report_evidence(
    report: RecommendationReport,
    *,
    allowed_nodes: dict[str, AtlasNode],
    allowed_policy_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    for claim in _all_claims(report):
        if (
            claim.classification == ClaimClassification.REPOSITORY_OBSERVATION
            and not claim.atlas_references
        ):
            errors.append(f"Repository observation {claim.claim_id} has no atlas reference")
        if claim.classification == ClaimClassification.POLICY_GUIDANCE and not claim.policy_ids:
            errors.append(f"Policy guidance {claim.claim_id} has no policy reference")
        for reference in claim.atlas_references:
            node = allowed_nodes.get(reference.node_id)
            if node is None:
                errors.append(
                    f"Claim {claim.claim_id} references unknown atlas node {reference.node_id}"
                )
                continue
            if reference.location is not None:
                location = reference.location
                if location.path != node.path:
                    errors.append(
                        f"Claim {claim.claim_id} source path does not match node {node.atlas_id}"
                    )
                if (
                    (node.start_line is not None
                    and location.start_line < node.start_line)
                    or (node.end_line is not None
                    and location.end_line > node.end_line)
                ):
                    errors.append(
                        f"Claim {claim.claim_id} source span exceeds node {node.atlas_id}"
                    )
        for policy_id in claim.policy_ids:
            if policy_id not in allowed_policy_ids:
                errors.append(
                    f"Claim {claim.claim_id} references policy that was not retrieved: {policy_id}"
                )
    return errors


def _all_claims(report: RecommendationReport) -> list[Claim]:
    unique: dict[str, Claim] = {}
    for collection in (
        report.confirmed_context,
        report.assumptions_and_unresolved_questions,
        report.repository_observations,
        report.relevant_policies,
        report.evidence_appendix,
    ):
        for claim in collection:
            unique[claim.claim_id] = claim
    return list(unique.values())

