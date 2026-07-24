from __future__ import annotations

from tests.evaluation.test_conversation_matrix import (
    _answer_context,
    _artifact_id,
    _node,
    _reference,
)

from archcompass.application.conversation_validation import (
    validate_conversation_answer,
)
from archcompass.domain.atlas import (
    AtlasEdge,
    AtlasMetricValue,
    AtlasNode,
    AtlasRelationshipEvidence,
    EdgeType,
    MetricScope,
)
from archcompass.domain.consultation import ClaimClassification
from archcompass.domain.conversation import (
    AnswerClaim,
    AnswerStatement,
    AnswerStatementKind,
    ConversationAnswer,
    ConversationEvidenceKind,
    ReportConversationContext,
    ReportQuestionType,
)


def _pinned_nodes(context: ReportConversationContext) -> dict[str, AtlasNode]:
    summaries = {
        item.node_id: item
        for finding in context.retrieved_findings
        for item in finding.affected_locations
    }
    summaries.update(
        {
            item.node_id: item
            for evidence in context.retrieved_atlas_evidence
            for item in evidence.nodes
        }
    )
    return {
        node_id: AtlasNode(
            atlas_id=node_id,
            path=node.path,
            symbol_name=node.qualified_name.rsplit(".", maxsplit=1)[-1],
            qualified_name=node.qualified_name,
            node_type=node.node_type,
            start_line=node.location.start_line if node.location else None,
            end_line=node.location.end_line if node.location else None,
            is_public=node.is_public,
            parser_version="test",
        )
        for node_id, node in summaries.items()
    }


def _answer(claim: AnswerClaim) -> ConversationAnswer:
    return ConversationAnswer(
        direct_answer=AnswerStatement(
            text=claim.text,
            kind=AnswerStatementKind.DIRECT_ANSWER,
            answer_claim_ids=[claim.claim_id],
        ),
        claims=[claim],
    )


def test_answer_validation_rejects_invented_metric_value() -> None:
    context = _answer_context(
        "Trace the evidence for FIND-003.",
        [ReportQuestionType.EVIDENCE_TRACE],
        finding_ids=["FIND-003"],
    )
    metric = AtlasMetricValue(
        node_id="node-03",
        metric="dependency.fan_in",
        value=7,
        scope=MetricScope.OWNING_MODULE,
        definition="Direct internal modules depending on the owner.",
    )
    metric_reference = _reference(
        ConversationEvidenceKind.ATLAS_METRIC,
        _artifact_id(metric),
        metric,
        node_id=metric.node_id,
    )
    atlas_evidence = context.retrieved_atlas_evidence[0].model_copy(
        update={
            "evidence_references": [
                *context.retrieved_atlas_evidence[0].evidence_references,
                metric_reference,
            ],
            "metrics": [metric],
        }
    )
    context = context.model_copy(
        update={
            "evidence_references": [
                *context.evidence_references,
                metric_reference,
            ],
            "retrieved_atlas_evidence": [atlas_evidence],
        }
    )
    claim = AnswerClaim(
        text="dependency.fan_in is 999 for node-03.",
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        evidence_ids=[metric_reference.evidence_id],
    )

    errors = validate_conversation_answer(
        _answer(claim),
        context=context,
        atlas_nodes=_pinned_nodes(context),
    )

    assert any("numeric values absent" in error and "999" in error for error in errors)


def test_answer_validation_accepts_exact_metric_value() -> None:
    context = _answer_context(
        "Trace the evidence for FIND-003.",
        [ReportQuestionType.EVIDENCE_TRACE],
        finding_ids=["FIND-003"],
    )
    metric = AtlasMetricValue(
        node_id="node-03",
        metric="dependency.fan_in",
        value=7,
        scope=MetricScope.OWNING_MODULE,
        definition="Direct internal modules depending on the owner.",
    )
    metric_reference = _reference(
        ConversationEvidenceKind.ATLAS_METRIC,
        _artifact_id(metric),
        metric,
        node_id=metric.node_id,
    )
    atlas_evidence = context.retrieved_atlas_evidence[0].model_copy(
        update={
            "evidence_references": [
                *context.retrieved_atlas_evidence[0].evidence_references,
                metric_reference,
            ],
            "metrics": [metric],
        }
    )
    context = context.model_copy(
        update={
            "evidence_references": [
                *context.evidence_references,
                metric_reference,
            ],
            "retrieved_atlas_evidence": [atlas_evidence],
        }
    )
    claim = AnswerClaim(
        text="dependency.fan_in is 7 for node-03.",
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        evidence_ids=[metric_reference.evidence_id],
    )

    errors = validate_conversation_answer(
        _answer(claim),
        context=context,
        atlas_nodes=_pinned_nodes(context),
    )

    assert errors == []


def test_answer_validation_rejects_invented_relationship_type() -> None:
    context = _answer_context(
        "Trace the evidence for FIND-003.",
        [ReportQuestionType.EVIDENCE_TRACE],
        finding_ids=["FIND-003"],
    )
    source = _node(3)
    target = _node(4)
    relationship = AtlasRelationshipEvidence(
        edge_id="edge-03-04",
        edge_type=EdgeType.IMPORTS,
        source=source,
        target=target,
        confidence=1.0,
        location=source.location,
    )
    edge = AtlasEdge(
        edge_id=relationship.edge_id,
        source_id=source.node_id,
        target_id=target.node_id,
        edge_type=relationship.edge_type,
        confidence=relationship.confidence,
        location=relationship.location,
    )
    source_reference = _reference(
        ConversationEvidenceKind.ATLAS_NODE,
        source.node_id,
        source,
        node_id=source.node_id,
        location=source.location,
    )
    target_reference = _reference(
        ConversationEvidenceKind.ATLAS_NODE,
        target.node_id,
        target,
        node_id=target.node_id,
        location=target.location,
    )
    edge_reference = _reference(
        ConversationEvidenceKind.ATLAS_RELATIONSHIP,
        edge.edge_id,
        edge,
        node_id=source.node_id,
        location=edge.location,
    )
    atlas_evidence = context.retrieved_atlas_evidence[0].model_copy(
        update={
            "evidence_references": [
                source_reference,
                target_reference,
                edge_reference,
            ],
            "ordered_node_ids": [source.node_id, target.node_id],
            "nodes": [source, target],
            "relationships": [relationship],
            "excerpts": [],
        }
    )
    retained_non_atlas = [
        reference
        for reference in context.evidence_references
        if reference.kind
        not in {
            ConversationEvidenceKind.ATLAS_NODE,
            ConversationEvidenceKind.SOURCE_EXCERPT,
        }
    ]
    context = context.model_copy(
        update={
            "evidence_references": [
                *retained_non_atlas,
                source_reference,
                target_reference,
                edge_reference,
            ],
            "retrieved_atlas_evidence": [atlas_evidence],
        }
    )
    claim = AnswerClaim(
        text="node-03 calls node-04.",
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        evidence_ids=[edge_reference.evidence_id],
    )

    errors = validate_conversation_answer(
        _answer(claim),
        context=context,
        atlas_nodes=_pinned_nodes(context),
    )

    assert any("relationship types absent" in error and "calls" in error for error in errors)
