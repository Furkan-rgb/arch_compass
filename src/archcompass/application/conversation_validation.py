"""Evidence validation for structured report-conversation answers and summaries."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import cast

from pydantic import BaseModel

from archcompass.domain.atlas import AtlasEdge, AtlasNode, SourceLocation
from archcompass.domain.base import canonical_json
from archcompass.domain.consultation import ClaimClassification
from archcompass.domain.conversation import (
    ConversationAnswer,
    ConversationEvidenceKind,
    ConversationEvidenceReference,
    ConversationEvidenceScope,
    ConversationSummary,
    ExplainMetricDefinitionAction,
    ReportConversationContext,
)
from archcompass.domain.evidence_rules import location_within, node_source_span

_REPOSITORY_EVIDENCE_KINDS = {
    ConversationEvidenceKind.ATLAS_NODE,
    ConversationEvidenceKind.ATLAS_RELATIONSHIP,
    ConversationEvidenceKind.ATLAS_METRIC,
    ConversationEvidenceKind.ATLAS_SIGNAL,
    ConversationEvidenceKind.SOURCE_EXCERPT,
    ConversationEvidenceKind.TEST,
    ConversationEvidenceKind.METRIC_DEFINITION,
}

_SENSITIVE_IDENTIFIER_RE = re.compile(
    r"\b(?:FIND-\d{3}|(?:node|edge|claim|policy|test|metric|signal)"
    r"[_-][a-zA-Z0-9_.:-]+)\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(
    r"(?<![a-zA-Z0-9_-])-?\d+(?:\.\d+)?(?![a-zA-Z0-9_-])"
)
_METRIC_RE = re.compile(
    r"\b(?:local|dependency|change_amplification|cognitive_scope)\.[a-z_]+\b",
    re.IGNORECASE,
)
_PATH_RE = re.compile(
    r"\b(?:[a-zA-Z0-9_.-]+/)+[a-zA-Z0-9_.-]+"
    r"\.(?:py|pyi|js|jsx|ts|tsx|json|ya?ml|toml|md)\b"
)
_LOCATION_RE = re.compile(
    r"(?P<path>(?:[a-zA-Z0-9_.-]+/)+[a-zA-Z0-9_.-]+\."
    r"(?:py|pyi|js|jsx|ts|tsx|json|ya?ml|toml|md)):"
    r"(?P<start>\d+)(?:-(?P<end>\d+))?"
)
_RELATIONSHIP_WORD_RE = re.compile(
    r"\b(contains|imports|calls|inherits|implements|references|tests|configures)\b",
    re.IGNORECASE,
)
_REPOSITORY_ARTIFACT_ID_RE = re.compile(
    r"\b(?:node|edge|test|metric|signal)[_-][a-zA-Z0-9_.:-]+\b",
    re.IGNORECASE,
)


def validate_conversation_answer(
    answer: ConversationAnswer,
    *,
    context: ReportConversationContext,
    atlas_nodes: dict[str, AtlasNode],
    original_evidence_registry: Mapping[str, set[str]] | None = None,
) -> list[str]:
    errors = validate_conversation_context(
        context,
        atlas_nodes=atlas_nodes,
        original_evidence_registry=original_evidence_registry,
    )
    allowed_finding_ids = {item.finding_id for item in context.finding_digests}
    allowed_claim_ids = {item.claim_id for item in context.retrieved_claims}
    evidence_by_id = {
        item.evidence_id: item for item in context.evidence_references
    }
    evidence_payloads = _conversation_evidence_payloads(context)
    findings_by_id = {
        item.finding_id: item for item in context.retrieved_findings
    }
    finding_digests_by_id = {
        item.finding_id: item for item in context.finding_digests
    }
    report_claims_by_id = {
        item.claim_id: item for item in context.retrieved_claims
    }
    policies_by_id = {
        item.policy.id: item for item in context.retrieved_policies
    }
    allowed_policy_ids = {item.policy.id for item in context.retrieved_policies}
    if unknown := set(answer.relevant_finding_ids) - allowed_finding_ids:
        errors.append(f"Answer references unknown findings: {sorted(unknown)}")
    claim_ids = [claim.claim_id for claim in answer.claims]
    if len(claim_ids) != len(set(claim_ids)):
        errors.append("Answer claim IDs must be unique")
    claims_by_id = {item.claim_id: item for item in answer.claims}
    claim_support_values: dict[str, list[str | BaseModel]] = {}
    for claim in answer.claims:
        if unknown := set(claim.finding_ids) - allowed_finding_ids:
            errors.append(
                f"Answer claim {claim.claim_id} references unknown findings: {sorted(unknown)}"
            )
        if unknown := set(claim.report_claim_ids) - allowed_claim_ids:
            errors.append(
                f"Answer claim {claim.claim_id} references unsupplied report claims: "
                f"{sorted(unknown)}"
            )
        if unknown := set(claim.evidence_ids) - set(evidence_by_id):
            errors.append(
                f"Answer claim {claim.claim_id} references unsupplied evidence: "
                f"{sorted(unknown)}"
            )
        if unknown := set(claim.policy_ids) - allowed_policy_ids:
            errors.append(
                f"Answer claim {claim.claim_id} references unsupplied policies: "
                f"{sorted(unknown)}"
            )
        cited_references = [
            evidence_by_id[evidence_id]
            for evidence_id in claim.evidence_ids
            if evidence_id in evidence_by_id
        ]
        repository_references = [
            item
            for item in cited_references
            if item.kind in _REPOSITORY_EVIDENCE_KINDS
        ]
        if (
            claim.classification == ClaimClassification.REPOSITORY_OBSERVATION
            and not repository_references
        ):
            errors.append(
                f"Repository observation {claim.claim_id} has no exact repository artifact"
            )
        if (
            claim.classification == ClaimClassification.POLICY_GUIDANCE
            and not claim.policy_ids
        ):
            errors.append(f"Policy guidance {claim.claim_id} has no policy reference")
        for reference in repository_references:
            if reference.node_id is None:
                if reference.kind not in {
                    ConversationEvidenceKind.ATLAS_RELATIONSHIP,
                    ConversationEvidenceKind.TEST,
                }:
                    errors.append(
                        f"Repository artifact {reference.evidence_id} has no Atlas node"
                    )
                continue
            node = atlas_nodes.get(reference.node_id)
            if node is None:
                errors.append(
                    f"Evidence {reference.evidence_id} references a node outside the pinned Atlas"
                )
                continue
            location = reference.location
            if location is None:
                if reference.kind in {
                    ConversationEvidenceKind.ATLAS_NODE,
                    ConversationEvidenceKind.ATLAS_SIGNAL,
                    ConversationEvidenceKind.SOURCE_EXCERPT,
                }:
                    errors.append(
                        f"Repository artifact {reference.evidence_id} has no source location"
                    )
                continue
            if location.path != node.path:
                errors.append(
                    f"Repository reference path does not match pinned node {node.atlas_id}"
                )
            if reference.kind is not ConversationEvidenceKind.SOURCE_EXCERPT and (
                not location_within(node_source_span(node), location)
            ):
                errors.append(
                    f"Repository reference span exceeds pinned node {node.atlas_id}"
                )
        support_values = [
            value
            for evidence_id in claim.evidence_ids
            for value in evidence_payloads.get(evidence_id, [])
        ]
        support_values.extend(
            findings_by_id.get(finding_id)
            or finding_digests_by_id[finding_id]
            for finding_id in claim.finding_ids
            if finding_id in findings_by_id or finding_id in finding_digests_by_id
        )
        support_values.extend(
            report_claims_by_id[claim_id]
            for claim_id in claim.report_claim_ids
            if claim_id in report_claims_by_id
        )
        support_values.extend(
            policies_by_id[policy_id]
            for policy_id in claim.policy_ids
            if policy_id in policies_by_id
        )
        claim_support_values[claim.claim_id] = support_values
        errors.extend(
            _validate_supported_facts(
                claim.text,
                support_values=support_values,
                label=f"Answer claim {claim.claim_id}",
                strict=(
                    claim.classification
                    is ClaimClassification.REPOSITORY_OBSERVATION
                ),
            )
        )
        repository_scopes = {item.scope for item in repository_references}
        normalized_claim_text = claim.text.casefold()
        if (
            "original run" in normalized_claim_text
            and ConversationEvidenceScope.ADDITIONAL_CONVERSATION
            in repository_scopes
        ):
            errors.append(
                f"Answer claim {claim.claim_id} presents additional evidence as original"
            )
        if (
            "additional repository evidence" in normalized_claim_text
            and ConversationEvidenceScope.ORIGINAL_RUN in repository_scopes
        ):
            errors.append(
                f"Answer claim {claim.claim_id} presents original evidence as additional"
            )
    statements = [
        answer.direct_answer,
        *answer.supporting_points,
        *answer.uncertainty,
    ]
    for statement in statements:
        if unknown := set(statement.answer_claim_ids) - set(claims_by_id):
            errors.append(
                f"Answer statement references unknown answer claims: {sorted(unknown)}"
            )
        if unknown := set(statement.finding_ids) - allowed_finding_ids:
            errors.append(
                f"Answer statement references unknown findings: {sorted(unknown)}"
            )
        if unknown := set(statement.report_claim_ids) - allowed_claim_ids:
            errors.append(
                f"Answer statement references unsupplied report claims: {sorted(unknown)}"
            )
        if not (
            statement.answer_claim_ids
            or statement.finding_ids
            or statement.report_claim_ids
        ):
            errors.append("Every rendered answer statement requires explicit support")
        for answer_claim_id in statement.answer_claim_ids:
            claim = claims_by_id.get(answer_claim_id)
            if claim is not None and not (
                claim.evidence_ids
                or claim.finding_ids
                or claim.report_claim_ids
                or claim.policy_ids
            ):
                errors.append(
                    f"Answer statement cites unsupported answer claim {answer_claim_id}"
                )
        statement_support_values: list[str | BaseModel] = []
        statement_support_values.extend(
            value
            for answer_claim_id in statement.answer_claim_ids
            for value in claim_support_values.get(answer_claim_id, [])
        )
        statement_support_values.extend(
            claims_by_id[answer_claim_id].text
            for answer_claim_id in statement.answer_claim_ids
            if answer_claim_id in claims_by_id
        )
        statement_support_values.extend(
            findings_by_id.get(finding_id)
            or finding_digests_by_id[finding_id]
            for finding_id in statement.finding_ids
            if finding_id in findings_by_id or finding_id in finding_digests_by_id
        )
        statement_support_values.extend(
            report_claims_by_id[claim_id]
            for claim_id in statement.report_claim_ids
            if claim_id in report_claims_by_id
        )
        errors.extend(
            _validate_supported_facts(
                statement.text,
                support_values=statement_support_values,
                label=f"Answer {statement.kind.value} statement",
                strict=(
                    bool(
                        _REPOSITORY_ARTIFACT_ID_RE.search(statement.text)
                        or _METRIC_RE.search(statement.text)
                        or _PATH_RE.search(statement.text)
                        or _LOCATION_RE.search(statement.text)
                    )
                    or any(
                        claims_by_id[answer_claim_id].classification
                        is ClaimClassification.REPOSITORY_OBSERVATION
                        for answer_claim_id in statement.answer_claim_ids
                        if answer_claim_id in claims_by_id
                    )
                ),
            )
        )
    foreign_run_ids = {
        match
        for value in [
            *(item.text for item in statements),
            *(item.text for item in answer.claims),
        ]
        for match in re.findall(r"\brun_[a-zA-Z0-9_-]+\b", value)
        if match != context.run_id
    }
    if foreign_run_ids:
        errors.append(
            f"Answer references another consultation run: {sorted(foreign_run_ids)}"
        )
    return list(dict.fromkeys(errors))


def validate_conversation_context(
    context: ReportConversationContext,
    *,
    atlas_nodes: dict[str, AtlasNode],
    original_evidence_registry: Mapping[str, set[str]] | None = None,
) -> list[str]:
    """Recompute exact supplied artifacts instead of trusting provider-facing refs."""
    expected: dict[str, list[ConversationEvidenceReference]] = {}

    def add(
        kind: ConversationEvidenceKind,
        artifact_id: str,
        value: str | BaseModel,
        *,
        node_id: str | None = None,
        location: SourceLocation | None = None,
    ) -> None:
        evidence_id = f"{kind.value}:{artifact_id}"
        serialized = (
            canonical_json({"value": value})
            if isinstance(value, str)
            else canonical_json(value)
        )
        candidate = ConversationEvidenceReference(
            evidence_id=evidence_id,
            kind=kind,
            artifact_id=artifact_id,
            # Candidate matching below deliberately excludes scope. Scope is
            # recomputed against the immutable original-run registry separately.
            scope=ConversationEvidenceScope.ORIGINAL_RUN,
            content_hash=sha256(serialized.encode("utf-8")).hexdigest(),
            node_id=node_id,
            location=location,
        )
        expected.setdefault(evidence_id, []).append(candidate)

    add(
        ConversationEvidenceKind.REPORT_CONTEXT,
        context.report_summary.report_id,
        context.report_summary,
    )
    add(
        ConversationEvidenceKind.REPORT_CONTEXT,
        f"{context.pinned_case.case_id}@{context.pinned_case.revision}",
        context.pinned_case,
    )
    for finding in context.retrieved_findings:
        add(
            ConversationEvidenceKind.FINDING,
            finding.finding_id,
            finding,
        )
        for node in finding.affected_locations:
            add(
                ConversationEvidenceKind.ATLAS_NODE,
                node.node_id,
                node,
                node_id=node.node_id,
                location=node.location,
            )
        for node_id in finding.atlas_node_ids:
            add(
                ConversationEvidenceKind.ATLAS_NODE,
                node_id,
                node_id,
                node_id=node_id,
            )
        for metric in finding.metric_observations:
            add(
                ConversationEvidenceKind.ATLAS_METRIC,
                _artifact_hash(metric),
                metric,
                node_id=metric.node_id,
            )
        for signal in finding.obscurity_signals:
            add(
                ConversationEvidenceKind.ATLAS_SIGNAL,
                _artifact_hash(signal),
                signal,
                node_id=signal.node_id,
                location=signal.location,
            )
    for claim in context.retrieved_claims:
        add(
            ConversationEvidenceKind.REPORT_CLAIM,
            claim.claim_id,
            claim,
        )
    for analysis in context.retrieved_concern_analyses:
        add(
            ConversationEvidenceKind.CONCERN_ANALYSIS,
            analysis.cluster_id,
            analysis,
        )
    for alternative in context.retrieved_alternatives:
        add(
            ConversationEvidenceKind.ALTERNATIVE,
            alternative.id,
            alternative,
        )
    for scenario in context.retrieved_scenarios:
        add(
            ConversationEvidenceKind.SCENARIO,
            _artifact_hash(scenario),
            scenario,
        )
    for policy in context.retrieved_policies:
        add(
            ConversationEvidenceKind.POLICY,
            policy.policy.id,
            policy,
        )
    for atlas_evidence in context.retrieved_atlas_evidence:
        metric_kind = (
            ConversationEvidenceKind.METRIC_DEFINITION
            if isinstance(atlas_evidence.action, ExplainMetricDefinitionAction)
            else ConversationEvidenceKind.ATLAS_METRIC
        )
        for node in atlas_evidence.nodes:
            add(
                ConversationEvidenceKind.ATLAS_NODE,
                node.node_id,
                node,
                node_id=node.node_id,
                location=node.location,
            )
        for node_id in atlas_evidence.ordered_node_ids:
            add(
                ConversationEvidenceKind.ATLAS_NODE,
                node_id,
                node_id,
                node_id=node_id,
            )
        for relationship in atlas_evidence.relationships:
            edge = AtlasEdge(
                edge_id=relationship.edge_id,
                source_id=relationship.source.node_id,
                target_id=relationship.target.node_id,
                edge_type=relationship.edge_type,
                confidence=relationship.confidence,
                location=relationship.location,
            )
            add(
                ConversationEvidenceKind.ATLAS_RELATIONSHIP,
                relationship.edge_id,
                edge,
                node_id=relationship.source.node_id,
                location=relationship.location,
            )
        for metric in atlas_evidence.metrics:
            add(
                metric_kind,
                _artifact_hash(metric),
                metric,
                node_id=metric.node_id,
            )
        for signal in atlas_evidence.signals:
            add(
                ConversationEvidenceKind.ATLAS_SIGNAL,
                _artifact_hash(signal),
                signal,
                node_id=signal.node_id,
                location=signal.location,
            )
        for excerpt in atlas_evidence.excerpts:
            add(
                ConversationEvidenceKind.SOURCE_EXCERPT,
                _artifact_hash(excerpt),
                excerpt,
                node_id=excerpt.node_id,
                location=excerpt.location,
            )
        for test_id in atlas_evidence.test_ids:
            add(
                ConversationEvidenceKind.TEST,
                test_id,
                test_id,
                node_id=test_id,
            )

    errors: list[str] = []
    actual_by_id = {
        item.evidence_id: item for item in context.evidence_references
    }
    for evidence_id in expected:
        if evidence_id not in actual_by_id:
            errors.append(f"Supplied artifact {evidence_id} has no exact evidence reference")
    for evidence_id, actual in actual_by_id.items():
        candidates = expected.get(evidence_id)
        if candidates is None:
            errors.append(
                f"Evidence reference {evidence_id} has no supplied artifact"
            )
            continue
        if not any(_same_exact_artifact(actual, candidate) for candidate in candidates):
            errors.append(
                f"Evidence reference {evidence_id} does not match its supplied artifact"
            )
        if actual.kind is ConversationEvidenceKind.REPORT_CONTEXT:
            expected_scope = ConversationEvidenceScope.ORIGINAL_RUN
        elif original_evidence_registry is not None:
            expected_scope = (
                ConversationEvidenceScope.ORIGINAL_RUN
                if actual.content_hash
                in original_evidence_registry.get(actual.evidence_id, set())
                else ConversationEvidenceScope.ADDITIONAL_CONVERSATION
            )
        else:
            expected_scope = actual.scope
        if actual.scope is not expected_scope:
            errors.append(
                f"Evidence reference {evidence_id} has an incorrect evidence scope"
            )

    for reference in context.evidence_references:
        if reference.node_id is None:
            continue
        node = atlas_nodes.get(reference.node_id)
        if node is None:
            errors.append(
                f"Evidence {reference.evidence_id} references a node outside the pinned Atlas"
            )
            continue
        location = reference.location
        if location is None:
            continue
        if location.path != node.path:
            errors.append(
                f"Repository reference path does not match pinned node {node.atlas_id}"
            )
        if reference.kind is not ConversationEvidenceKind.SOURCE_EXCERPT and (
            not location_within(node_source_span(node), location)
        ):
            errors.append(
                f"Repository reference span exceeds pinned node {node.atlas_id}"
            )
    return list(dict.fromkeys(errors))


def _conversation_evidence_payloads(
    context: ReportConversationContext,
) -> dict[str, list[str | BaseModel]]:
    """Index the exact transient values represented by each supplied evidence ID."""
    payloads: dict[str, list[str | BaseModel]] = {}

    def add(
        kind: ConversationEvidenceKind,
        artifact_id: str,
        value: str | BaseModel,
    ) -> None:
        payloads.setdefault(f"{kind.value}:{artifact_id}", []).append(value)

    add(
        ConversationEvidenceKind.REPORT_CONTEXT,
        context.report_summary.report_id,
        context.report_summary,
    )
    add(
        ConversationEvidenceKind.REPORT_CONTEXT,
        f"{context.pinned_case.case_id}@{context.pinned_case.revision}",
        context.pinned_case,
    )
    for finding in context.retrieved_findings:
        add(ConversationEvidenceKind.FINDING, finding.finding_id, finding)
        for node in finding.affected_locations:
            add(ConversationEvidenceKind.ATLAS_NODE, node.node_id, node)
        for node_id in finding.atlas_node_ids:
            add(ConversationEvidenceKind.ATLAS_NODE, node_id, node_id)
        for metric in finding.metric_observations:
            add(
                ConversationEvidenceKind.ATLAS_METRIC,
                _artifact_hash(metric),
                metric,
            )
        for signal in finding.obscurity_signals:
            add(
                ConversationEvidenceKind.ATLAS_SIGNAL,
                _artifact_hash(signal),
                signal,
            )
    for claim in context.retrieved_claims:
        add(ConversationEvidenceKind.REPORT_CLAIM, claim.claim_id, claim)
    for analysis in context.retrieved_concern_analyses:
        add(
            ConversationEvidenceKind.CONCERN_ANALYSIS,
            analysis.cluster_id,
            analysis,
        )
    for alternative in context.retrieved_alternatives:
        add(ConversationEvidenceKind.ALTERNATIVE, alternative.id, alternative)
    for scenario in context.retrieved_scenarios:
        add(ConversationEvidenceKind.SCENARIO, _artifact_hash(scenario), scenario)
    for policy in context.retrieved_policies:
        add(ConversationEvidenceKind.POLICY, policy.policy.id, policy)
    for atlas_evidence in context.retrieved_atlas_evidence:
        for reference in atlas_evidence.evidence_references:
            if atlas_evidence.query_summary:
                payloads.setdefault(reference.evidence_id, []).append(
                    atlas_evidence.query_summary
                )
            if atlas_evidence.unavailable_reason:
                payloads.setdefault(reference.evidence_id, []).append(
                    atlas_evidence.unavailable_reason
                )
        metric_kind = (
            ConversationEvidenceKind.METRIC_DEFINITION
            if isinstance(atlas_evidence.action, ExplainMetricDefinitionAction)
            else ConversationEvidenceKind.ATLAS_METRIC
        )
        for node in atlas_evidence.nodes:
            add(ConversationEvidenceKind.ATLAS_NODE, node.node_id, node)
        for node_id in atlas_evidence.ordered_node_ids:
            add(ConversationEvidenceKind.ATLAS_NODE, node_id, node_id)
        for relationship in atlas_evidence.relationships:
            edge = AtlasEdge(
                edge_id=relationship.edge_id,
                source_id=relationship.source.node_id,
                target_id=relationship.target.node_id,
                edge_type=relationship.edge_type,
                confidence=relationship.confidence,
                location=relationship.location,
            )
            add(
                ConversationEvidenceKind.ATLAS_RELATIONSHIP,
                relationship.edge_id,
                edge,
            )
        for metric in atlas_evidence.metrics:
            add(metric_kind, _artifact_hash(metric), metric)
        for signal in atlas_evidence.signals:
            add(
                ConversationEvidenceKind.ATLAS_SIGNAL,
                _artifact_hash(signal),
                signal,
            )
        for excerpt in atlas_evidence.excerpts:
            add(
                ConversationEvidenceKind.SOURCE_EXCERPT,
                _artifact_hash(excerpt),
                excerpt,
            )
        for test_id in atlas_evidence.test_ids:
            add(ConversationEvidenceKind.TEST, test_id, test_id)
    return payloads


def _validate_supported_facts(
    text: str,
    *,
    support_values: list[str | BaseModel],
    label: str,
    strict: bool,
) -> list[str]:
    """Reject exact-looking repository facts absent from the cited support values."""
    if not strict or not support_values:
        return []
    serialized_values = [
        canonical_json({"value": value})
        if isinstance(value, str)
        else canonical_json(value)
        for value in support_values
    ]
    support_blob = "\n".join(serialized_values).casefold()
    errors: list[str] = []

    mentioned_ids = {
        item.casefold() for item in _SENSITIVE_IDENTIFIER_RE.findall(text)
    }
    supplied_ids = {
        item.casefold()
        for value in serialized_values
        for item in _SENSITIVE_IDENTIFIER_RE.findall(value)
    }
    if unknown := mentioned_ids - supplied_ids:
        errors.append(
            f"{label} states artifact IDs absent from its exact support: "
            f"{sorted(unknown)}"
        )

    mentioned_metrics = {
        item.casefold() for item in _METRIC_RE.findall(text)
    }
    supplied_metrics = {
        item.casefold()
        for value in serialized_values
        for item in _METRIC_RE.findall(value)
    }
    if unknown := mentioned_metrics - supplied_metrics:
        errors.append(
            f"{label} states metrics absent from its exact support: {sorted(unknown)}"
        )

    supplied_numbers = {
        number
        for value in serialized_values
        for number in _decimal_tokens(value)
    }
    if unknown_numbers := _decimal_tokens(text) - supplied_numbers:
        errors.append(
            f"{label} states numeric values absent from its exact support: "
            f"{sorted(str(item) for item in unknown_numbers)}"
        )

    supplied_locations = {
        (path.casefold(), start, end)
        for value in support_values
        for path, start, end in _source_locations(value)
    }
    for match in _LOCATION_RE.finditer(text):
        location = (
            match.group("path").casefold(),
            int(match.group("start")),
            int(match.group("end") or match.group("start")),
        )
        if location not in supplied_locations:
            errors.append(
                f"{label} states source location "
                f"{match.group(0)} absent from its exact support"
            )

    mentioned_paths = {item.casefold() for item in _PATH_RE.findall(text)}
    supplied_paths = {
        path.casefold()
        for value in support_values
        for path, _, _ in _source_locations(value)
    }
    if unknown_paths := mentioned_paths - supplied_paths:
        errors.append(
            f"{label} states source paths absent from its exact support: "
            f"{sorted(unknown_paths)}"
        )

    edge_types = {
        edge_type.casefold()
        for value in support_values
        for edge_type in _edge_types(value)
    }
    mentioned_relationships = {
        item.casefold() for item in _RELATIONSHIP_WORD_RE.findall(text)
    }
    if unknown := mentioned_relationships - edge_types:
        errors.append(
            f"{label} states relationship types absent from its exact support: "
            f"{sorted(unknown)}"
        )

    signal_codes = {
        code.casefold()
        for value in support_values
        for code in _signal_codes(value)
    }
    mentioned_signal_codes = {
        match.group(1).casefold()
        for match in re.finditer(
            r"\bsignal\s+([a-zA-Z0-9_.-]+)\b",
            text,
            flags=re.IGNORECASE,
        )
    }
    if signal_codes and (unknown := mentioned_signal_codes - signal_codes):
        errors.append(
            f"{label} states signal codes absent from its exact support: "
            f"{sorted(unknown)}"
        )

    quoted_values = [
        match.group(1).strip().casefold()
        for match in re.finditer(r"""["']([^"'\n]{4,})["']""", text)
    ]
    has_text_payload = any(
        "text" in value.model_dump()
        for value in support_values
        if isinstance(value, BaseModel)
    )
    if has_text_payload:
        for quoted in quoted_values:
            if quoted not in support_blob:
                errors.append(
                    f"{label} quotes text absent from its exact support"
                )
    return list(dict.fromkeys(errors))


def _decimal_tokens(value: str) -> set[Decimal]:
    result: set[Decimal] = set()
    for match in _NUMBER_RE.finditer(value):
        try:
            result.add(Decimal(match.group(0)))
        except InvalidOperation:
            continue
    return result


def _source_locations(value: str | BaseModel) -> list[tuple[str, int, int]]:
    if isinstance(value, str):
        return []
    return _nested_source_locations(value.model_dump(mode="json"))


def _nested_source_locations(value: object) -> list[tuple[str, int, int]]:
    if isinstance(value, list):
        return [
            location
            for item in cast(list[object], value)
            for location in _nested_source_locations(item)
        ]
    if not isinstance(value, dict):
        return []
    mapping = cast(dict[str, object], value)
    result: list[tuple[str, int, int]] = []
    path = mapping.get("path")
    start = mapping.get("start_line")
    end = mapping.get("end_line")
    if isinstance(path, str) and isinstance(start, int) and isinstance(end, int):
        result.append((path, start, end))
    for nested in mapping.values():
        result.extend(_nested_source_locations(nested))
    return result


def _edge_types(value: str | BaseModel) -> list[str]:
    if isinstance(value, str):
        return []
    dumped = cast(dict[str, object], value.model_dump(mode="json"))
    if {
        "source_id",
        "target_id",
        "edge_type",
    } <= set(dumped) and isinstance(dumped["edge_type"], str):
        return [dumped["edge_type"]]
    return []


def _signal_codes(value: str | BaseModel) -> list[str]:
    if isinstance(value, str):
        return []
    dumped = cast(dict[str, object], value.model_dump(mode="json"))
    code = dumped.get("code")
    if (
        isinstance(code, str)
        and isinstance(dumped.get("message"), str)
        and isinstance(dumped.get("node_id"), str)
    ):
        return [code]
    return []


def _artifact_hash(value: BaseModel) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _same_exact_artifact(
    actual: ConversationEvidenceReference,
    expected: ConversationEvidenceReference,
) -> bool:
    return (
        actual.kind is expected.kind
        and actual.artifact_id == expected.artifact_id
        and actual.content_hash == expected.content_hash
        and actual.node_id == expected.node_id
        and actual.location == expected.location
    )


def validate_conversation_summary(
    summary: ConversationSummary,
    *,
    allowed_finding_ids: set[str],
    allowed_claim_ids: set[str],
    allowed_evidence_ids: set[str] | None = None,
    allowed_node_ids: set[str] | None = None,
    allowed_policy_ids: set[str],
    allowed_source_ordinals: set[int] | None = None,
    user_source_ordinals: set[int] | None = None,
    max_characters: int = 6000,
) -> list[str]:
    errors: list[str] = []
    if not summary.narrative.strip():
        errors.append("Conversation summary must not be blank")
    if len(summary.narrative) > max_characters:
        errors.append(
            f"Conversation summary exceeds {max_characters} characters"
        )
    permitted_evidence_ids = set(allowed_evidence_ids or set())
    permitted_evidence_ids.update(allowed_node_ids or set())
    if unknown := set(summary.discussed_finding_ids) - allowed_finding_ids:
        errors.append(
            f"Conversation summary introduces unknown finding IDs: {sorted(unknown)}"
        )
    if unknown := set(summary.discussed_evidence_ids) - permitted_evidence_ids:
        errors.append(
            f"Conversation summary introduces unknown evidence IDs: {sorted(unknown)}"
        )
    items = [
        *summary.user_corrections,
        *summary.hypotheticals,
        *summary.unresolved_questions,
    ]
    for item in items:
        if unknown := set(item.finding_ids) - allowed_finding_ids:
            errors.append(
                f"Conversation summary item introduces unknown findings: {sorted(unknown)}"
            )
        if unknown := set(item.evidence_ids) - permitted_evidence_ids:
            errors.append(
                f"Conversation summary item introduces unknown evidence: {sorted(unknown)}"
            )
        if allowed_source_ordinals is not None and (
            unknown := set(item.source_ordinals) - allowed_source_ordinals
        ):
            errors.append(
                f"Conversation summary item cites unavailable message ordinals: "
                f"{sorted(unknown)}"
            )
        if user_source_ordinals is not None and (
            invalid := set(item.source_ordinals) - user_source_ordinals
        ):
            errors.append(
                f"Conversation summary item must cite user-message ordinals: "
                f"{sorted(invalid)}"
            )
    text = " ".join(
        [
            summary.narrative,
            *(item.text for item in items),
        ]
    )
    identifiers = set(
        re.findall(
            r"\b(?:FIND-\d{3}|(?:claim|node|policy|pidx|atlas)[_-][a-zA-Z0-9_-]+)\b",
            text,
        )
    )
    allowed_text_ids = (
        allowed_finding_ids
        | allowed_claim_ids
        | permitted_evidence_ids
        | allowed_policy_ids
    )
    if unknown := identifiers - allowed_text_ids:
        errors.append(
            f"Conversation summary introduces unknown evidence IDs: {sorted(unknown)}"
        )
    return list(dict.fromkeys(errors))
