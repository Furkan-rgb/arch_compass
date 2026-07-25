"""Deterministic evidence validation and one-pass conservative repair."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from archcompass.domain.atlas import (
    AtlasMetricValue,
    AtlasNode,
    AtlasNodeEvidence,
    AtlasNodeSummary,
    ObscuritySignal,
    SourceLocation,
)
from archcompass.domain.consultation import (
    ArchitecturalFinding,
    Claim,
    ClaimClassification,
    ConcernAnalysis,
    FocusedAnalysisPacket,
    RecommendationReport,
    SupportedStatement,
)
from archcompass.domain.evidence_rules import location_within, node_source_span


@dataclass(frozen=True)
class EvidenceRepairOutcome:
    report: RecommendationReport
    actions: list[str]


@dataclass(frozen=True)
class CanonicalFindingEvidence:
    """Exact cluster-local artifacts from a validated focused packet."""

    cluster_id: str
    claims: dict[str, Claim]
    nodes: dict[str, AtlasNodeEvidence]
    policy_ids: frozenset[str]


@dataclass(frozen=True)
class FindingCanonicalizationOutcome:
    report: RecommendationReport
    actions: list[dict[str, object]]
    evidence_by_cluster: dict[str, CanonicalFindingEvidence]


def canonicalize_report_findings(
    report: RecommendationReport,
    *,
    packets: list[FocusedAnalysisPacket],
    analyses: list[ConcernAnalysis],
) -> FindingCanonicalizationOutcome:
    """Replace provider-authored finding evidence with exact packet artifacts.

    Providers retain responsibility for a finding's meaning, importance, confidence,
    response, uncertainty, and claim links. A missing cluster is assigned only when
    exactly one focused packet exists; ambiguous multi-cluster output remains invalid.
    Node, location, metric, signal, and policy evidence is an application-owned
    projection of those claim links.
    """

    evidence_by_cluster = _canonical_finding_evidence(packets, analyses)
    sole_cluster_id = (
        next(iter(evidence_by_cluster)) if len(evidence_by_cluster) == 1 else None
    )
    actions: list[dict[str, object]] = []
    findings: list[ArchitecturalFinding] = []
    for ordinal, finding in enumerate(report.findings, start=1):
        expected_id = f"FIND-{ordinal:03d}"
        if finding.concern_cluster_id is None and sole_cluster_id is not None:
            finding = finding.model_copy(
                update={"concern_cluster_id": sole_cluster_id}
            )
            actions.append(
                {
                    "kind": "assigned_single_concern_cluster_to_finding",
                    "finding_id": expected_id,
                    "concern_cluster_id": sole_cluster_id,
                }
            )
        evidence = (
            evidence_by_cluster.get(finding.concern_cluster_id)
            if finding.concern_cluster_id is not None
            else None
        )
        canonical = _project_finding_evidence(
            finding,
            evidence=evidence,
            finding_id=expected_id,
        )
        # Filling in evidence a finding never asserted is projection, not restoration.
        # Only a finding that stated differing evidence has anything to restore.
        if canonical != finding and _asserts_projected_evidence(finding):
            actions.append(
                {
                    "kind": "restored_canonical_finding_evidence",
                    "finding_id": expected_id,
                    "concern_cluster_id": finding.concern_cluster_id,
                    "model_output": _finding_evidence_payload(finding),
                    "canonical_input": _finding_evidence_payload(canonical),
                }
            )
        findings.append(canonical)
    return FindingCanonicalizationOutcome(
        report=report.model_copy(update={"findings": findings}),
        actions=actions,
        evidence_by_cluster=evidence_by_cluster,
    )


def _cluster_owned_claim_ids(
    finding_evidence_by_cluster: dict[str, CanonicalFindingEvidence] | None,
) -> set[str]:
    """Claim IDs that belong to some cluster's focused investigation.

    A claim outside this set is owned by no cluster — a case statement or an advisor
    claim — and belongs to the consultation rather than to one investigation, so any
    finding may rest on it. Only a claim owned by a *different* cluster is foreign.
    Fabricated IDs cannot hide here: an ID absent from the report's claim registry is
    rejected as unknown before scope is considered.
    """

    if finding_evidence_by_cluster is None:
        return set()
    return {
        claim_id
        for evidence in finding_evidence_by_cluster.values()
        for claim_id in evidence.claims
    }


def validate_report_evidence(
    report: RecommendationReport,
    *,
    allowed_nodes: dict[str, AtlasNode],
    allowed_policy_ids: set[str],
    finding_evidence_by_cluster: dict[str, CanonicalFindingEvidence] | None = None,
) -> list[str]:
    errors: list[str] = []
    claims = _all_claims(report)
    claim_registry: dict[str, Claim] = {}
    invalid_claim_ids: set[str] = set()
    for claim in claims:
        prior = claim_registry.get(claim.claim_id)
        if prior is not None and prior != claim:
            errors.append(f"Claim ID {claim.claim_id} is reused for different claims")
            invalid_claim_ids.add(claim.claim_id)
        claim_registry[claim.claim_id] = claim
        claim_errors = _claim_errors(
            claim,
            allowed_nodes=allowed_nodes,
            allowed_policy_ids=allowed_policy_ids,
        )
        if claim_errors:
            invalid_claim_ids.add(claim.claim_id)
            errors.extend(claim_errors)

    for statement in report.supported_statements():
        unknown = [
            claim_id
            for claim_id in statement.supporting_claim_ids
            if claim_id not in claim_registry
        ]
        invalid = [
            claim_id for claim_id in statement.supporting_claim_ids if claim_id in invalid_claim_ids
        ]
        if unknown:
            errors.append(f"Supported statement references unknown claim IDs: {sorted(unknown)}")
        if invalid:
            errors.append(f"Supported statement references invalid claim IDs: {sorted(invalid)}")
        if not statement.supporting_claim_ids:
            errors.append("Supported statement has no supporting claim IDs")

    if not report.findings:
        errors.append("A recommendation report must contain architectural findings")
    cluster_owned_claim_ids = _cluster_owned_claim_ids(finding_evidence_by_cluster)
    for finding in report.findings:
        unknown_claims = set(finding.claim_ids) - set(claim_registry)
        invalid_claims = set(finding.claim_ids) & invalid_claim_ids
        if unknown_claims:
            errors.append(
                f"Finding {finding.finding_id} references unknown claims: "
                f"{sorted(unknown_claims)}"
            )
        if invalid_claims:
            errors.append(
                f"Finding {finding.finding_id} references invalid claims: "
                f"{sorted(invalid_claims)}"
            )
        if unknown_nodes := set(finding.atlas_node_ids) - set(allowed_nodes):
            errors.append(
                f"Finding {finding.finding_id} references unsurfaced Atlas nodes: "
                f"{sorted(unknown_nodes)}"
            )
        if unknown_policies := set(finding.policy_ids) - allowed_policy_ids:
            errors.append(
                f"Finding {finding.finding_id} references unretrieved policies: "
                f"{sorted(unknown_policies)}"
            )
        if finding_evidence_by_cluster is not None:
            evidence = (
                finding_evidence_by_cluster.get(finding.concern_cluster_id)
                if finding.concern_cluster_id is not None
                else None
            )
            if evidence is None:
                errors.append(
                    f"Finding {finding.finding_id} has no matching focused evidence packet"
                )
            else:
                foreign = [
                    claim_id
                    for claim_id in finding.claim_ids
                    if claim_id not in evidence.claims
                    and claim_id in cluster_owned_claim_ids
                ]
                if foreign:
                    errors.append(
                        f"Finding {finding.finding_id} references claims from another "
                        f"concern cluster: {sorted(foreign)}"
                    )
                # Projection reads only this cluster's claims, so passing the finding
                # whole is equivalent to pre-filtering it and says less.
                expected = _project_finding_evidence(
                    finding,
                    evidence=evidence,
                    finding_id=finding.finding_id,
                )
                if finding.atlas_node_ids != expected.atlas_node_ids:
                    errors.append(
                        f"Finding {finding.finding_id} Atlas nodes do not match its "
                        "focused packet"
                    )
                if finding.affected_locations != expected.affected_locations:
                    errors.append(
                        f"Finding {finding.finding_id} locations do not match its "
                        "focused packet"
                    )
                if finding.metric_observations != expected.metric_observations:
                    errors.append(
                        f"Finding {finding.finding_id} metrics do not match its focused packet"
                    )
                if finding.obscurity_signals != expected.obscurity_signals:
                    errors.append(
                        f"Finding {finding.finding_id} signals do not match its focused packet"
                    )
                if finding.policy_ids != expected.policy_ids:
                    errors.append(
                        f"Finding {finding.finding_id} policies do not match its focused packet"
                    )
        for location in finding.affected_locations:
            node = allowed_nodes.get(location.node_id)
            if node is None:
                continue
            if location.path != node.path or location.location is None:
                errors.append(
                    f"Finding {finding.finding_id} location does not match "
                    f"Atlas node {location.node_id}"
                )
                continue
            if _reference_invalid(location.node_id, location.location, allowed_nodes):
                errors.append(
                    f"Finding {finding.finding_id} source span exceeds "
                    f"Atlas node {location.node_id}"
                )

    evidence_policy_ids = {item.id for item in report.policy_evidence}
    invented_evidence = evidence_policy_ids - allowed_policy_ids
    if invented_evidence:
        errors.append(
            "Policy evidence contains policies that were not retrieved: "
            f"{sorted(invented_evidence)}"
        )
    for conflict in report.policy_conflicts:
        unknown = set(conflict.policy_ids) - allowed_policy_ids
        absent = set(conflict.policy_ids) - evidence_policy_ids
        if unknown:
            errors.append(
                f"Policy conflict references policies that were not retrieved: {sorted(unknown)}"
            )
        if absent:
            errors.append(
                f"Policy conflict references policies absent from report evidence: {sorted(absent)}"
            )
    return _deduplicate(errors)


def _claim_errors(
    claim: Claim,
    *,
    allowed_nodes: dict[str, AtlasNode],
    allowed_policy_ids: set[str],
) -> list[str]:
    errors: list[str] = []
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
        location = reference.location
        if claim.classification == ClaimClassification.REPOSITORY_OBSERVATION and location is None:
            errors.append(
                f"Repository observation {claim.claim_id} has no source location for "
                f"{reference.node_id}"
            )
            continue
        if location is None:
            continue
        if location.path != node.path:
            errors.append(f"Claim {claim.claim_id} source path does not match node {node.atlas_id}")
        elif not location_within(node_source_span(node), location):
            errors.append(f"Claim {claim.claim_id} source span exceeds node {node.atlas_id}")
    for policy_id in claim.policy_ids:
        if policy_id not in allowed_policy_ids:
            errors.append(
                f"Claim {claim.claim_id} references policy that was not retrieved: {policy_id}"
            )
    return errors


def repair_report_evidence_with_history(
    report: RecommendationReport,
    *,
    allowed_nodes: dict[str, AtlasNode],
    allowed_policy_ids: set[str],
    finding_evidence_by_cluster: dict[str, CanonicalFindingEvidence] | None = None,
) -> EvidenceRepairOutcome:
    actions: list[str] = []
    valid_claim_ids: set[str] = set()
    valid_claims: dict[str, Claim] = {}
    report_claims = _disambiguate_claim_ids(report, actions)

    def repair_claim(claim: Claim) -> Claim | None:
        claim_errors = _claim_errors(
            claim,
            allowed_nodes=allowed_nodes,
            allowed_policy_ids=allowed_policy_ids,
        )
        # A repository observation is atomic evidence. In particular, an invalid
        # location removes the observation; it is never erased while prose survives.
        if claim.classification == ClaimClassification.REPOSITORY_OBSERVATION and claim_errors:
            actions.append(
                f"Removed repository observation {claim.claim_id}: " + "; ".join(claim_errors)
            )
            return None
        atlas_references = [
            reference
            for reference in claim.atlas_references
            if not _reference_invalid(reference.node_id, reference.location, allowed_nodes)
        ]
        if len(atlas_references) != len(claim.atlas_references):
            actions.append(f"Removed invalid atlas references from claim {claim.claim_id}")
        policy_ids = [
            policy_id for policy_id in claim.policy_ids if policy_id in allowed_policy_ids
        ]
        if len(policy_ids) != len(claim.policy_ids):
            actions.append(f"Removed invalid policy references from claim {claim.claim_id}")
        if claim.classification == ClaimClassification.POLICY_GUIDANCE and not policy_ids:
            actions.append(f"Removed unsupported policy guidance {claim.claim_id}")
            return None
        repaired = claim.model_copy(
            update={
                "atlas_references": atlas_references,
                "policy_ids": policy_ids,
            }
        )
        valid_claim_ids.add(repaired.claim_id)
        valid_claims[repaired.claim_id] = repaired
        return repaired

    updates: dict[str, list[Claim]] = {}
    for field in (
        "confirmed_context",
        "assumptions_and_unresolved_questions",
        "repository_observations",
        "relevant_policies",
        "evidence_appendix",
    ):
        repaired_claims = [
            repaired
            for claim in report_claims[field]
            if (repaired := repair_claim(claim)) is not None
        ]
        updates[field] = _unique_claims(repaired_claims)

    def repair_statement(statement: SupportedStatement) -> SupportedStatement:
        supporting = [
            claim_id for claim_id in statement.supporting_claim_ids if claim_id in valid_claim_ids
        ]
        if supporting != statement.supporting_claim_ids:
            actions.append(
                f"Removed invalid supporting claim IDs from statement: {statement.text[:80]}"
            )
        return statement.model_copy(update={"supporting_claim_ids": supporting})

    policy_evidence = [item for item in report.policy_evidence if item.id in allowed_policy_ids]
    if len(policy_evidence) != len(report.policy_evidence):
        actions.append("Removed policy evidence that was not retrieved")
    evidence_policy_ids = {item.id for item in policy_evidence}
    conflicts = [
        conflict
        for conflict in report.policy_conflicts
        if set(conflict.policy_ids) <= evidence_policy_ids
        and set(conflict.policy_ids) <= allowed_policy_ids
    ]
    if len(conflicts) != len(report.policy_conflicts):
        actions.append("Removed policy conflicts with unsupported policy IDs")

    repaired_findings = []
    cluster_owned_claim_ids = _cluster_owned_claim_ids(finding_evidence_by_cluster)
    for finding in report.findings:
        finding_evidence = (
            finding_evidence_by_cluster.get(finding.concern_cluster_id)
            if finding_evidence_by_cluster is not None
            and finding.concern_cluster_id is not None
            else None
        )
        claim_ids = [
            claim_id
            for claim_id in finding.claim_ids
            if claim_id in valid_claim_ids
            and (
                finding_evidence_by_cluster is None
                or claim_id not in cluster_owned_claim_ids
                or (
                    finding_evidence is not None
                    and claim_id in finding_evidence.claims
                )
            )
        ]
        if claim_ids != finding.claim_ids:
            actions.append(
                f"Removed unsupported or cross-cluster claims from finding "
                f"{finding.finding_id}"
            )
        if not claim_ids:
            actions.append(f"Removed unsupported finding {finding.finding_id}")
            continue
        supported_nodes = {
            reference.node_id
            for claim_id in claim_ids
            for reference in valid_claims[claim_id].atlas_references
        }
        supported_policies = {
            policy_id
            for claim_id in claim_ids
            for policy_id in valid_claims[claim_id].policy_ids
        }
        node_ids = [
            node_id
            for node_id in finding.atlas_node_ids
            if node_id in allowed_nodes and node_id in supported_nodes
        ]
        finding_policy_ids = [
            policy_id
            for policy_id in finding.policy_ids
            if policy_id in allowed_policy_ids and policy_id in supported_policies
        ]
        repaired_findings.append(
            _project_finding_evidence(
                finding.model_copy(
                    update={
                        "claim_ids": claim_ids,
                        "atlas_node_ids": node_ids,
                        "policy_ids": finding_policy_ids,
                        "affected_locations": [
                            item
                            for item in finding.affected_locations
                            if item.node_id in node_ids
                            and item.location is not None
                            and not _reference_invalid(
                                item.node_id,
                                item.location,
                                allowed_nodes,
                            )
                        ],
                        "metric_observations": [
                            item
                            for item in finding.metric_observations
                            if item.node_id in node_ids
                        ],
                        "obscurity_signals": [
                            item
                            for item in finding.obscurity_signals
                            if item.node_id in node_ids
                        ],
                    }
                ),
                evidence=finding_evidence,
                finding_id=finding.finding_id,
            )
        )

    repaired_adr = report.adr.model_copy(
        update={
            "decision": repair_statement(report.adr.decision),
            "consequences": [repair_statement(statement) for statement in report.adr.consequences],
        }
    )
    repaired_report = report.model_copy(
        update={
            **updates,
            "policy_evidence": policy_evidence,
            "policy_conflicts": conflicts,
            "findings": repaired_findings,
            "decision_summary": repair_statement(report.decision_summary),
            "recommended_architecture": repair_statement(report.recommended_architecture),
            "responsibility_allocation": [
                repair_statement(statement) for statement in report.responsibility_allocation
            ],
            "conceptual_interfaces": [
                repair_statement(statement) for statement in report.conceptual_interfaces
            ],
            "change_amplification_analysis": repair_statement(report.change_amplification_analysis),
            "trade_offs": [repair_statement(statement) for statement in report.trade_offs],
            "implementation_sequence": [
                repair_statement(statement) for statement in report.implementation_sequence
            ],
            "reversal_conditions": [
                repair_statement(statement) for statement in report.reversal_conditions
            ],
            "revisit_triggers": [
                repair_statement(statement) for statement in report.revisit_triggers
            ],
            "adr": repaired_adr,
        }
    )
    return EvidenceRepairOutcome(report=repaired_report, actions=actions)


def _disambiguate_claim_ids(
    report: RecommendationReport,
    actions: list[str],
) -> dict[str, list[Claim]]:
    """Re-ID only duplicate claims whose intended support is unambiguous."""
    fields = (
        "confirmed_context",
        "assumptions_and_unresolved_questions",
        "repository_observations",
        "relevant_policies",
        "evidence_appendix",
    )
    claims_by_field = {field: list(getattr(report, field)) for field in fields}
    occurrences: dict[str, list[Claim]] = {}
    for claims in claims_by_field.values():
        for claim in claims:
            occurrences.setdefault(claim.claim_id, []).append(claim)

    support_classifications: dict[str, set[ClaimClassification]] = {}
    for statement in report.supported_statements():
        for claim_id in statement.supporting_claim_ids:
            support_classifications.setdefault(claim_id, set()).add(
                statement.classification
            )

    replacements: dict[tuple[str, str], str] = {}
    occupied_ids = set(occurrences)
    for claim_id, claims in occurrences.items():
        distinct = {claim.model_dump_json(): claim for claim in claims}
        if len(distinct) < 2:
            continue
        classifications = support_classifications.get(claim_id, set())
        if classifications:
            matching = {
                serialized: claim
                for serialized, claim in distinct.items()
                if claim.classification in classifications
            }
            if len(matching) != 1:
                continue
            preferred = next(iter(matching))
        else:
            preferred = claims[0].model_dump_json()

        for serialized, claim in distinct.items():
            if serialized == preferred:
                continue
            digest_input = f"{claim_id}\0{serialized}".encode()
            replacement = f"claim_{sha256(digest_input).hexdigest()[:32]}"
            counter = 1
            while replacement in occupied_ids:
                replacement = (
                    f"claim_{sha256(digest_input + str(counter).encode()).hexdigest()[:32]}"
                )
                counter += 1
            occupied_ids.add(replacement)
            replacements[(claim_id, serialized)] = replacement
            actions.append(
                f"Reassigned duplicate claim ID {claim_id} to {replacement} "
                f"for {claim.classification}: {claim.text[:80]}"
            )

    if not replacements:
        return claims_by_field
    return {
        field: [
            claim.model_copy(
                update={
                    "claim_id": replacements.get(
                        (claim.claim_id, claim.model_dump_json()),
                        claim.claim_id,
                    )
                }
            )
            for claim in claims
        ]
        for field, claims in claims_by_field.items()
    }


def _canonical_finding_evidence(
    packets: list[FocusedAnalysisPacket],
    analyses: list[ConcernAnalysis],
) -> dict[str, CanonicalFindingEvidence]:
    packet_by_cluster: dict[str, FocusedAnalysisPacket] = {}
    for packet in packets:
        cluster_id = packet.cluster.cluster_id
        prior = packet_by_cluster.get(cluster_id)
        if prior is not None and prior != packet:
            raise ValueError(f"Conflicting focused packets for concern cluster {cluster_id}")
        packet_by_cluster[cluster_id] = packet

    analysis_by_cluster: dict[str, ConcernAnalysis] = {}
    for analysis in analyses:
        prior = analysis_by_cluster.get(analysis.cluster_id)
        if prior is not None and prior != analysis:
            raise ValueError(
                f"Conflicting concern analyses for cluster {analysis.cluster_id}"
            )
        analysis_by_cluster[analysis.cluster_id] = analysis

    result: dict[str, CanonicalFindingEvidence] = {}
    for cluster_id, packet in packet_by_cluster.items():
        analysis = analysis_by_cluster.get(cluster_id)
        if analysis is None:
            raise ValueError(f"Focused packet {cluster_id} has no concern analysis")
        claims: dict[str, Claim] = {}
        for claim in analysis.findings:
            prior = claims.get(claim.claim_id)
            if prior is not None and prior != claim:
                raise ValueError(
                    f"Concern cluster {cluster_id} reuses claim ID "
                    f"{claim.claim_id} for different claims"
                )
            claims[claim.claim_id] = claim
        nodes: dict[str, AtlasNodeEvidence] = {}
        for node in packet.node_evidence:
            node_id = node.node.node_id
            prior = nodes.get(node_id)
            if prior is not None and prior != node:
                raise ValueError(
                    f"Focused packet {cluster_id} contains conflicting evidence "
                    f"for Atlas node {node_id}"
                )
            nodes[node_id] = node
        result[cluster_id] = CanonicalFindingEvidence(
            cluster_id=cluster_id,
            claims=claims,
            nodes=nodes,
            policy_ids=frozenset(item.policy.id for item in packet.policies),
        )
    return result


def _project_finding_evidence(
    finding: ArchitecturalFinding,
    *,
    evidence: CanonicalFindingEvidence | None,
    finding_id: str,
) -> ArchitecturalFinding:
    if evidence is None:
        return finding.model_copy(
            update={
                "finding_id": finding_id,
                "atlas_node_ids": [],
                "policy_ids": [],
                "affected_locations": [],
                "metric_observations": [],
                "obscurity_signals": [],
            }
        )
    claims = [
        evidence.claims[claim_id]
        for claim_id in finding.claim_ids
        if claim_id in evidence.claims
    ]
    node_ids = list(
        dict.fromkeys(
            reference.node_id
            for claim in claims
            for reference in claim.atlas_references
            if reference.node_id in evidence.nodes
        )
    )
    policy_ids = list(
        dict.fromkeys(
            policy_id
            for claim in claims
            for policy_id in claim.policy_ids
            if policy_id in evidence.policy_ids
        )
    )
    node_evidence = [
        evidence.nodes[node_id] for node_id in node_ids if node_id in evidence.nodes
    ]
    affected_locations: list[AtlasNodeSummary] = [item.node for item in node_evidence]
    metric_observations: list[AtlasMetricValue] = [
        metric for item in node_evidence for metric in item.metrics
    ]
    obscurity_signals: list[ObscuritySignal] = [
        signal for item in node_evidence for signal in item.signals
    ]
    return finding.model_copy(
        update={
            "finding_id": finding_id,
            "atlas_node_ids": node_ids,
            "policy_ids": policy_ids,
            "affected_locations": affected_locations,
            "metric_observations": metric_observations,
            "obscurity_signals": obscurity_signals,
        }
    )


def _asserts_projected_evidence(finding: ArchitecturalFinding) -> bool:
    """True when the finding stated evidence that projection would have to overwrite."""

    return bool(
        finding.atlas_node_ids
        or finding.policy_ids
        or finding.affected_locations
        or finding.metric_observations
        or finding.obscurity_signals
    )


def _finding_evidence_payload(finding: ArchitecturalFinding) -> dict[str, object]:
    return {
        "finding_id": finding.finding_id,
        "claim_ids": list(finding.claim_ids),
        "atlas_node_ids": list(finding.atlas_node_ids),
        "policy_ids": list(finding.policy_ids),
        "affected_locations": [
            item.model_dump(mode="json") for item in finding.affected_locations
        ],
        "metric_observations": [
            item.model_dump(mode="json") for item in finding.metric_observations
        ],
        "obscurity_signals": [
            item.model_dump(mode="json") for item in finding.obscurity_signals
        ],
    }


def _reference_invalid(
    node_id: str,
    location: SourceLocation | None,
    allowed_nodes: dict[str, AtlasNode],
) -> bool:
    """An unknown node is always invalid; a cited span must lie inside its node."""

    node = allowed_nodes.get(node_id)
    if node is None:
        return True
    if location is None:
        return False
    return not location_within(node_source_span(node), location)


def _all_claims(report: RecommendationReport) -> list[Claim]:
    return [
        *report.confirmed_context,
        *report.assumptions_and_unresolved_questions,
        *report.repository_observations,
        *report.relevant_policies,
        *report.evidence_appendix,
    ]


def _unique_claims(claims: list[Claim]) -> list[Claim]:
    unique: dict[str, Claim] = {}
    for claim in claims:
        unique.setdefault(claim.model_dump_json(), claim)
    return list(unique.values())


def _deduplicate(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
