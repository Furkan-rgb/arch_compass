"""Validated, bounded retrieval against one consultation run and its pinned evidence."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import TypeVar

from pydantic import BaseModel

from archcompass.configuration import ConversationConfig, ReasoningModelConfig
from archcompass.domain import budgets
from archcompass.domain.atlas import (
    Atlas,
    AtlasNode,
    AtlasNodeSummary,
    AtlasQueryResult,
    NeighbourhoodQuery,
    NodeDetailsQuery,
    SearchNodesQuery,
    ShortestPathQuery,
    SourceExcerpt,
    SourceExcerptQuery,
    SourceLocation,
)
from archcompass.domain.atlas_metrics import profile_observations
from archcompass.domain.base import canonical_json
from archcompass.domain.consultation import ArchitecturalFinding, Claim, ConsultationRun
from archcompass.domain.conversation import (
    CompareFindingsAction,
    ConversationEvidenceKind,
    ConversationEvidenceReference,
    ConversationEvidenceScope,
    ConversationRetrievalAction,
    ConversationRetrievalResult,
    ExplainMetricDefinitionAction,
    GetAlternativeAction,
    GetAtlasNodesAction,
    GetClusterAnalysisAction,
    GetDependencyNeighbourhoodAction,
    GetDependencyPathAction,
    GetFindingAction,
    GetMetricProfilesAction,
    GetObscuritySignalsAction,
    GetPoliciesAction,
    GetReportClaimsAction,
    GetScenarioAction,
    GetSourceExcerptAction,
    ListFindingsAction,
    ReportQuestionPlan,
    SearchAtlasNodesAction,
)
from archcompass.domain.errors import (
    ConversationRetrievalError,
    StaleAtlasError,
)
from archcompass.domain.policy import RetrievedPolicy
from archcompass.ports.atlas import AtlasQueryService
from archcompass.ports.repositories import AtlasRepository

_BudgetItem = TypeVar("_BudgetItem")
_OriginalEvidenceRegistry = dict[str, set[str]]
_SERIALIZED_BUDGET_REASON = (
    "Serialized retrieval budget limited the turn to the configured character ceiling."
)
_MINIMUM_RESULT_REASON = "No evidence fit within the remaining conversation retrieval budget."
_MAX_EVIDENCE_REFERENCES = 96


def conversation_evidence_id(kind: str, value: str | BaseModel) -> str:
    """Return a stable identity for one exact conversation evidence artifact."""
    if isinstance(value, str):
        return f"{kind}:{value}"
    digest = sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{kind}:{digest}"


def _content_hash(value: str | BaseModel) -> str:
    payload = (
        canonical_json(value) if isinstance(value, BaseModel) else canonical_json({"value": value})
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _evidence_reference(
    *,
    kind: ConversationEvidenceKind,
    artifact_id: str,
    content: str | BaseModel,
    original_evidence_registry: _OriginalEvidenceRegistry,
    node_id: str | None = None,
    location: SourceLocation | None = None,
) -> ConversationEvidenceReference:
    evidence_id = f"{kind.value}:{artifact_id}"
    content_hash = _content_hash(content)
    return ConversationEvidenceReference(
        evidence_id=evidence_id,
        kind=kind,
        artifact_id=artifact_id,
        scope=(
            ConversationEvidenceScope.ORIGINAL_RUN
            if content_hash in original_evidence_registry.get(evidence_id, set())
            else ConversationEvidenceScope.ADDITIONAL_CONVERSATION
        ),
        content_hash=content_hash,
        node_id=node_id,
        location=location,
    )


def _artifact_reference(
    *,
    kind: ConversationEvidenceKind,
    artifact: BaseModel,
    original_evidence_registry: _OriginalEvidenceRegistry,
    node_id: str | None = None,
    location: SourceLocation | None = None,
) -> ConversationEvidenceReference:
    artifact_id = _content_hash(artifact)
    return _evidence_reference(
        kind=kind,
        artifact_id=artifact_id,
        content=artifact,
        original_evidence_registry=original_evidence_registry,
        node_id=node_id,
        location=location,
    )


def _result_references(
    result: ConversationRetrievalResult,
    *,
    original_evidence_registry: _OriginalEvidenceRegistry,
) -> list[ConversationEvidenceReference]:
    references: dict[str, ConversationEvidenceReference] = {}

    def add(reference: ConversationEvidenceReference) -> None:
        references.setdefault(reference.evidence_id, reference)

    for finding in result.findings:
        add(
            _evidence_reference(
                kind=ConversationEvidenceKind.FINDING,
                artifact_id=finding.finding_id,
                content=finding,
                original_evidence_registry=original_evidence_registry,
            )
        )
        for node in finding.affected_locations:
            add(
                _evidence_reference(
                    kind=ConversationEvidenceKind.ATLAS_NODE,
                    artifact_id=node.node_id,
                    content=node,
                    original_evidence_registry=original_evidence_registry,
                    node_id=node.node_id,
                    location=node.location,
                )
            )
        for node_id in finding.atlas_node_ids:
            add(
                _evidence_reference(
                    kind=ConversationEvidenceKind.ATLAS_NODE,
                    artifact_id=node_id,
                    content=node_id,
                    original_evidence_registry=original_evidence_registry,
                    node_id=node_id,
                )
            )
        for metric in finding.metric_observations:
            add(
                _artifact_reference(
                    kind=ConversationEvidenceKind.ATLAS_METRIC,
                    artifact=metric,
                    original_evidence_registry=original_evidence_registry,
                    node_id=metric.node_id,
                )
            )
        for signal in finding.obscurity_signals:
            add(
                _artifact_reference(
                    kind=ConversationEvidenceKind.ATLAS_SIGNAL,
                    artifact=signal,
                    original_evidence_registry=original_evidence_registry,
                    node_id=signal.node_id,
                    location=signal.location,
                )
            )
    for claim in result.claims:
        add(
            _evidence_reference(
                kind=ConversationEvidenceKind.REPORT_CLAIM,
                artifact_id=claim.claim_id,
                content=claim,
                original_evidence_registry=original_evidence_registry,
            )
        )
        for atlas_reference in claim.atlas_references:
            add(
                _evidence_reference(
                    kind=ConversationEvidenceKind.ATLAS_NODE,
                    artifact_id=atlas_reference.node_id,
                    content=atlas_reference,
                    original_evidence_registry=original_evidence_registry,
                    node_id=atlas_reference.node_id,
                    location=atlas_reference.location,
                )
            )
    for analysis in result.concern_analyses:
        add(
            _evidence_reference(
                kind=ConversationEvidenceKind.CONCERN_ANALYSIS,
                artifact_id=analysis.cluster_id,
                content=analysis,
                original_evidence_registry=original_evidence_registry,
            )
        )
        for claim in analysis.findings:
            add(
                _evidence_reference(
                    kind=ConversationEvidenceKind.REPORT_CLAIM,
                    artifact_id=claim.claim_id,
                    content=claim,
                    original_evidence_registry=original_evidence_registry,
                )
            )
            for atlas_reference in claim.atlas_references:
                add(
                    _evidence_reference(
                        kind=ConversationEvidenceKind.ATLAS_NODE,
                        artifact_id=atlas_reference.node_id,
                        content=atlas_reference,
                        original_evidence_registry=original_evidence_registry,
                        node_id=atlas_reference.node_id,
                        location=atlas_reference.location,
                    )
                )
    for alternative in result.alternatives:
        add(
            _evidence_reference(
                kind=ConversationEvidenceKind.ALTERNATIVE,
                artifact_id=alternative.id,
                content=alternative,
                original_evidence_registry=original_evidence_registry,
            )
        )
    for scenario in result.scenarios:
        artifact_id = _content_hash(scenario)
        add(
            _evidence_reference(
                kind=ConversationEvidenceKind.SCENARIO,
                artifact_id=artifact_id,
                content=scenario,
                original_evidence_registry=original_evidence_registry,
            )
        )
    for policy in result.policies:
        add(
            _evidence_reference(
                kind=ConversationEvidenceKind.POLICY,
                artifact_id=policy.policy.id,
                content=policy,
                original_evidence_registry=original_evidence_registry,
            )
        )
    for metric in result.metric_definitions:
        add(
            _artifact_reference(
                kind=ConversationEvidenceKind.METRIC_DEFINITION,
                artifact=metric,
                original_evidence_registry=original_evidence_registry,
                node_id=metric.node_id,
            )
        )
    for atlas_result in result.atlas_results:
        for node in atlas_result.node_summaries:
            add(
                _evidence_reference(
                    kind=ConversationEvidenceKind.ATLAS_NODE,
                    artifact_id=node.node_id,
                    content=node,
                    original_evidence_registry=original_evidence_registry,
                    node_id=node.node_id,
                    location=node.location,
                )
            )
        for node_id in atlas_result.node_ids:
            add(
                _evidence_reference(
                    kind=ConversationEvidenceKind.ATLAS_NODE,
                    artifact_id=node_id,
                    content=node_id,
                    original_evidence_registry=original_evidence_registry,
                    node_id=node_id,
                )
            )
        for relationship in atlas_result.relationships:
            add(
                _evidence_reference(
                    kind=ConversationEvidenceKind.ATLAS_RELATIONSHIP,
                    artifact_id=relationship.edge_id,
                    content=relationship,
                    original_evidence_registry=original_evidence_registry,
                    node_id=relationship.source_id,
                    location=relationship.location,
                )
            )
        for metric in atlas_result.metric_values:
            add(
                _artifact_reference(
                    kind=ConversationEvidenceKind.ATLAS_METRIC,
                    artifact=metric,
                    original_evidence_registry=original_evidence_registry,
                    node_id=metric.node_id,
                )
            )
        for signal in atlas_result.signals:
            add(
                _artifact_reference(
                    kind=ConversationEvidenceKind.ATLAS_SIGNAL,
                    artifact=signal,
                    original_evidence_registry=original_evidence_registry,
                    node_id=signal.node_id,
                    location=signal.location,
                )
            )
        for excerpt in atlas_result.excerpts:
            add(
                _artifact_reference(
                    kind=ConversationEvidenceKind.SOURCE_EXCERPT,
                    artifact=excerpt,
                    original_evidence_registry=original_evidence_registry,
                    node_id=excerpt.node_id,
                    location=excerpt.location,
                )
            )
        for test_id in atlas_result.test_ids:
            add(
                _evidence_reference(
                    kind=ConversationEvidenceKind.TEST,
                    artifact_id=test_id,
                    content=test_id,
                    original_evidence_registry=original_evidence_registry,
                    node_id=test_id,
                )
            )
    return list(references.values())


def _bounded_reason(reason: str) -> str:
    """Fit an unavailability reason inside its transient field.

    The reason is often a provider or validation error; a multi-kilobyte dump must
    become a bounded honest record, not a ValidationError that fails the turn.
    """

    limit = 2_000
    if len(reason) <= limit:
        return reason
    return reason[: limit - 1].rstrip() + "…"


def _append_truncation(
    result: ConversationRetrievalResult,
    reason: str,
) -> ConversationRetrievalResult:
    reasons = list(dict.fromkeys([*result.truncation_reasons, reason]))[:16]
    return result.model_copy(
        update={
            "truncated": True,
            "truncation_reasons": reasons,
        }
    )


def _excerpt_line_count(excerpt: SourceExcerpt) -> int:
    return excerpt.location.end_line - excerpt.location.start_line + 1


def _truncate_excerpt(excerpt: SourceExcerpt, max_lines: int) -> SourceExcerpt | None:
    if max_lines <= 0:
        return None
    current_lines = _excerpt_line_count(excerpt)
    if current_lines <= max_lines:
        return excerpt
    text_lines = excerpt.text.splitlines(keepends=True)
    text = "".join(text_lines[:max_lines]) if text_lines else excerpt.text
    return excerpt.model_copy(
        update={
            "location": excerpt.location.model_copy(
                update={"end_line": excerpt.location.start_line + max_lines - 1}
            ),
            "text": text,
        }
    )


class _TurnRetrievalBudget:
    def __init__(
        self,
        *,
        config: ConversationConfig,
        character_budget: int,
        original_evidence_registry: _OriginalEvidenceRegistry,
    ) -> None:
        self._config = config
        self._character_budget = character_budget
        self._original_evidence_registry = original_evidence_registry
        self._finding_ids: set[str] = set()
        self._node_ids: set[str] = set()
        self._policy_ids: set[str] = set()
        self._evidence_ids: set[str] = set()
        self._excerpt_lines = 0
        self._serialized_characters = 0

    def project(
        self,
        result: ConversationRetrievalResult,
        *,
        future_actions: list[ConversationRetrievalAction],
    ) -> ConversationRetrievalResult:
        projected = self._project_findings(result)
        projected = self._project_report_node_references(projected)
        projected = self._project_policies(projected)
        projected = self._project_atlas(projected)
        projected = self._project_evidence_references(projected)

        reserved = sum(self._minimum_result_size(action) for action in future_actions)
        available = (
            self._character_budget - self._serialized_characters - reserved
        )
        projected = self._fit_serialized_characters(projected, available)
        size = len(projected.model_dump_json())
        if self._serialized_characters + size + reserved > self._character_budget:
            raise ConversationRetrievalError(
                "Question plan action metadata exceeds the serialized retrieval budget"
            )

        self._finding_ids.update(item.finding_id for item in projected.findings)
        self._policy_ids.update(item.policy.id for item in projected.policies)
        self._evidence_ids.update(
            reference.evidence_id for reference in projected.evidence_references
        )
        self._node_ids.update(self._node_ids_in(projected))
        self._excerpt_lines += sum(
            _excerpt_line_count(excerpt)
            for atlas_result in projected.atlas_results
            for excerpt in atlas_result.excerpts
        )
        self._serialized_characters += size
        return projected

    def _project_evidence_references(
        self,
        result: ConversationRetrievalResult,
    ) -> ConversationRetrievalResult:
        projected = result.model_copy(update={"evidence_references": []})
        references = _result_references(
            projected,
            original_evidence_registry=self._original_evidence_registry,
        )
        while (
            len(
                self._evidence_ids
                | {reference.evidence_id for reference in references}
            )
            > _MAX_EVIDENCE_REFERENCES
        ):
            projected = _append_truncation(
                projected,
                "Evidence-reference budget limited the turn to 96 exact artifacts.",
            )
            reduced = self._reduce_content(projected)
            if reduced is None:
                raise ConversationRetrievalError(
                    "Retrieved evidence cannot fit the exact-reference budget"
                )
            projected = reduced
            references = _result_references(
                projected,
                original_evidence_registry=self._original_evidence_registry,
            )
        return projected.model_copy(update={"evidence_references": references})

    @property
    def remaining_nodes(self) -> int:
        return self._config.max_atlas_nodes - len(self._node_ids)

    @property
    def remaining_excerpt_lines(self) -> int:
        return self._config.max_total_excerpt_lines - self._excerpt_lines

    def clamp_node_ids(self, node_ids: list[str]) -> tuple[list[str], bool]:
        visible = set(self._node_ids)
        projected: list[str] = []
        for node_id in node_ids:
            if self._allow_nodes((node_id,), visible_nodes=visible):
                projected.append(node_id)
        return projected, len(projected) != len(node_ids)

    def can_retrieve_node(self, node_id: str) -> bool:
        return node_id in self._node_ids or self.remaining_nodes > 0

    def _project_findings(
        self,
        result: ConversationRetrievalResult,
    ) -> ConversationRetrievalResult:
        findings, truncated = self._project_unique(
            result.findings,
            identity=lambda item: item.finding_id,
            seen=self._finding_ids,
            limit=self._config.max_findings,
        )
        projected = result.model_copy(update={"findings": findings})
        if truncated:
            projected = _append_truncation(
                projected,
                "Finding budget limited the turn to 12 unique findings.",
            )
        return projected

    def _project_policies(
        self,
        result: ConversationRetrievalResult,
    ) -> ConversationRetrievalResult:
        policies, truncated = self._project_unique(
            result.policies,
            identity=lambda item: item.policy.id,
            seen=self._policy_ids,
            limit=self._config.max_policies,
        )
        projected = result.model_copy(update={"policies": policies})
        if truncated:
            projected = _append_truncation(
                projected,
                "Policy budget limited the turn to 8 unique policies.",
            )
        return projected

    def _project_report_node_references(
        self,
        result: ConversationRetrievalResult,
    ) -> ConversationRetrievalResult:
        visible_nodes = set(self._node_ids)
        truncated = False

        findings = []
        for finding in result.findings:
            if self._allow_nodes(
                tuple(self._finding_node_ids(finding)),
                visible_nodes=visible_nodes,
            ):
                findings.append(finding)
            else:
                truncated = True

        claims = []
        for claim in result.claims:
            if self._allow_nodes(
                tuple(reference.node_id for reference in claim.atlas_references),
                visible_nodes=visible_nodes,
            ):
                claims.append(claim)
            else:
                truncated = True

        concern_analyses = []
        for analysis in result.concern_analyses:
            node_ids = tuple(
                reference.node_id
                for claim in analysis.findings
                for reference in claim.atlas_references
            )
            if self._allow_nodes(node_ids, visible_nodes=visible_nodes):
                concern_analyses.append(analysis)
            else:
                truncated = True

        projected = result.model_copy(
            update={
                "findings": findings,
                "claims": claims,
                "concern_analyses": concern_analyses,
            }
        )
        if truncated:
            projected = _append_truncation(
                projected,
                "Atlas-node budget omitted detailed report evidence exceeding 24 unique nodes.",
            )
        return projected

    def _project_atlas(
        self,
        result: ConversationRetrievalResult,
    ) -> ConversationRetrievalResult:
        visible_nodes = self._report_node_ids_in(result) | self._node_ids
        excerpt_lines = self._excerpt_lines
        atlas_results: list[AtlasQueryResult] = []
        truncated_nodes = False
        truncated_excerpts = False

        for atlas_result in result.atlas_results:
            (
                projected,
                node_truncated,
                excerpt_truncated,
                excerpt_lines,
            ) = self._project_atlas_result(
                atlas_result,
                visible_nodes=visible_nodes,
                excerpt_lines=excerpt_lines,
            )
            atlas_results.append(projected)
            truncated_nodes = truncated_nodes or node_truncated
            truncated_excerpts = truncated_excerpts or excerpt_truncated

        metric_definitions = []
        for metric in result.metric_definitions:
            if self._allow_nodes(
                (metric.node_id,),
                visible_nodes=visible_nodes,
            ):
                metric_definitions.append(metric)
            else:
                truncated_nodes = True

        projected_result = result.model_copy(
            update={
                "atlas_results": atlas_results,
                "metric_definitions": metric_definitions,
            }
        )
        if truncated_nodes:
            projected_result = _append_truncation(
                projected_result,
                "Atlas-node budget limited the turn to 24 unique nodes, including path nodes.",
            )
        if truncated_excerpts:
            projected_result = _append_truncation(
                projected_result,
                "Excerpt budget limited evidence to 120 lines per excerpt and 180 lines per turn.",
            )
        return projected_result

    def _project_atlas_result(
        self,
        atlas_result: AtlasQueryResult,
        *,
        visible_nodes: set[str],
        excerpt_lines: int,
    ) -> tuple[AtlasQueryResult, bool, bool, int]:
        truncated_nodes = False
        truncated_excerpts = False

        node_ids = []
        for node_id in atlas_result.node_ids:
            if self._allow_nodes((node_id,), visible_nodes=visible_nodes):
                node_ids.append(node_id)
            else:
                truncated_nodes = True

        node_summaries = []
        for node in atlas_result.node_summaries:
            if self._allow_nodes((node.node_id,), visible_nodes=visible_nodes):
                node_summaries.append(node)
            else:
                truncated_nodes = True

        metric_values = []
        for metric in atlas_result.metric_values:
            if self._allow_nodes((metric.node_id,), visible_nodes=visible_nodes):
                metric_values.append(metric)
            else:
                truncated_nodes = True

        relationships = []
        for relationship in atlas_result.relationships:
            if self._allow_nodes(
                (relationship.source_id, relationship.target_id),
                visible_nodes=visible_nodes,
            ):
                relationships.append(relationship)
            else:
                truncated_nodes = True

        test_ids = []
        for test_id in atlas_result.test_ids:
            if self._allow_nodes((test_id,), visible_nodes=visible_nodes):
                test_ids.append(test_id)
            else:
                truncated_nodes = True

        signals = []
        for signal in atlas_result.signals:
            if self._allow_nodes((signal.node_id,), visible_nodes=visible_nodes):
                signals.append(signal)
            else:
                truncated_nodes = True

        excerpts = []
        for excerpt in atlas_result.excerpts:
            if not self._allow_nodes((excerpt.node_id,), visible_nodes=visible_nodes):
                truncated_nodes = True
                continue
            remaining = self._config.max_total_excerpt_lines - excerpt_lines
            per_excerpt = min(self._config.max_excerpt_lines, remaining)
            projected_excerpt = _truncate_excerpt(excerpt, per_excerpt)
            if projected_excerpt is None:
                truncated_excerpts = True
                continue
            excerpts.append(projected_excerpt)
            retained_lines = _excerpt_line_count(projected_excerpt)
            excerpt_lines += retained_lines
            if retained_lines < _excerpt_line_count(excerpt):
                truncated_excerpts = True

        return (
            atlas_result.model_copy(
                update={
                    "node_ids": node_ids,
                    "node_summaries": node_summaries,
                    "metric_values": metric_values,
                    "relationships": relationships,
                    "test_ids": test_ids,
                    "signals": signals,
                    "excerpts": excerpts,
                }
            ),
            truncated_nodes,
            truncated_excerpts,
            excerpt_lines,
        )

    def _allow_nodes(
        self,
        node_ids: tuple[str, ...],
        *,
        visible_nodes: set[str],
    ) -> bool:
        missing = set(node_ids) - visible_nodes
        if len(visible_nodes) + len(missing) > self._config.max_atlas_nodes:
            return False
        visible_nodes.update(missing)
        return True

    def _fit_serialized_characters(
        self,
        result: ConversationRetrievalResult,
        available: int,
    ) -> ConversationRetrievalResult:
        if len(result.model_dump_json()) <= available:
            return result
        projected = _append_truncation(result, _SERIALIZED_BUDGET_REASON)
        while len(projected.model_dump_json()) > available:
            reduced = self._reduce_content(projected)
            if reduced is None:
                raise ConversationRetrievalError(
                    "Question plan action metadata exceeds the serialized retrieval budget"
                )
            projected = reduced.model_copy(
                update={
                    "evidence_references": _result_references(
                        reduced,
                        original_evidence_registry=self._original_evidence_registry,
                    )
                }
            )
        return projected

    @staticmethod
    def _reduce_content(
        result: ConversationRetrievalResult,
    ) -> ConversationRetrievalResult | None:
        for field_name in (
            "policies",
            "findings",
            "claims",
            "concern_analyses",
            "alternatives",
            "scenarios",
            "metric_definitions",
        ):
            values = getattr(result, field_name)
            if values:
                return result.model_copy(update={field_name: values[:-1]})

        if result.atlas_results:
            atlas_results = list(result.atlas_results)
            reduced = _TurnRetrievalBudget._reduce_atlas_result(atlas_results[-1])
            if reduced is None:
                atlas_results.pop()
            else:
                atlas_results[-1] = reduced
            return result.model_copy(update={"atlas_results": atlas_results})

        if result.unavailable_reason and len(result.unavailable_reason) > 80:
            shortened = result.unavailable_reason[: max(80, len(result.unavailable_reason) // 2)]
            return result.model_copy(update={"unavailable_reason": shortened.rstrip() + "…"})
        return None

    @staticmethod
    def _reduce_atlas_result(atlas_result: AtlasQueryResult) -> AtlasQueryResult | None:
        if atlas_result.excerpts:
            excerpts = list(atlas_result.excerpts)
            last = excerpts[-1]
            lines = _excerpt_line_count(last)
            reduced = _truncate_excerpt(last, lines // 2)
            if reduced is None or lines == 1:
                excerpts.pop()
            else:
                excerpts[-1] = reduced
            return atlas_result.model_copy(update={"excerpts": excerpts})
        for field_name in (
            "signals",
            "metric_values",
            "relationships",
            "test_ids",
            "node_summaries",
            "node_ids",
        ):
            values = getattr(atlas_result, field_name)
            if values:
                return atlas_result.model_copy(update={field_name: values[:-1]})
        if atlas_result.summary:
            if len(atlas_result.summary) <= 64:
                return atlas_result.model_copy(update={"summary": ""})
            return atlas_result.model_copy(
                update={"summary": atlas_result.summary[: len(atlas_result.summary) // 2]}
            )
        return None

    @staticmethod
    def _project_unique(
        items: list[_BudgetItem],
        *,
        identity: Callable[[_BudgetItem], str],
        seen: set[str],
        limit: int,
    ) -> tuple[list[_BudgetItem], bool]:
        projected: list[_BudgetItem] = []
        visible = set(seen)
        truncated = False
        for item in items:
            item_id = identity(item)
            if item_id in visible or len(visible) < limit:
                projected.append(item)
                visible.add(item_id)
            else:
                truncated = True
        return projected, truncated

    @staticmethod
    def _node_ids_in(result: ConversationRetrievalResult) -> set[str]:
        return {
            *_TurnRetrievalBudget._report_node_ids_in(result),
            *(
                node_id
                for atlas_result in result.atlas_results
                for node_id in atlas_result.node_ids
            ),
            *(
                node.node_id
                for atlas_result in result.atlas_results
                for node in atlas_result.node_summaries
            ),
            *(
                metric.node_id
                for atlas_result in result.atlas_results
                for metric in atlas_result.metric_values
            ),
            *(
                signal.node_id
                for atlas_result in result.atlas_results
                for signal in atlas_result.signals
            ),
            *(
                excerpt.node_id
                for atlas_result in result.atlas_results
                for excerpt in atlas_result.excerpts
            ),
            *(
                node_id
                for atlas_result in result.atlas_results
                for relationship in atlas_result.relationships
                for node_id in (relationship.source_id, relationship.target_id)
            ),
            *(
                test_id
                for atlas_result in result.atlas_results
                for test_id in atlas_result.test_ids
            ),
            *(metric.node_id for metric in result.metric_definitions),
        }

    @staticmethod
    def _report_node_ids_in(result: ConversationRetrievalResult) -> set[str]:
        return {
            *(
                node_id
                for finding in result.findings
                for node_id in _TurnRetrievalBudget._finding_node_ids(finding)
            ),
            *(
                reference.node_id
                for claim in result.claims
                for reference in claim.atlas_references
            ),
            *(
                reference.node_id
                for analysis in result.concern_analyses
                for claim in analysis.findings
                for reference in claim.atlas_references
            ),
        }

    @staticmethod
    def _finding_node_ids(finding: ArchitecturalFinding) -> set[str]:
        return {
            *finding.atlas_node_ids,
            *(item.node_id for item in finding.affected_locations),
            *(item.node_id for item in finding.metric_observations),
            *(item.node_id for item in finding.obscurity_signals),
        }

    @staticmethod
    def _minimum_result_size(action: ConversationRetrievalAction) -> int:
        return len(
            ConversationRetrievalResult(
                action=action,
                unavailable_reason=_MINIMUM_RESULT_REASON,
                truncated=True,
                truncation_reasons=[_SERIALIZED_BUDGET_REASON],
            ).model_dump_json()
        )


class ConversationEvidenceRetriever:
    def __init__(
        self,
        *,
        atlases: AtlasRepository,
        queries: AtlasQueryService,
        config: ConversationConfig,
        reasoning: ReasoningModelConfig,
    ) -> None:
        self._atlases = atlases
        self._queries = queries
        self._config = config
        # The evidence budget tracks the configured model window; a workspace value may
        # narrow it but never raise it past what the window supports, so the derived
        # figure is the ceiling and the transport guard the hard backstop.
        derived_budget = budgets.retrieved_character_budget(
            context_window_tokens=reasoning.context_window_tokens,
            max_output_tokens=reasoning.max_output_tokens,
            chars_per_token=reasoning.chars_per_token,
        )
        self._character_budget = (
            min(config.max_retrieved_text_characters, derived_budget)
            if config.max_retrieved_text_characters is not None
            else derived_budget
        )

    def execute(
        self,
        *,
        run: ConsultationRun,
        plan: ReportQuestionPlan,
        previous_node_ids: set[str] | None = None,
    ) -> list[ConversationRetrievalResult]:
        if run.report is None:
            raise ConversationRetrievalError("The pinned run has no report")
        report = run.report
        self._validate_limits(plan)
        claim_registry = self._claim_registry(run)
        finding_registry = {item.finding_id: item for item in report.findings}
        cluster_registry = {item.cluster_id: item for item in run.concern_analyses}
        alternative_registry = {item.id: item for item in run.alternatives}
        original_node_ids = self.original_node_ids(run)
        original_evidence_registry = self.original_evidence_registry(run)
        visible_node_ids = original_node_ids | (previous_node_ids or set())
        policy_registry = self._policy_registry(run)
        self._validate_plan(
            plan,
            finding_ids=set(finding_registry),
            claim_ids=set(claim_registry),
            node_ids=visible_node_ids,
            policy_ids=set(policy_registry),
            cluster_ids=set(cluster_registry),
            alternative_ids=set(alternative_registry),
            scenario_count=len(run.scenarios),
        )
        needs_atlas = any(
            isinstance(
                action,
                (
                    GetAtlasNodesAction,
                    SearchAtlasNodesAction,
                    GetMetricProfilesAction,
                    GetObscuritySignalsAction,
                    GetDependencyNeighbourhoodAction,
                    GetDependencyPathAction,
                    GetSourceExcerptAction,
                ),
            )
            for action in plan.retrieval_actions
        )
        atlas = self._load_atlas(run) if needs_atlas else None
        results: list[ConversationRetrievalResult] = []
        budget = _TurnRetrievalBudget(
            config=self._config,
            character_budget=self._character_budget,
            original_evidence_registry=original_evidence_registry,
        )
        for index, action in enumerate(plan.retrieval_actions):
            if isinstance(action, ListFindingsAction):
                result = ConversationRetrievalResult(
                    action=action,
                    findings=report.findings[: min(action.limit, self._config.max_findings)],
                )
            elif isinstance(action, GetFindingAction):
                finding = finding_registry[action.finding_id]
                result = ConversationRetrievalResult(
                    action=action,
                    findings=[finding],
                )
            elif isinstance(action, CompareFindingsAction):
                findings = [finding_registry[item] for item in action.finding_ids]
                result = ConversationRetrievalResult(
                    action=action,
                    findings=findings,
                )
            elif isinstance(action, GetReportClaimsAction):
                claims = [claim_registry[item] for item in action.claim_ids]
                result = ConversationRetrievalResult(
                    action=action,
                    claims=claims,
                )
            elif isinstance(action, GetClusterAnalysisAction):
                analysis = cluster_registry[action.cluster_id]
                result = ConversationRetrievalResult(
                    action=action,
                    concern_analyses=[analysis],
                    claims=analysis.findings[:16],
                )
            elif isinstance(action, GetAlternativeAction):
                alternative = alternative_registry[action.alternative_id]
                result = ConversationRetrievalResult(
                    action=action,
                    alternatives=[alternative],
                )
            elif isinstance(action, GetScenarioAction):
                scenario = run.scenarios[action.ordinal - 1]
                result = ConversationRetrievalResult(
                    action=action,
                    scenarios=[scenario],
                )
            elif isinstance(action, GetPoliciesAction):
                policies = [policy_registry[item] for item in action.policy_ids]
                result = ConversationRetrievalResult(
                    action=action,
                    policies=policies,
                )
            elif isinstance(action, ExplainMetricDefinitionAction):
                observations = [
                    observation
                    for finding in report.findings
                    for observation in finding.metric_observations
                    if observation.metric in set(action.metric_names)
                ][:8]
                result = ConversationRetrievalResult(
                    action=action,
                    metric_definitions=observations,
                    unavailable_reason=(
                        None
                        if observations
                        else "No requested metric definition was retained by the pinned run."
                    ),
                )
            else:
                if atlas is None:
                    result = ConversationRetrievalResult(
                        action=action,
                        unavailable_reason="The pinned run has no RepositoryAtlas.",
                    )
                else:
                    result = self._atlas_result(
                        action,
                        atlas=atlas,
                        budget=budget,
                    )
            results.append(
                budget.project(
                    result,
                    future_actions=plan.retrieval_actions[index + 1 :],
                )
            )
        return results

    def _validate_limits(self, plan: ReportQuestionPlan) -> None:
        if len(plan.retrieval_actions) > self._config.max_actions_per_question:
            raise ConversationRetrievalError(
                "Question plan exceeds the configured retrieval-action limit"
            )
        for action in plan.retrieval_actions:
            if isinstance(action, ListFindingsAction) and (
                action.limit > self._config.max_findings
            ):
                raise ConversationRetrievalError(
                    "Question plan exceeds the configured finding limit"
                )
            if isinstance(action, CompareFindingsAction) and (
                len(action.finding_ids) > self._config.max_findings
            ):
                raise ConversationRetrievalError(
                    "Question plan exceeds the configured finding limit"
                )
            if (
                isinstance(
                    action,
                    (GetAtlasNodesAction, GetMetricProfilesAction, GetObscuritySignalsAction),
                )
                and len(action.node_ids) > self._config.max_atlas_nodes
            ):
                raise ConversationRetrievalError(
                    "Question plan exceeds the configured Atlas-node limit"
                )
            if isinstance(action, SearchAtlasNodesAction) and (
                action.limit > self._config.max_atlas_nodes
            ):
                raise ConversationRetrievalError(
                    "Question plan exceeds the configured Atlas-node limit"
                )
            if isinstance(action, GetDependencyNeighbourhoodAction) and (
                action.limit > self._config.max_atlas_nodes
                or action.depth > self._config.max_neighbourhood_depth
            ):
                raise ConversationRetrievalError(
                    "Question plan exceeds a configured neighbourhood limit"
                )
            if isinstance(action, GetSourceExcerptAction) and (
                action.max_lines > self._config.max_excerpt_lines
            ):
                raise ConversationRetrievalError(
                    "Question plan exceeds the configured excerpt-line limit"
                )
            if isinstance(action, GetPoliciesAction) and (
                len(action.policy_ids) > self._config.max_policies
            ):
                raise ConversationRetrievalError(
                    "Question plan exceeds the configured policy limit"
                )

    def _atlas_result(
        self,
        action: ConversationRetrievalAction,
        *,
        atlas: Atlas,
        budget: _TurnRetrievalBudget,
    ) -> ConversationRetrievalResult:
        truncation_reasons: list[str] = []
        try:
            if isinstance(
                action,
                (GetAtlasNodesAction, GetMetricProfilesAction, GetObscuritySignalsAction),
            ):
                node_ids, truncated = budget.clamp_node_ids(action.node_ids)
                if truncated:
                    truncation_reasons.append(
                        "Atlas-node budget clamped this action before query execution."
                    )
                if not node_ids:
                    return self._budget_unavailable_result(
                        action,
                        "Atlas-node budget was exhausted before query execution.",
                    )
                atlas_results = [
                    self._queries.execute(
                        atlas,
                        NodeDetailsQuery(kind="node_details", node_id=node_id),
                    )
                    for node_id in node_ids
                ]
            elif isinstance(action, SearchAtlasNodesAction):
                if budget.remaining_nodes <= 0:
                    return self._budget_unavailable_result(
                        action,
                        "Atlas-node budget was exhausted before search execution.",
                    )
                limit = min(action.limit, budget.remaining_nodes)
                if limit < action.limit:
                    truncation_reasons.append(
                        "Atlas-node budget clamped the search limit before query execution."
                    )
                atlas_results = [
                    self._queries.execute(
                        atlas,
                        SearchNodesQuery(
                            kind="search_nodes",
                            terms=action.terms,
                            limit=limit,
                        ),
                    )
                ]
            elif isinstance(action, GetDependencyNeighbourhoodAction):
                if budget.remaining_nodes <= 0:
                    return self._budget_unavailable_result(
                        action,
                        "Atlas-node budget was exhausted before neighbourhood execution.",
                    )
                limit = min(action.limit, budget.remaining_nodes)
                if limit < action.limit:
                    truncation_reasons.append(
                        "Atlas-node budget clamped the neighbourhood before query execution."
                    )
                atlas_results = [
                    self._queries.execute(
                        atlas,
                        NeighbourhoodQuery(
                            kind=(
                                "forward_neighbourhood"
                                if action.direction == "forward"
                                else "reverse_neighbourhood"
                            ),
                            node_id=action.node_id,
                            depth=action.depth,
                            limit=limit,
                        ),
                    )
                ]
            elif isinstance(action, GetDependencyPathAction):
                atlas_results = [
                    self._queries.execute(
                        atlas,
                        ShortestPathQuery(
                            kind="shortest_dependency_path",
                            source_id=action.source_node_id,
                            target_id=action.target_node_id,
                        ),
                    )
                ]
            elif isinstance(action, GetSourceExcerptAction):
                if not budget.can_retrieve_node(action.node_id):
                    return self._budget_unavailable_result(
                        action,
                        "Atlas-node budget was exhausted before source retrieval.",
                    )
                if budget.remaining_excerpt_lines <= 0:
                    return self._budget_unavailable_result(
                        action,
                        "Excerpt-line budget was exhausted before source retrieval.",
                    )
                max_lines = min(action.max_lines, budget.remaining_excerpt_lines)
                if max_lines < action.max_lines:
                    truncation_reasons.append(
                        "Excerpt-line budget clamped the source query before repository access."
                    )
                atlas_results = [
                    self._queries.execute(
                        atlas,
                        SourceExcerptQuery(
                            kind="source_excerpt",
                            node_id=action.node_id,
                            context_lines=action.context_lines,
                            max_lines=max_lines,
                        ),
                    )
                ]
            else:
                raise ConversationRetrievalError("Unsupported conversation retrieval action")
        except StaleAtlasError as error:
            return ConversationRetrievalResult(
                action=action,
                unavailable_reason=_bounded_reason(str(error)),
            )
        atlas_results = [
            self._enrich_relationship_endpoints(atlas, atlas_result)
            for atlas_result in atlas_results
        ]
        return ConversationRetrievalResult(
            action=action,
            atlas_results=atlas_results,
            truncated=bool(truncation_reasons),
            truncation_reasons=truncation_reasons,
        )

    @staticmethod
    def _enrich_relationship_endpoints(
        atlas: Atlas,
        result: AtlasQueryResult,
    ) -> AtlasQueryResult:
        nodes = {node.atlas_id: node for node in atlas.nodes}
        summaries = list(result.node_summaries)
        supplied_ids = {node.node_id for node in summaries}
        wanted_ids = dict.fromkeys(
            [
                *(
                    node_id
                    for relationship in result.relationships
                    for node_id in (relationship.source_id, relationship.target_id)
                ),
                *result.test_ids,
            ]
        )
        for node_id in wanted_ids:
            if node_id in supplied_ids or (node := nodes.get(node_id)) is None:
                continue
            summaries.append(ConversationEvidenceRetriever._node_summary(node))
            supplied_ids.add(node_id)
        return result.model_copy(update={"node_summaries": summaries})

    @staticmethod
    def _node_summary(node: AtlasNode) -> AtlasNodeSummary:
        location = (
            SourceLocation(
                path=node.path,
                start_line=node.start_line,
                end_line=node.end_line,
            )
            if node.start_line is not None and node.end_line is not None
            else None
        )
        return AtlasNodeSummary(
            node_id=node.atlas_id,
            qualified_name=node.qualified_name,
            node_type=node.node_type,
            path=node.path,
            location=location,
            is_public=node.is_public,
        )

    @staticmethod
    def _budget_unavailable_result(
        action: ConversationRetrievalAction,
        reason: str,
    ) -> ConversationRetrievalResult:
        return ConversationRetrievalResult(
            action=action,
            unavailable_reason=reason,
            truncated=True,
            truncation_reasons=[reason],
        )

    def _load_atlas(self, run: ConsultationRun) -> Atlas | None:
        if run.atlas_version_id is None:
            return None
        return self._atlases.get(run.atlas_version_id)

    @staticmethod
    def original_node_ids(run: ConsultationRun) -> set[str]:
        return {
            *(node_id for packet in run.focused_packets for node_id in packet.surfaced_node_ids),
            *(
                evidence.node.node_id
                for packet in run.focused_packets
                for evidence in packet.node_evidence
            ),
            *(
                node.node_id
                for packet in run.focused_packets
                for node in packet.test_evidence
            ),
            *(
                test_id
                for packet in run.focused_packets
                for test_id in packet.test_ids
            ),
            *(
                node_id
                for packet in run.focused_packets
                for relationship in packet.relationships
                for node_id in (relationship.source_id, relationship.target_id)
            ),
            *(
                node_id
                for packet in run.focused_packets
                for relationship in packet.relationship_evidence
                for node_id in (
                    relationship.source.node_id,
                    relationship.target.node_id,
                )
            ),
            *(
                profile.node_id
                for packet in run.focused_packets
                for profile in packet.metrics
            ),
            *(
                reference.node_id
                for claim in ConversationEvidenceRetriever._claim_registry(run).values()
                for reference in claim.atlas_references
            ),
            *(
                node_id
                for finding in (run.report.findings if run.report is not None else [])
                for node_id in finding.atlas_node_ids
            ),
        }

    @staticmethod
    def original_evidence_registry(
        run: ConsultationRun,
    ) -> _OriginalEvidenceRegistry:
        """Index exact immutable-run artifact identities and their canonical content."""
        if run.report is None:
            return {}
        registry: _OriginalEvidenceRegistry = {}

        def add(
            kind: ConversationEvidenceKind,
            artifact_id: str,
            content: str | BaseModel,
        ) -> None:
            evidence_id = f"{kind.value}:{artifact_id}"
            registry.setdefault(evidence_id, set()).add(_content_hash(content))

        for finding in run.report.findings:
            add(ConversationEvidenceKind.FINDING, finding.finding_id, finding)
        for claim in ConversationEvidenceRetriever._claim_registry(run).values():
            add(ConversationEvidenceKind.REPORT_CLAIM, claim.claim_id, claim)
            for atlas_reference in claim.atlas_references:
                add(
                    ConversationEvidenceKind.ATLAS_NODE,
                    atlas_reference.node_id,
                    atlas_reference,
                )
        for node_id in ConversationEvidenceRetriever.original_node_ids(run):
            add(ConversationEvidenceKind.ATLAS_NODE, node_id, node_id)
        for retrieved in ConversationEvidenceRetriever._policy_registry(run).values():
            add(ConversationEvidenceKind.POLICY, retrieved.policy.id, retrieved)
        for analysis in run.concern_analyses:
            add(ConversationEvidenceKind.CONCERN_ANALYSIS, analysis.cluster_id, analysis)
        for alternative in run.alternatives:
            add(ConversationEvidenceKind.ALTERNATIVE, alternative.id, alternative)
        for scenario in run.scenarios:
            digest = _content_hash(scenario)
            add(ConversationEvidenceKind.SCENARIO, digest, scenario)

        for packet in run.focused_packets:
            for evidence in packet.node_evidence:
                add(
                    ConversationEvidenceKind.ATLAS_NODE,
                    evidence.node.node_id,
                    evidence.node,
                )
                for metric in evidence.metrics:
                    add(
                        ConversationEvidenceKind.ATLAS_METRIC,
                        _content_hash(metric),
                        metric,
                    )
                for signal in evidence.signals:
                    add(
                        ConversationEvidenceKind.ATLAS_SIGNAL,
                        _content_hash(signal),
                        signal,
                    )
            for node in packet.test_evidence:
                add(ConversationEvidenceKind.ATLAS_NODE, node.node_id, node)
            for edge in packet.relationships:
                add(
                    ConversationEvidenceKind.ATLAS_RELATIONSHIP,
                    edge.edge_id,
                    edge,
                )
            for relationship in packet.relationship_evidence:
                add(
                    ConversationEvidenceKind.ATLAS_RELATIONSHIP,
                    relationship.edge_id,
                    relationship,
                )
            for profile in packet.metrics:
                for metric in profile_observations(profile):
                    add(
                        ConversationEvidenceKind.ATLAS_METRIC,
                        _content_hash(metric),
                        metric,
                    )
            for excerpt in packet.excerpts:
                add(
                    ConversationEvidenceKind.SOURCE_EXCERPT,
                    _content_hash(excerpt),
                    excerpt,
                )
            for test_id in packet.test_ids:
                add(ConversationEvidenceKind.TEST, test_id, test_id)

        for finding in run.report.findings:
            for node in finding.affected_locations:
                add(ConversationEvidenceKind.ATLAS_NODE, node.node_id, node)
            for metric in finding.metric_observations:
                digest = _content_hash(metric)
                add(ConversationEvidenceKind.ATLAS_METRIC, digest, metric)
                add(ConversationEvidenceKind.METRIC_DEFINITION, digest, metric)
            for signal in finding.obscurity_signals:
                add(
                    ConversationEvidenceKind.ATLAS_SIGNAL,
                    _content_hash(signal),
                    signal,
                )
        return registry

    @staticmethod
    def original_evidence_ids(run: ConsultationRun) -> set[str]:
        """Return stable IDs for all exact evidence retained by the immutable run."""
        return set(ConversationEvidenceRetriever.original_evidence_registry(run))

    @staticmethod
    def _policy_registry(run: ConsultationRun) -> dict[str, RetrievedPolicy]:
        registry: dict[str, RetrievedPolicy] = {}
        for packet in run.focused_packets:
            for retrieved in packet.policies:
                policy_id = retrieved.policy.id
                previous = registry.get(policy_id)
                if previous is None:
                    registry[policy_id] = retrieved
                    continue
                if previous.policy != retrieved.policy:
                    raise ConversationRetrievalError(
                        f"Pinned run retains inconsistent policy documents for {policy_id}"
                    )
                chunks = {chunk.chunk_id: chunk for chunk in previous.chunks}
                for chunk in retrieved.chunks:
                    existing = chunks.get(chunk.chunk_id)
                    if existing is not None and existing != chunk:
                        raise ConversationRetrievalError(
                            f"Pinned run retains inconsistent policy chunk {chunk.chunk_id}"
                        )
                    chunks.setdefault(chunk.chunk_id, chunk)
                registry[policy_id] = previous.model_copy(
                    update={
                        "chunks": list(chunks.values()),
                        "distance": min(previous.distance, retrieved.distance),
                    }
                )
        return registry

    @staticmethod
    def _claim_registry(run: ConsultationRun) -> dict[str, Claim]:
        if run.report is None:
            return {}
        claims = [
            *run.report.confirmed_context,
            *run.report.assumptions_and_unresolved_questions,
            *run.report.repository_observations,
            *run.report.relevant_policies,
            *run.report.evidence_appendix,
            *(claim for analysis in run.concern_analyses for claim in analysis.findings),
        ]
        registry: dict[str, Claim] = {}
        for claim in claims:
            previous = registry.get(claim.claim_id)
            if previous is not None and previous != claim:
                raise ConversationRetrievalError(
                    f"Pinned run retains inconsistent report claims for {claim.claim_id}"
                )
            registry.setdefault(claim.claim_id, claim)
        return registry

    @staticmethod
    def _validate_plan(
        plan: ReportQuestionPlan,
        *,
        finding_ids: set[str],
        claim_ids: set[str],
        node_ids: set[str],
        policy_ids: set[str],
        cluster_ids: set[str],
        alternative_ids: set[str],
        scenario_count: int,
    ) -> None:
        if unknown := set(plan.finding_ids) - finding_ids:
            raise ConversationRetrievalError(
                f"Question plan references unknown findings: {sorted(unknown)}"
            )
        if unknown := set(plan.report_claim_ids) - claim_ids:
            raise ConversationRetrievalError(
                f"Question plan references unknown report claims: {sorted(unknown)}"
            )
        if unknown := set(plan.atlas_node_ids) - node_ids:
            raise ConversationRetrievalError(
                f"Question plan references Atlas nodes not visible in the conversation: "
                f"{sorted(unknown)}"
            )
        if unknown := set(plan.policy_ids) - policy_ids:
            raise ConversationRetrievalError(
                f"Question plan references policies unavailable to the pinned run: "
                f"{sorted(unknown)}"
            )
        for action in plan.retrieval_actions:
            if isinstance(action, (GetFindingAction,)):
                wanted_findings: set[str] = {action.finding_id}
            elif isinstance(action, CompareFindingsAction):
                wanted_findings = set(action.finding_ids)
            else:
                wanted_findings = set[str]()
            if unknown := wanted_findings - finding_ids:
                raise ConversationRetrievalError(
                    f"Retrieval action references unknown findings: {sorted(unknown)}"
                )
            if isinstance(action, GetReportClaimsAction) and (
                unknown := set(action.claim_ids) - claim_ids
            ):
                raise ConversationRetrievalError(
                    f"Retrieval action references unknown claims: {sorted(unknown)}"
                )
            if (
                isinstance(action, GetClusterAnalysisAction)
                and action.cluster_id not in cluster_ids
            ):
                raise ConversationRetrievalError(
                    f"Retrieval action references unknown cluster {action.cluster_id}"
                )
            if (
                isinstance(action, GetAlternativeAction)
                and action.alternative_id not in alternative_ids
            ):
                raise ConversationRetrievalError(
                    f"Retrieval action references unknown alternative {action.alternative_id}"
                )
            if isinstance(action, GetPoliciesAction) and (
                unknown := set(action.policy_ids) - policy_ids
            ):
                raise ConversationRetrievalError(
                    f"Retrieval action references unavailable policies: {sorted(unknown)}"
                )
            action_node_ids: set[str] = set()
            if isinstance(
                action,
                (GetAtlasNodesAction, GetMetricProfilesAction, GetObscuritySignalsAction),
            ):
                action_node_ids = set(action.node_ids)
            elif isinstance(action, GetDependencyNeighbourhoodAction):
                action_node_ids = {action.node_id}
            elif isinstance(action, GetDependencyPathAction):
                action_node_ids = {action.source_node_id, action.target_node_id}
            elif isinstance(action, GetSourceExcerptAction):
                action_node_ids = {action.node_id}
            if unknown := action_node_ids - node_ids:
                raise ConversationRetrievalError(
                    "Retrieval action references Atlas nodes not visible in the "
                    f"conversation: {sorted(unknown)}"
                )
            if isinstance(action, GetScenarioAction) and action.ordinal > scenario_count:
                raise ConversationRetrievalError(
                    f"Scenario ordinal {action.ordinal} is out of range"
                )
