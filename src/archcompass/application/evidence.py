"""Deterministic evidence validation and one-pass conservative repair."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from archcompass.domain.atlas import AtlasNode
from archcompass.domain.consultation import (
    Claim,
    ClaimClassification,
    RecommendationReport,
    SupportedStatement,
)


@dataclass(frozen=True)
class EvidenceRepairOutcome:
    report: RecommendationReport
    actions: list[str]


def validate_report_evidence(
    report: RecommendationReport,
    *,
    allowed_nodes: dict[str, AtlasNode],
    allowed_policy_ids: set[str],
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
        if statement.legacy:
            continue
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
        if location.end_line < location.start_line:
            errors.append(f"Claim {claim.claim_id} source span is reversed")
        if (
            node.start_line is None
            or node.end_line is None
            or location.start_line < node.start_line
            or location.end_line > node.end_line
        ):
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
) -> EvidenceRepairOutcome:
    actions: list[str] = []
    valid_claim_ids: set[str] = set()
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
        if statement.legacy:
            return statement
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


def repair_report_evidence(
    report: RecommendationReport,
    *,
    allowed_nodes: dict[str, AtlasNode],
    allowed_policy_ids: set[str],
) -> RecommendationReport:
    """Schema-v1 API compatibility; new callers should retain the repair history."""
    return repair_report_evidence_with_history(
        report,
        allowed_nodes=allowed_nodes,
        allowed_policy_ids=allowed_policy_ids,
    ).report


def _reference_invalid(
    node_id: str,
    location: object,
    allowed_nodes: dict[str, AtlasNode],
) -> bool:
    node = allowed_nodes.get(node_id)
    if node is None:
        return True
    if location is None:
        return False
    start_line = getattr(location, "start_line", None)
    end_line = getattr(location, "end_line", None)
    path = getattr(location, "path", None)
    return bool(
        path != node.path
        or not isinstance(start_line, int)
        or not isinstance(end_line, int)
        or end_line < start_line
        or node.start_line is None
        or node.end_line is None
        or start_line < node.start_line
        or end_line > node.end_line
    )


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
