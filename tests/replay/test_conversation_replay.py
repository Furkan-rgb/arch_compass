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

import pytest

from archcompass.application.conversation_validation import (
    validate_conversation_answer,
)
from archcompass.domain.atlas import AtlasMetricValue, MetricScope
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
    )


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
    )

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


@pytest.mark.xfail(
    reason=(
        "WS4: a count derived from the citation itself is scraped as an invented "
        "repository number and fails the turn; this becomes an audit warning"
    ),
    strict=True,
)
def test_count_derived_from_the_citation_does_not_fail_the_turn() -> None:
    """A figure the reader can verify from the citation is not a fabricated fact."""

    assert _observation_errors("This observation rests on 1 metric for node-03.") == []


@pytest.mark.xfail(
    reason=(
        "WS4: ordinary English words that collide with Atlas edge-type names are "
        "scraped as invented relationships; this becomes an audit warning"
    ),
    strict=True,
)
def test_relationship_word_in_prose_does_not_fail_the_turn() -> None:
    """`imports`, `calls`, and `contains` are common English, not only edge types."""

    assert _observation_errors("node-03 imports the boundary module.") == []
