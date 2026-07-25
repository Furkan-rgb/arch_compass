"""Compose the persisted recommendation from canonical artifacts plus one proposal.

The synthesis stage returns a `ProposedRecommendation`: prose, findings, and the claim
handles that support them. This module turns that into the `RecommendationReport` that
is validated, rendered, and stored.

Four kinds of provider error disappear here by construction rather than by repair:

* **Invented evidence** — claims are drawn from a pool this module builds from the
  concern analyses and the pinned case, so a claim reference either resolves to a real
  claim or fails validation. Providers may author only advisor inference and derived
  constraints, which carry no evidence references.
* **Misclassified sections** — claims are placed into report sections by their own
  classification, so there is no section to get wrong.
* **Duplicate claim identity** — claim IDs are owned by ArchCompass. Pooled claims keep
  the identity they already had; authored claims are named by a hash of their content,
  so identical text is one claim and different text can never collide.
* **Altered canonical artifacts** — design forces, alternatives, scenarios, policy
  evidence, and policy conflicts are injected from workflow state and are never part of
  the response, so there is nothing to restore.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256

from archcompass.domain.base import canonical_json
from archcompass.domain.case import ArchitectureCase, CaseAlternative
from archcompass.domain.consultation import (
    ADRRecord,
    ArchitecturalFinding,
    Claim,
    ClaimClassification,
    ConcernAnalysis,
    ConcernCluster,
    DesignForce,
    FocusedAnalysisPacket,
    RecommendationDisposition,
    RecommendationReport,
    ScenarioEvaluation,
    SupportedStatement,
)
from archcompass.domain.policy import PolicyConflict, canonical_policy_evidence
from archcompass.domain.proposals import (
    AvailableClaim,
    ProposedRecommendation,
    ProposedStatement,
)

#: Report sections keyed by the claim classification that belongs in each.
_SECTION_BY_CLASSIFICATION = {
    ClaimClassification.CONFIRMED_REQUIREMENT: "confirmed_context",
    ClaimClassification.SCENARIO_ASSUMPTION: "assumptions_and_unresolved_questions",
    ClaimClassification.REPOSITORY_OBSERVATION: "repository_observations",
    ClaimClassification.POLICY_GUIDANCE: "relevant_policies",
}


@dataclass(frozen=True)
class SynthesisClaimPool:
    """The claims synthesis may cite, each under a request-local handle."""

    claims_by_ref: dict[str, Claim]
    cluster_ref_by_id: dict[str, str]
    cluster_id_by_ref: dict[str, str]
    cluster_ref_by_claim_ref: dict[str, str]
    available: list[AvailableClaim]

    def claim_refs_for(self, cluster_ref: str) -> set[str]:
        """The evidence claims produced by one concern cluster's analysis."""

        return {
            ref
            for ref, owner in self.cluster_ref_by_claim_ref.items()
            if owner == cluster_ref
        }

    @property
    def refs(self) -> set[str]:
        return set(self.claims_by_ref)

    @property
    def cluster_refs(self) -> set[str]:
        return set(self.cluster_id_by_ref)


@dataclass(frozen=True)
class CompositionOutcome:
    report: RecommendationReport
    actions: list[dict[str, object]]


class ProposalCompositionError(ValueError):
    """The proposal cannot be composed into a valid report."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def build_claim_pool(
    *,
    case: ArchitectureCase,
    clusters: list[ConcernCluster],
    analyses: list[ConcernAnalysis],
) -> SynthesisClaimPool:
    """Offer every citable claim under a short handle.

    Concern-analysis claims keep the identity assigned when their cluster was analysed,
    because report findings must cite claims from their own focused packet. Case
    statements become claims of the matching classification.
    """

    cluster_ref_by_id = {
        cluster.cluster_id: f"C{ordinal}"
        for ordinal, cluster in enumerate(clusters, start=1)
    }
    claims_by_ref: dict[str, Claim] = {}
    available: list[AvailableClaim] = []

    ordinal = 0
    for analysis in analyses:
        cluster_ref = cluster_ref_by_id.get(analysis.cluster_id)
        for claim in analysis.findings:
            ordinal += 1
            ref = f"E{ordinal}"
            claims_by_ref[ref] = claim
            available.append(
                AvailableClaim(
                    ref=ref,
                    text=claim.text,
                    classification=claim.classification,
                    cluster_ref=cluster_ref,
                )
            )

    case_statements = (
        [(item, ClaimClassification.CONFIRMED_REQUIREMENT) for item in case.confirmed_facts]
        + [(item, ClaimClassification.DERIVED_CONSTRAINT) for item in case.derived_constraints]
        + [
            (item, ClaimClassification.SCENARIO_ASSUMPTION)
            for item in [*case.assumptions, *case.unresolved_questions]
        ]
    )
    for statement, classification in case_statements:
        ordinal += 1
        ref = f"E{ordinal}"
        claims_by_ref[ref] = Claim(
            claim_id=statement.id,
            text=statement.text,
            classification=classification,
        )
        available.append(
            AvailableClaim(
                ref=ref,
                text=statement.text,
                classification=classification,
            )
        )

    return SynthesisClaimPool(
        claims_by_ref=claims_by_ref,
        cluster_ref_by_id=cluster_ref_by_id,
        cluster_id_by_ref={ref: cluster_id for cluster_id, ref in cluster_ref_by_id.items()},
        cluster_ref_by_claim_ref={
            item.ref: item.cluster_ref
            for item in available
            if item.cluster_ref is not None
        },
        available=available,
    )


def validate_proposal(
    proposal: ProposedRecommendation,
    *,
    pool: SynthesisClaimPool,
) -> list[str]:
    """Report every reason the proposal cannot be composed, without raising."""

    errors: list[str] = []
    authored_refs = {claim.ref for claim in proposal.advisor_claims}
    if overlap := authored_refs & pool.refs:
        errors.append(
            f"Advisor claim handles collide with supplied claims: {sorted(overlap)}"
        )
    known_refs = pool.refs | authored_refs

    for ordinal, statement in enumerate(proposal.statements(), start=1):
        if unknown := set(statement.claim_refs) - known_refs:
            errors.append(
                f"Statement {ordinal} cites unknown claim handles: {sorted(unknown)}"
            )

    try:
        RecommendationDisposition(proposal.disposition)
    except ValueError:
        errors.append(
            f"Unknown recommendation disposition: {proposal.disposition!r}"
        )

    covered_clusters: set[str] = set()
    for ordinal, finding in enumerate(proposal.findings, start=1):
        cluster_id = pool.cluster_id_by_ref.get(finding.cluster_ref)
        if cluster_id is None:
            errors.append(
                f"Finding {ordinal} cites unknown concern cluster {finding.cluster_ref!r}"
            )
            continue
        covered_clusters.add(cluster_id)
        if unknown := set(finding.claim_refs) - known_refs:
            errors.append(
                f"Finding {ordinal} cites unknown claim handles: {sorted(unknown)}"
            )
            continue
        outside = [
            ref
            for ref in finding.claim_refs
            if pool.cluster_ref_by_claim_ref.get(ref, finding.cluster_ref)
            != finding.cluster_ref
        ]
        if outside:
            errors.append(
                f"Finding {ordinal} cites claims from another concern cluster: {sorted(outside)}"
            )
        own_cluster_refs = pool.claim_refs_for(finding.cluster_ref)
        if own_cluster_refs and not own_cluster_refs & set(finding.claim_refs):
            errors.append(
                f"Finding {ordinal} cites no evidence claim from its own concern cluster"
            )

    if missing := set(pool.cluster_id_by_ref.values()) - covered_clusters:
        missing_refs = sorted(pool.cluster_ref_by_id[cluster_id] for cluster_id in missing)
        errors.append(f"No finding was produced for concern clusters: {missing_refs}")
    return errors


def compose_recommendation(
    proposal: ProposedRecommendation,
    *,
    pool: SynthesisClaimPool,
    forces: list[DesignForce],
    alternatives: list[CaseAlternative],
    scenarios: list[ScenarioEvaluation],
    analyses: list[ConcernAnalysis],
    packets: list[FocusedAnalysisPacket],
) -> CompositionOutcome:
    """Build the persisted report. Raises `ProposalCompositionError` if invalid."""

    errors = validate_proposal(proposal, pool=pool)
    if errors:
        raise ProposalCompositionError(errors)

    actions: list[dict[str, object]] = []
    claims_by_ref = dict(pool.claims_by_ref)
    for authored in proposal.advisor_claims:
        claims_by_ref[authored.ref] = Claim(
            claim_id=_authored_claim_id(authored.text, authored.classification),
            text=authored.text,
            classification=authored.classification,
        )

    cited_refs = {
        ref
        for statement in proposal.statements()
        for ref in statement.claim_refs
    } | {ref for finding in proposal.findings for ref in finding.claim_refs}
    cited_claims = _unique_claims(
        claims_by_ref[ref] for ref in sorted(cited_refs, key=_ref_order)
    )

    sections: dict[str, list[Claim]] = {name: [] for name in _SECTION_BY_CLASSIFICATION.values()}
    for claim in cited_claims:
        section = _SECTION_BY_CLASSIFICATION.get(claim.classification)
        if section is not None:
            sections[section].append(claim)

    findings = [
        ArchitecturalFinding(
            finding_id=f"FIND-{ordinal:03d}",
            title=finding.title,
            summary=finding.summary,
            concern_cluster_id=pool.cluster_id_by_ref[finding.cluster_ref],
            importance=finding.importance,
            importance_rationale=finding.importance_rationale,
            confidence=finding.confidence,
            consequence=finding.consequence,
            claim_ids=_unique_ids(
                claims_by_ref[ref].claim_id for ref in finding.claim_refs
            ),
            recommended_response=finding.recommended_response,
            uncertainty=list(finding.uncertainty),
        )
        for ordinal, finding in enumerate(proposal.findings, start=1)
    ]

    def compose(statement: ProposedStatement) -> SupportedStatement:
        return SupportedStatement(
            text=statement.text,
            classification=statement.classification,
            supporting_claim_ids=_unique_ids(
                claims_by_ref[ref].claim_id for ref in statement.claim_refs
            ),
        )

    policy_evidence = canonical_policy_evidence(
        item for packet in packets for item in packet.policies
    )
    policy_conflicts = _canonical_policy_conflicts(
        analyses,
        allowed_policy_ids={item.id for item in policy_evidence},
    )
    actions.append(
        {
            "kind": "composed_report_from_proposal",
            "claim_count": len(cited_claims),
            "authored_claim_count": len(proposal.advisor_claims),
            "finding_count": len(findings),
        }
    )

    report = RecommendationReport(
        schema_version=3,
        disposition=RecommendationDisposition(proposal.disposition),
        decision_summary=compose(proposal.decision_summary),
        problem_and_desired_outcome=proposal.problem_and_desired_outcome,
        confirmed_context=sections["confirmed_context"],
        assumptions_and_unresolved_questions=sections["assumptions_and_unresolved_questions"],
        important_design_forces=forces,
        findings=findings,
        repository_observations=sections["repository_observations"],
        relevant_policies=sections["relevant_policies"],
        policy_evidence=policy_evidence,
        policy_conflicts=policy_conflicts,
        recommended_architecture=compose(proposal.recommended_architecture),
        responsibility_allocation=[compose(item) for item in proposal.responsibility_allocation],
        conceptual_interfaces=[compose(item) for item in proposal.conceptual_interfaces],
        alternatives_considered=alternatives,
        scenario_analysis=scenarios,
        change_amplification_analysis=compose(proposal.change_amplification_analysis),
        trade_offs=[compose(item) for item in proposal.trade_offs],
        implementation_sequence=[compose(item) for item in proposal.implementation_sequence],
        confidence=proposal.confidence,
        reversal_conditions=[compose(item) for item in proposal.reversal_conditions],
        revisit_triggers=[compose(item) for item in proposal.revisit_triggers],
        adr=ADRRecord(
            title=proposal.adr.title,
            status=proposal.adr.status,
            context=proposal.adr.context,
            decision=compose(proposal.adr.decision),
            consequences=[compose(item) for item in proposal.adr.consequences],
        ),
        evidence_appendix=cited_claims,
    )
    return CompositionOutcome(report=report, actions=actions)


def proposal_content_hash(proposal: ProposedRecommendation) -> str:
    """A stable identity for the exact response that produced a report."""

    return sha256(canonical_json(proposal).encode("utf-8")).hexdigest()


def _authored_claim_id(text: str, classification: ClaimClassification) -> str:
    digest = sha256(f"{classification}\0{text}".encode()).hexdigest()
    return f"claim_{digest[:32]}"


def _ref_order(ref: str) -> tuple[str, int, str]:
    """Order handles by prefix then numeric suffix so composition is deterministic."""

    prefix = ref[:1]
    suffix = ref[1:]
    return (prefix, int(suffix) if suffix.isdigit() else 0, ref)


def _unique_ids(claim_ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(claim_ids))


def _unique_claims(claims: Iterable[Claim]) -> list[Claim]:
    unique: dict[str, Claim] = {}
    for claim in claims:
        unique.setdefault(claim.claim_id, claim)
    return list(unique.values())


def _canonical_policy_conflicts(
    analyses: list[ConcernAnalysis],
    *,
    allowed_policy_ids: set[str],
) -> list[PolicyConflict]:
    """Carry forward exactly the conflicts concern analysis already validated."""

    unique: dict[str, PolicyConflict] = {}
    for analysis in analyses:
        for conflict in analysis.policy_conflicts:
            if not set(conflict.policy_ids) <= allowed_policy_ids:
                continue
            unique.setdefault(canonical_json(conflict), conflict)
    return list(unique.values())


