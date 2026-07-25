"""Replay conversation answers through validation to pin support and fact rules.

Strict prose fact-checking applies to repository-observation claims and the
statements that carry them. Within that scope the checks split into two groups:

* High-precision checks (artifact IDs, source locations, paths) are contract
  guarantees. They must stay hard failures through WS4.
* Heuristic checks (bare numbers, relationship words) produce false positives on
  prose that fabricates nothing. WS4 demotes those to audit warnings; the xfail
  tests below become passing assertions at that point.
"""

from __future__ import annotations

from archcompass.application.conversation_validation import (
    validate_conversation_answer,
)
from archcompass.domain.atlas import (
    AtlasEdge,
    AtlasMetricValue,
    AtlasRelationshipEvidence,
    EdgeType,
    MetricScope,
)
from archcompass.domain.consultation import ClaimClassification
from archcompass.domain.conversation import (
    AnswerClaim,
    ConversationEvidenceKind,
    ReportConversationContext,
    ReportQuestionType,
)
from tests.evaluation.test_conversation_matrix import (
    _answer_context,
    _artifact_id,
    _node,
    _reference,
)
from tests.unit.test_conversation_fact_validation import _answer, _pinned_nodes

_METRIC = AtlasMetricValue(
    node_id="node-03",
    metric="dependency.fan_in",
    value=7,
    scope=MetricScope.OWNING_MODULE,
    definition="Direct internal modules depending on the owner.",
)


def _metric_context() -> tuple[ReportConversationContext, str]:
    """An evidence-trace context whose only exact artifact is one metric value."""

    context = _answer_context(
        "Trace the evidence for FIND-003.",
        [ReportQuestionType.EVIDENCE_TRACE],
        finding_ids=["FIND-003"],
    )
    reference = _reference(
        ConversationEvidenceKind.ATLAS_METRIC,
        _artifact_id(_METRIC),
        _METRIC,
        node_id=_METRIC.node_id,
    )
    atlas_evidence = context.retrieved_atlas_evidence[0].model_copy(
        update={
            "evidence_references": [
                *context.retrieved_atlas_evidence[0].evidence_references,
                reference,
            ],
            "metrics": [_METRIC],
        }
    )
    context = context.model_copy(
        update={
            "evidence_references": [*context.evidence_references, reference],
            "retrieved_atlas_evidence": [atlas_evidence],
        }
    )
    return context, reference.evidence_id


def _observation_errors(text: str) -> list[str]:
    context, evidence_id = _metric_context()
    claim = AnswerClaim(
        text=text,
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        evidence_ids=[evidence_id],
    )
    return validate_conversation_answer(
        _answer(claim),
        context=context,
        atlas_nodes=_pinned_nodes(context),
    ).errors


def test_exact_metric_restatement_is_accepted() -> None:
    assert _observation_errors("dependency.fan_in is 7 for node-03.") == []


def test_answer_referencing_an_unsupplied_finding_is_rejected() -> None:
    context, _ = _metric_context()
    claim = AnswerClaim(
        text="FIND-999 also applies here.",
        classification=ClaimClassification.ADVISOR_INFERENCE,
        finding_ids=["FIND-999"],
    )

    errors = validate_conversation_answer(
        _answer(claim),
        context=context,
        atlas_nodes=_pinned_nodes(context),
    ).errors

    assert any("unknown finding" in error.casefold() for error in errors)


def test_invented_repository_artifact_id_is_rejected() -> None:
    """A hard failure that must survive WS4: invented artifact IDs are contract breaks."""

    errors = _observation_errors(
        "The evidence comes from node-invented for node-03."
    )
    assert any("artifact ids absent" in error.casefold() for error in errors)


def test_invented_metric_value_is_rejected() -> None:
    """A hard failure that must survive WS4: a restated metric must be the exact value."""

    errors = _observation_errors("dependency.fan_in is 999 for node-03.")
    assert any(
        "numeric values absent" in error.casefold() and "999" in error
        for error in errors
    )


def test_count_derived_from_the_citation_does_not_fail_the_turn() -> None:
    """A figure the reader can verify from the citation is not a fabricated fact."""

    assert _observation_errors("This observation rests on 1 metric for node-03.") == []


def test_relationship_word_in_prose_does_not_fail_the_turn() -> None:
    """`imports`, `calls`, and `contains` are common English, not only edge types."""

    assert _observation_errors("node-03 imports the boundary module.") == []


def _edge_context() -> tuple[ReportConversationContext, str]:
    """An evidence-trace context whose only exact artifact is one relationship edge."""

    context = _answer_context(
        "Trace the evidence for FIND-003.",
        [ReportQuestionType.EVIDENCE_TRACE],
        finding_ids=["FIND-003"],
    )
    source = next(
        item
        for item in context.retrieved_atlas_evidence[0].nodes
        if item.node_id == "node-03"
    )
    target = _node(4)
    edge = AtlasRelationshipEvidence(
        edge_id="edge-03",
        edge_type=EdgeType.CALLS,
        source=source,
        target=target,
        confidence=1.0,
    )
    # Retrieval and validation both project a relationship into an AtlasEdge before
    # hashing it, so the fixture must reference the projected shape.
    projected = AtlasEdge(
        edge_id=edge.edge_id,
        source_id=edge.source.node_id,
        target_id=edge.target.node_id,
        edge_type=edge.edge_type,
        confidence=edge.confidence,
    )
    reference = _reference(
        ConversationEvidenceKind.ATLAS_RELATIONSHIP,
        edge.edge_id,
        projected,
        node_id=edge.source.node_id,
    )
    atlas_evidence = context.retrieved_atlas_evidence[0].model_copy(
        update={
            "evidence_references": [
                *context.retrieved_atlas_evidence[0].evidence_references,
                reference,
            ],
            "relationships": [edge],
        }
    )
    context = context.model_copy(
        update={
            "evidence_references": [*context.evidence_references, reference],
            "retrieved_atlas_evidence": [atlas_evidence],
        }
    )
    return context, reference.evidence_id


def _edge_observation_errors(text: str) -> list[str]:
    context, evidence_id = _edge_context()
    claim = AnswerClaim(
        text=text,
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        evidence_ids=[evidence_id],
    )
    return validate_conversation_answer(
        _answer(claim),
        context=context,
        atlas_nodes=_pinned_nodes(context),
    ).errors


def test_relationship_check_still_rejects_an_unsupplied_edge_type() -> None:
    """The guard scopes the check to supplied evidence; it does not disable it.

    Once a relationship edge is actually cited, naming a different edge type is a
    fabricated repository relationship and must still fail the turn.
    """

    errors = _edge_observation_errors("node-03 imports the target module.")

    assert any("relationship types absent" in error for error in errors)


def test_relationship_check_accepts_the_supplied_edge_type() -> None:
    assert _edge_observation_errors("node-03 calls the target module.") == []


def test_demoted_observations_are_recorded_rather_than_discarded() -> None:
    """A demoted check still produces a durable audit record, not silence."""

    context, evidence_id = _metric_context()
    claim = AnswerClaim(
        text="This observation rests on 1 metric for node-03.",
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        evidence_ids=[evidence_id],
    )

    validation = validate_conversation_answer(
        _answer(claim),
        context=context,
        atlas_nodes=_pinned_nodes(context),
    )

    assert validation.errors == []
    assert validation.is_valid
    assert any("numeric values absent" in item for item in validation.warnings)
