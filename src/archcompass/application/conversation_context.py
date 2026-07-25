"""Build bounded provider-neutral contexts for report-conversation turns."""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from typing import TypeVar

from pydantic import BaseModel

from archcompass.configuration import ConversationConfig, ReasoningModelConfig
from archcompass.domain import budgets
from archcompass.domain.atlas import (
    Atlas,
    AtlasNode,
    AtlasNodeSummary,
    AtlasRelationshipEvidence,
    SourceLocation,
)
from archcompass.domain.base import canonical_json
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.consultation import (
    ArchitecturalFinding,
    Claim,
    ConsultationRun,
    RecommendationReport,
    SupportedStatement,
)
from archcompass.domain.conversation import (
    ConversationAtlasEvidence,
    ConversationEvidenceKind,
    ConversationEvidenceReference,
    ConversationEvidenceScope,
    ConversationMessage,
    ConversationMessageView,
    ConversationRetrievalResult,
    FindingDigest,
    PinnedCaseSummary,
    ReportConversation,
    ReportConversationContext,
    ReportQuestionPlan,
    ReportQuestionPlanningContext,
    ReportSummary,
)
from archcompass.domain.errors import ConversationValidationError

ContextItem = TypeVar("ContextItem", bound=BaseModel)


class ConversationContextBuilder:
    def __init__(
        self,
        config: ConversationConfig,
        *,
        reasoning: ReasoningModelConfig,
    ) -> None:
        self._config = config
        # The assembled context becomes the model prompt, so its cap is derived from
        # the configured window rather than frozen. The former fixed 56,000-character
        # cap predates the transport guard that now measures the real request.
        self._context_budget = budgets.conversation_context_budget(
            context_window_tokens=reasoning.context_window_tokens,
            max_output_tokens=reasoning.max_output_tokens,
            chars_per_token=reasoning.chars_per_token,
        )

    def build_planning(
        self,
        *,
        conversation: ReportConversation,
        run: ConsultationRun,
        case: ArchitectureCase,
        question: str,
        history: list[ConversationMessage],
        prior_evidence_references: list[ConversationEvidenceReference],
    ) -> ReportQuestionPlanningContext:
        report = self._report(run)
        self._validate_case_pin(conversation, case)
        context = ReportQuestionPlanningContext(
            question=question,
            pinned_case=self._pinned_case(case),
            report_summary=self._report_summary(run),
            finding_digests=[self._finding_digest(item) for item in report.findings],
            conversation_summary=conversation.current_summary,
            recent_messages=self._message_views(history),
            prior_evidence_references=prior_evidence_references[-96:],
        )
        self._require_bounded(context, "planning")
        return context

    def build(
        self,
        *,
        conversation: ReportConversation,
        run: ConsultationRun,
        case: ArchitectureCase,
        question: str,
        plan: ReportQuestionPlan,
        history: list[ConversationMessage],
        retrieval_results: list[ConversationRetrievalResult],
        atlas: Atlas | None,
    ) -> ReportConversationContext:
        report = self._report(run)
        self._validate_case_pin(conversation, case)
        atlas_nodes = {item.atlas_id: item for item in atlas.nodes} if atlas is not None else {}
        retrieved_findings = self._unique(
            item for result in retrieval_results for item in result.findings
        )
        retrieved_claims = self._claims(run, retrieval_results)
        retrieved_concerns = self._unique(
            item for result in retrieval_results for item in result.concern_analyses
        )
        retrieved_policies = self._unique(
            item
            for result in retrieval_results
            for item in result.policies
        )
        alternatives = self._unique(
            item for result in retrieval_results for item in result.alternatives
        )
        scenarios = self._unique(
            item for result in retrieval_results for item in result.scenarios
        )
        evidence_references = self._evidence_references(
            run,
            case,
            retrieval_results,
            retrieved_claims,
        )
        atlas_evidence = [
            self._atlas_evidence(
                result,
                atlas_nodes=atlas_nodes,
                allowed_evidence_ids={
                    item.evidence_id for item in evidence_references
                },
            )
            for result in retrieval_results
            if result.atlas_results
            or result.metric_definitions
            or result.unavailable_reason is not None
        ]
        context = ReportConversationContext(
            conversation_id=conversation.conversation_id,
            run_id=run.run_id,
            case_id=conversation.case_id,
            case_revision=conversation.case_revision,
            atlas_version_id=conversation.atlas_version_id,
            policy_index_version_id=conversation.policy_index_version_id,
            question=question,
            question_plan=plan,
            pinned_case=self._pinned_case(case),
            report_summary=self._report_summary(run),
            finding_digests=[self._finding_digest(item) for item in report.findings],
            conversation_summary=conversation.current_summary,
            recent_messages=self._message_views(history),
            evidence_references=evidence_references,
            retrieved_findings=retrieved_findings,
            retrieved_claims=retrieved_claims,
            retrieved_concern_analyses=retrieved_concerns,
            retrieved_atlas_evidence=atlas_evidence,
            retrieved_policies=retrieved_policies,
            retrieved_alternatives=alternatives,
            retrieved_scenarios=scenarios,
            evidence_scope_notes=[
                note
                for note, present in (
                    (
                        "Original-run evidence directly explains the persisted recommendation.",
                        any(
                            item.scope is ConversationEvidenceScope.ORIGINAL_RUN
                            for item in evidence_references
                        ),
                    ),
                    (
                        "Additional repository evidence was retrieved during this conversation "
                        "from the pinned Atlas and did not influence the original report.",
                        any(
                            item.scope
                            is ConversationEvidenceScope.ADDITIONAL_CONVERSATION
                            for item in evidence_references
                        ),
                    ),
                )
                if present
            ],
        )
        self._require_bounded(context, "answer")
        return context

    def report_summary(self, run: ConsultationRun) -> ReportSummary:
        """Expose the compact stable report projection used by planning."""
        return self._report_summary(run)

    def _report_summary(self, run: ConsultationRun) -> ReportSummary:
        report = self._report(run)
        return ReportSummary(
            report_id=report.report_id,
            disposition=report.disposition,
            decision_summary=self._statement(report.decision_summary, 1600),
            problem_and_desired_outcome=self._truncate(
                report.problem_and_desired_outcome,
                2400,
            ),
            important_design_forces=report.important_design_forces[:12],
            recommended_architecture=self._statement(
                report.recommended_architecture,
                1800,
            ),
            alternatives=report.alternatives_considered[:5],
            scenarios=report.scenario_analysis[:4],
            implementation_sequence=[
                self._statement(item, 800)
                for item in report.implementation_sequence[:8]
            ],
            confidence=report.confidence,
            reversal_conditions=[
                self._statement(item, 800)
                for item in report.reversal_conditions[:8]
            ],
            revisit_triggers=[
                self._statement(item, 800)
                for item in report.revisit_triggers[:8]
            ],
            policies=report.policy_evidence[:12],
        )

    def _message_views(
        self,
        history: list[ConversationMessage],
    ) -> list[ConversationMessageView]:
        return [
            ConversationMessageView(
                ordinal=item.ordinal,
                role=item.role,
                text=self._truncate(item.text, 2000),
                relevant_finding_ids=(
                    item.answer.relevant_finding_ids if item.answer is not None else []
                ),
                relevant_evidence_ids=(
                    item.retrieved_context.supplied_evidence_ids
                    if item.retrieved_context is not None
                    else []
                )[:48],
                uncertainty=(
                    [statement.text for statement in item.answer.uncertainty]
                    if item.answer is not None
                    else []
                ),
            )
            for item in history[-self._config.recent_message_limit :]
        ]

    def _evidence_references(
        self,
        run: ConsultationRun,
        case: ArchitectureCase,
        results: list[ConversationRetrievalResult],
        claims: list[Claim],
    ) -> list[ConversationEvidenceReference]:
        report = self._report(run)
        references = [
            self._reference(
                kind=ConversationEvidenceKind.REPORT_CONTEXT,
                artifact_id=report.report_id,
                value=self._report_summary(run),
            ),
            self._reference(
                kind=ConversationEvidenceKind.REPORT_CONTEXT,
                artifact_id=f"{case.case_id}@{case.revision}",
                value=self._pinned_case(case),
            ),
        ]
        references.extend(
            self._reference(
                kind=ConversationEvidenceKind.FINDING,
                artifact_id=item.finding_id,
                value=item,
            )
            for result in results
            for item in result.findings
        )
        referenced_claim_ids = {item.claim_id for item in claims}
        references.extend(
            self._reference(
                kind=ConversationEvidenceKind.REPORT_CLAIM,
                artifact_id=item.claim_id,
                value=item,
            )
            for item in self._claim_registry(run).values()
            if item.claim_id in referenced_claim_ids
        )
        references.extend(
            item
            for result in results
            for item in result.evidence_references
        )
        unique: dict[str, ConversationEvidenceReference] = {}
        for item in references:
            previous = unique.get(item.evidence_id)
            if previous is not None and previous != item:
                raise ConversationValidationError(
                    f"Evidence ID {item.evidence_id} maps to conflicting artifacts"
                )
            unique.setdefault(item.evidence_id, item)
        bounded = list(unique.values())
        if len(bounded) > 128:
            raise ConversationValidationError(
                "The report conversation evidence inventory exceeds 128 exact artifacts"
            )
        return bounded

    def _atlas_evidence(
        self,
        result: ConversationRetrievalResult,
        *,
        atlas_nodes: dict[str, AtlasNode],
        allowed_evidence_ids: set[str],
    ) -> ConversationAtlasEvidence:
        atlas_results = result.atlas_results
        nodes = self._unique(
            item for atlas_result in atlas_results for item in atlas_result.node_summaries
        )
        node_summaries = {item.node_id: item for item in nodes}
        relationships: list[AtlasRelationshipEvidence] = []
        for edge in self._unique(
            item for atlas_result in atlas_results for item in atlas_result.relationships
        ):
            source = node_summaries.get(edge.source_id) or self._node_summary(
                atlas_nodes.get(edge.source_id)
            )
            target = node_summaries.get(edge.target_id) or self._node_summary(
                atlas_nodes.get(edge.target_id)
            )
            if source is None or target is None:
                continue
            relationships.append(
                AtlasRelationshipEvidence(
                    edge_id=edge.edge_id,
                    edge_type=edge.edge_type,
                    source=source,
                    target=target,
                    confidence=edge.confidence,
                    location=edge.location,
                )
            )
        metrics = self._unique(
            item
            for item in [
                *(
                    metric
                    for atlas_result in atlas_results
                    for metric in atlas_result.metric_values
                ),
                *result.metric_definitions,
            ]
        )
        signals = self._unique(
            item for atlas_result in atlas_results for item in atlas_result.signals
        )
        excerpts = self._unique(
            item
            for atlas_result in atlas_results
            for item in atlas_result.excerpts
        )
        ordered_node_ids = list(
            dict.fromkeys(
                node_id
                for atlas_result in atlas_results
                for node_id in atlas_result.node_ids
            )
        )
        query_summary = " | ".join(
            [
                *(
                    item.summary.strip()
                    for item in atlas_results
                    if item.summary.strip()
                ),
                *(
                    f"Truncated: {reason}"
                    for reason in result.truncation_reasons
                ),
            ]
        )
        return ConversationAtlasEvidence(
            action=result.action,
            evidence_references=[
                item
                for item in result.evidence_references
                if item.evidence_id in allowed_evidence_ids
                and item.kind
                in {
                    ConversationEvidenceKind.ATLAS_NODE,
                    ConversationEvidenceKind.ATLAS_RELATIONSHIP,
                    ConversationEvidenceKind.ATLAS_METRIC,
                    ConversationEvidenceKind.ATLAS_SIGNAL,
                    ConversationEvidenceKind.SOURCE_EXCERPT,
                    ConversationEvidenceKind.TEST,
                    ConversationEvidenceKind.METRIC_DEFINITION,
                }
            ],
            query_summary=query_summary,
            ordered_node_ids=ordered_node_ids,
            nodes=nodes,
            relationships=relationships,
            metrics=metrics,
            signals=signals,
            excerpts=excerpts,
            test_ids=list(
                dict.fromkeys(
                    test_id
                    for atlas_result in atlas_results
                    for test_id in atlas_result.test_ids
                )
            ),
            unavailable_reason=result.unavailable_reason,
            truncated=result.truncated,
        )

    @staticmethod
    def _claims(
        run: ConsultationRun,
        results: list[ConversationRetrievalResult],
    ) -> list[Claim]:
        registry = ConversationContextBuilder._claim_registry(run)
        wanted = [
            *(
                claim.claim_id
                for result in results
                for claim in result.claims
            ),
            *(
                claim_id
                for result in results
                for finding in result.findings
                for claim_id in finding.claim_ids
            ),
        ]
        return [
            registry[claim_id]
            for claim_id in dict.fromkeys(wanted)
            if claim_id in registry
        ]

    @staticmethod
    def _claim_registry(run: ConsultationRun) -> dict[str, Claim]:
        report = ConversationContextBuilder._report(run)
        claims = [
            *report.confirmed_context,
            *report.assumptions_and_unresolved_questions,
            *report.repository_observations,
            *report.relevant_policies,
            *report.evidence_appendix,
            *(claim for analysis in run.concern_analyses for claim in analysis.findings),
        ]
        registry: dict[str, Claim] = {}
        for claim in claims:
            previous = registry.get(claim.claim_id)
            if previous is not None and previous != claim:
                raise ConversationValidationError(
                    f"Claim ID {claim.claim_id} maps to conflicting canonical claims"
                )
            registry.setdefault(claim.claim_id, claim)
        return registry

    @staticmethod
    def _pinned_case(case: ArchitectureCase) -> PinnedCaseSummary:
        return PinnedCaseSummary(
            case_id=case.case_id,
            revision=case.revision,
            title=case.title,
            problem_statement=case.problem_statement,
            desired_outcome=case.desired_outcome,
            actors_and_workflows=case.actors_and_workflows,
            functional_requirements=case.functional_requirements,
            quality_attributes=case.quality_attributes,
            technical_constraints=case.technical_constraints,
            organisational_constraints=case.organisational_constraints,
            derived_constraints=[item.text for item in case.derived_constraints],
            confirmed_facts=[item.text for item in case.confirmed_facts],
            expected_future_changes=case.expected_future_changes,
            non_goals=case.non_goals,
            assumptions=[item.text for item in case.assumptions],
        )

    @staticmethod
    def _reference(
        *,
        kind: ConversationEvidenceKind,
        artifact_id: str,
        value: BaseModel,
    ) -> ConversationEvidenceReference:
        serialized = canonical_json(value)
        return ConversationEvidenceReference(
            evidence_id=f"{kind.value}:{artifact_id}",
            kind=kind,
            artifact_id=artifact_id,
            scope=ConversationEvidenceScope.ORIGINAL_RUN,
            content_hash=sha256(serialized.encode("utf-8")).hexdigest(),
        )

    @staticmethod
    def _node_summary(node: AtlasNode | None) -> AtlasNodeSummary | None:
        if node is None:
            return None
        return AtlasNodeSummary(
            node_id=node.atlas_id,
            qualified_name=node.qualified_name,
            node_type=node.node_type,
            path=node.path,
            location=(
                None
                if node.start_line is None or node.end_line is None
                else SourceLocation(
                    path=node.path,
                    start_line=node.start_line,
                    end_line=node.end_line,
                )
            ),
            is_public=node.is_public,
        )

    @staticmethod
    def _report(run: ConsultationRun) -> RecommendationReport:
        if run.report is None:
            raise ConversationValidationError("The pinned run has no report")
        return run.report

    @staticmethod
    def _validate_case_pin(
        conversation: ReportConversation,
        case: ArchitectureCase,
    ) -> None:
        if (
            case.case_id != conversation.case_id
            or case.revision != conversation.case_revision
        ):
            raise ConversationValidationError(
                "Conversation case context does not match its pinned revision"
            )

    @staticmethod
    def _statement(statement: SupportedStatement, limit: int) -> SupportedStatement:
        return statement.model_copy(
            update={"text": ConversationContextBuilder._truncate(statement.text, limit)}
        )

    @staticmethod
    def _finding_digest(finding: ArchitecturalFinding) -> FindingDigest:
        return FindingDigest.from_finding(finding)

    @staticmethod
    def _unique(items: Iterable[ContextItem]) -> list[ContextItem]:
        unique: dict[str, ContextItem] = {}
        for item in items:
            key = canonical_json(item)
            unique.setdefault(key, item)
        return list(unique.values())

    def _require_bounded(self, context: BaseModel, name: str) -> None:
        if len(canonical_json(context)) > self._context_budget:
            raise ConversationValidationError(
                f"The report conversation {name} context exceeds the hard serialized budget"
            )

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        normalized = value.strip()
        return normalized if len(normalized) <= limit else normalized[: limit - 1].rstrip() + "…"
