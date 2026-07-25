"""Pinned report-conversation contracts and bounded retrieval language."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from archcompass.domain.atlas import (
    AtlasMetricValue,
    AtlasNodeSummary,
    AtlasQueryResult,
    AtlasRelationshipEvidence,
    ObscuritySignal,
    SourceExcerpt,
    SourceLocation,
)
from archcompass.domain.base import DomainModel, new_id, utc_now
from archcompass.domain.case import CaseAlternative, Confidence
from archcompass.domain.consultation import (
    ArchitecturalFinding,
    Claim,
    ClaimClassification,
    ConcernAnalysis,
    DesignForce,
    FindingImportance,
    RecommendationDisposition,
    ScenarioEvaluation,
    SupportedStatement,
)
from archcompass.domain.policy import PolicyEvidenceSummary, RetrievedPolicy


class ConversationEvidenceScope(StrEnum):
    ORIGINAL_RUN = "original_run"
    ADDITIONAL_CONVERSATION = "additional_conversation"


class ConversationEvidenceKind(StrEnum):
    FINDING = "finding"
    REPORT_CLAIM = "report_claim"
    REPORT_CONTEXT = "report_context"
    CONCERN_ANALYSIS = "concern_analysis"
    ALTERNATIVE = "alternative"
    SCENARIO = "scenario"
    ATLAS_NODE = "atlas_node"
    ATLAS_RELATIONSHIP = "atlas_relationship"
    ATLAS_METRIC = "atlas_metric"
    ATLAS_SIGNAL = "atlas_signal"
    SOURCE_EXCERPT = "source_excerpt"
    TEST = "test"
    POLICY = "policy"
    METRIC_DEFINITION = "metric_definition"
    RETRIEVAL_UNAVAILABLE = "retrieval_unavailable"


class ConversationEvidenceReference(DomainModel):
    """Stable reference to one exact artifact supplied to conversation reasoning."""

    evidence_id: str = Field(min_length=1)
    kind: ConversationEvidenceKind
    artifact_id: str = Field(min_length=1)
    scope: ConversationEvidenceScope
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    node_id: str | None = None
    location: SourceLocation | None = None


class ConversationExcerptSnapshot(DomainModel):
    """Bounded durable copy only for an otherwise unreconstructable excerpt."""

    evidence_id: str = Field(min_length=1)
    location: SourceLocation
    text: str = Field(min_length=1, max_length=24_000)

    @model_validator(mode="after")
    def validate_line_budget(self) -> ConversationExcerptSnapshot:
        if self.text.count("\n") + 1 > 120:
            raise ValueError("One excerpt snapshot may contain at most 120 lines")
        return self


class ReportQuestionType(StrEnum):
    REPORT_SUMMARY = "report_summary"
    LIST_FINDINGS = "list_findings"
    FINDING_DETAILS = "finding_details"
    FINDING_PRIORITY = "finding_priority"
    COMPARE_FINDINGS = "compare_findings"
    EVIDENCE_TRACE = "evidence_trace"
    SOURCE_EXPLANATION = "source_explanation"
    POLICY_EXPLANATION = "policy_explanation"
    ALTERNATIVE_EXPLANATION = "alternative_explanation"
    SCENARIO_EXPLANATION = "scenario_explanation"
    ASSUMPTION_REVIEW = "assumption_review"
    IMPLEMENTATION_ORDER = "implementation_order"
    COUNTERFACTUAL = "counterfactual"
    GENERAL_REPORT_QUESTION = "general_report_question"


class ListFindingsAction(DomainModel):
    kind: Literal["list_findings"]
    limit: int = Field(default=12, ge=1, le=12)


class GetFindingAction(DomainModel):
    kind: Literal["get_finding"]
    finding_id: str


class CompareFindingsAction(DomainModel):
    kind: Literal["compare_findings"]
    finding_ids: list[str] = Field(min_length=2, max_length=12)


class GetReportClaimsAction(DomainModel):
    kind: Literal["get_report_claims"]
    claim_ids: list[str] = Field(min_length=1, max_length=16)


class GetClusterAnalysisAction(DomainModel):
    kind: Literal["get_cluster_analysis"]
    cluster_id: str


class GetAlternativeAction(DomainModel):
    kind: Literal["get_alternative"]
    alternative_id: str


class GetScenarioAction(DomainModel):
    kind: Literal["get_scenario"]
    ordinal: int = Field(ge=1)


class GetAtlasNodesAction(DomainModel):
    kind: Literal["get_atlas_nodes"]
    node_ids: list[str] = Field(min_length=1, max_length=24)


class SearchAtlasNodesAction(DomainModel):
    kind: Literal["search_atlas_nodes"]
    terms: list[str] = Field(min_length=1, max_length=10)
    limit: int = Field(default=12, ge=1, le=24)


class GetMetricProfilesAction(DomainModel):
    kind: Literal["get_metric_profiles"]
    node_ids: list[str] = Field(min_length=1, max_length=24)


class GetObscuritySignalsAction(DomainModel):
    kind: Literal["get_obscurity_signals"]
    node_ids: list[str] = Field(min_length=1, max_length=24)


class GetDependencyNeighbourhoodAction(DomainModel):
    kind: Literal["get_dependency_neighbourhood"]
    node_id: str
    direction: Literal["forward", "reverse"] = "reverse"
    depth: int = Field(default=1, ge=1, le=2)
    limit: int = Field(default=24, ge=1, le=24)


class GetDependencyPathAction(DomainModel):
    kind: Literal["get_dependency_path"]
    source_node_id: str
    target_node_id: str


class GetSourceExcerptAction(DomainModel):
    kind: Literal["get_source_excerpt"]
    node_id: str
    context_lines: int = Field(default=3, ge=0, le=20)
    max_lines: int = Field(default=60, ge=1, le=120)


class GetPoliciesAction(DomainModel):
    kind: Literal["get_policies"]
    policy_ids: list[str] = Field(min_length=1, max_length=8)


class ExplainMetricDefinitionAction(DomainModel):
    kind: Literal["explain_metric_definition"]
    metric_names: list[str] = Field(min_length=1, max_length=8)


ConversationRetrievalAction = Annotated[
    ListFindingsAction
    | GetFindingAction
    | CompareFindingsAction
    | GetReportClaimsAction
    | GetClusterAnalysisAction
    | GetAlternativeAction
    | GetScenarioAction
    | GetAtlasNodesAction
    | SearchAtlasNodesAction
    | GetMetricProfilesAction
    | GetObscuritySignalsAction
    | GetDependencyNeighbourhoodAction
    | GetDependencyPathAction
    | GetSourceExcerptAction
    | GetPoliciesAction
    | ExplainMetricDefinitionAction,
    Field(discriminator="kind"),
]


class ReportQuestionPlan(DomainModel):
    question_types: list[ReportQuestionType] = Field(min_length=1)
    finding_ids: list[str] = Field(default_factory=list[str], max_length=12)
    report_claim_ids: list[str] = Field(default_factory=list[str], max_length=16)
    atlas_node_ids: list[str] = Field(default_factory=list[str], max_length=24)
    policy_ids: list[str] = Field(default_factory=list[str], max_length=8)
    search_terms: list[str] = Field(default_factory=list[str], max_length=10)
    retrieval_actions: list[ConversationRetrievalAction] = Field(max_length=8)
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique_references(self) -> ReportQuestionPlan:
        for name, values in (
            ("finding", self.finding_ids),
            ("claim", self.report_claim_ids),
            ("Atlas node", self.atlas_node_ids),
            ("policy", self.policy_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Question-plan {name} references must be unique")
        if len(self.question_types) != len(set(self.question_types)):
            raise ValueError("Question types must be unique")
        return self


class ConversationRetrievalResult(DomainModel):
    """Transient bounded payload; this object is never stored in message rows."""

    action: ConversationRetrievalAction
    evidence_references: list[ConversationEvidenceReference] = Field(
        default_factory=list[ConversationEvidenceReference],
        max_length=96,
    )
    findings: list[ArchitecturalFinding] = Field(
        default_factory=list[ArchitecturalFinding],
        max_length=12,
    )
    claims: list[Claim] = Field(default_factory=list[Claim], max_length=16)
    concern_analyses: list[ConcernAnalysis] = Field(
        default_factory=list[ConcernAnalysis],
        max_length=4,
    )
    alternatives: list[CaseAlternative] = Field(
        default_factory=list[CaseAlternative],
        max_length=5,
    )
    scenarios: list[ScenarioEvaluation] = Field(
        default_factory=list[ScenarioEvaluation],
        max_length=4,
    )
    atlas_results: list[AtlasQueryResult] = Field(
        default_factory=list[AtlasQueryResult],
        max_length=24,
    )
    policies: list[RetrievedPolicy] = Field(
        default_factory=list[RetrievedPolicy],
        max_length=8,
    )
    metric_definitions: list[AtlasMetricValue] = Field(
        default_factory=list[AtlasMetricValue],
        max_length=8,
    )
    unavailable_reason: str | None = None
    truncated: bool = False
    truncation_reasons: list[str] = Field(default_factory=list[str], max_length=16)

    @model_validator(mode="after")
    def unique_evidence_references(self) -> ConversationRetrievalResult:
        evidence_ids = [item.evidence_id for item in self.evidence_references]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Retrieval-result evidence IDs must be unique")
        if any(not item.strip() for item in self.truncation_reasons):
            raise ValueError("Retrieval-result truncation reasons must not be blank")
        return self


class AnswerClaim(DomainModel):
    claim_id: str = Field(default_factory=lambda: new_id("answer_claim"))
    text: str = Field(min_length=1)
    classification: ClaimClassification
    evidence_ids: list[str] = Field(default_factory=list[str], max_length=48)
    finding_ids: list[str] = Field(default_factory=list[str], max_length=12)
    report_claim_ids: list[str] = Field(default_factory=list[str], max_length=16)
    policy_ids: list[str] = Field(default_factory=list[str], max_length=8)

    @model_validator(mode="after")
    def require_unique_support(self) -> AnswerClaim:
        for name, values in (
            ("evidence", self.evidence_ids),
            ("finding", self.finding_ids),
            ("report claim", self.report_claim_ids),
            ("policy", self.policy_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Answer-claim {name} references must be unique")
        if not self.text.strip():
            raise ValueError("Answer claim text must not be blank")
        if not (
            self.evidence_ids
            or self.finding_ids
            or self.report_claim_ids
            or self.policy_ids
        ):
            raise ValueError("Every answer claim must cite exact supplied support")
        return self


class AnswerStatementKind(StrEnum):
    DIRECT_ANSWER = "direct_answer"
    SUPPORTING_POINT = "supporting_point"
    UNCERTAINTY = "uncertainty"


class AnswerStatement(DomainModel):
    """Rendered prose whose complete support is explicit and validated."""

    text: str = Field(min_length=1)
    kind: AnswerStatementKind
    answer_claim_ids: list[str] = Field(default_factory=list[str], max_length=20)
    finding_ids: list[str] = Field(default_factory=list[str], max_length=12)
    report_claim_ids: list[str] = Field(default_factory=list[str], max_length=16)

    @model_validator(mode="after")
    def require_support(self) -> AnswerStatement:
        for name, values in (
            ("answer claim", self.answer_claim_ids),
            ("finding", self.finding_ids),
            ("report claim", self.report_claim_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Answer-statement {name} references must be unique")
        if not self.text.strip():
            raise ValueError("Answer statement text must not be blank")
        if not (self.answer_claim_ids or self.finding_ids or self.report_claim_ids):
            raise ValueError("Every answer statement must cite explicit support")
        return self

    def __str__(self) -> str:
        return self.text


class ConversationAnswer(DomainModel):
    direct_answer: AnswerStatement
    supporting_points: list[AnswerStatement] = Field(
        default_factory=list[AnswerStatement],
        max_length=12,
    )
    claims: list[AnswerClaim] = Field(default_factory=list[AnswerClaim], max_length=20)
    relevant_finding_ids: list[str] = Field(default_factory=list[str], max_length=12)
    uncertainty: list[AnswerStatement] = Field(
        default_factory=list[AnswerStatement],
        max_length=10,
    )
    suggested_follow_up_questions: list[str] = Field(
        default_factory=list[str],
        max_length=5,
    )

    @model_validator(mode="after")
    def validate_statement_kinds_and_claims(self) -> ConversationAnswer:
        if self.direct_answer.kind is not AnswerStatementKind.DIRECT_ANSWER:
            raise ValueError("The direct answer must use the direct_answer statement kind")
        if any(
            item.kind is not AnswerStatementKind.SUPPORTING_POINT
            for item in self.supporting_points
        ):
            raise ValueError("Supporting points must use the supporting_point statement kind")
        if any(
            item.kind is not AnswerStatementKind.UNCERTAINTY
            for item in self.uncertainty
        ):
            raise ValueError("Uncertainty statements must use the uncertainty kind")
        claim_ids = [item.claim_id for item in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("Conversation answer claim IDs must be unique")
        known_claim_ids = set(claim_ids)
        statements = [
            self.direct_answer,
            *self.supporting_points,
            *self.uncertainty,
        ]
        unknown_claim_ids = {
            claim_id
            for statement in statements
            for claim_id in statement.answer_claim_ids
            if claim_id not in known_claim_ids
        }
        if unknown_claim_ids:
            raise ValueError(
                "Answer statements reference unknown answer claims: "
                f"{sorted(unknown_claim_ids)}"
            )
        if len(self.relevant_finding_ids) != len(set(self.relevant_finding_ids)):
            raise ValueError("Relevant finding IDs must be unique")
        statement_finding_ids = {
            finding_id
            for statement in statements
            for finding_id in statement.finding_ids
        }
        if unknown_findings := statement_finding_ids - set(
            self.relevant_finding_ids
        ):
            raise ValueError(
                "Answer statements cite findings absent from relevant_finding_ids: "
                f"{sorted(unknown_findings)}"
            )
        return self


class ConversationRetrievalRecord(DomainModel):
    """Lightweight durable audit record for the exact supplied context."""

    consultation_run_id: str
    case_id: str
    case_revision: int = Field(ge=1)
    atlas_version_id: str | None = None
    policy_index_version_id: str | None = None
    question_plan: ReportQuestionPlan
    retrieval_actions: list[ConversationRetrievalAction] = Field(max_length=8)
    evidence_references: list[ConversationEvidenceReference] = Field(
        default_factory=list[ConversationEvidenceReference],
        max_length=128,
    )
    supplied_finding_ids: list[str] = Field(default_factory=list[str], max_length=12)
    supplied_report_claim_ids: list[str] = Field(
        default_factory=list[str],
        max_length=16,
    )
    supplied_evidence_ids: list[str] = Field(default_factory=list[str], max_length=128)
    supplied_policy_ids: list[str] = Field(default_factory=list[str], max_length=8)
    summary_revision: int | None = Field(default=None, ge=1)
    recent_message_ordinals: list[int] = Field(default_factory=list[int], max_length=8)
    truncations: list[str] = Field(default_factory=list[str], max_length=16)
    unavailable_reasons: list[str] = Field(default_factory=list[str], max_length=8)
    excerpt_snapshots: list[ConversationExcerptSnapshot] = Field(
        default_factory=list[ConversationExcerptSnapshot],
        max_length=8,
    )
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_context_inventory(self) -> ConversationRetrievalRecord:
        if self.retrieval_actions != self.question_plan.retrieval_actions:
            raise ValueError(
                "Durable retrieval actions must exactly match the validated question plan"
            )
        evidence_ids = [item.evidence_id for item in self.evidence_references]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Durable evidence references must have unique IDs")
        if self.supplied_evidence_ids != evidence_ids:
            raise ValueError(
                "Supplied evidence IDs must exactly match ordered evidence references"
            )
        for name, values in (
            ("finding", self.supplied_finding_ids),
            ("report claim", self.supplied_report_claim_ids),
            ("policy", self.supplied_policy_ids),
            ("recent-message ordinal", self.recent_message_ordinals),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Durable {name} inventory must be unique")
        if self.recent_message_ordinals != sorted(self.recent_message_ordinals):
            raise ValueError("Recent-message ordinals must be ordered")
        if any(ordinal < 1 for ordinal in self.recent_message_ordinals):
            raise ValueError("Recent-message ordinals must be positive")
        reference_ids = set(evidence_ids)
        snapshots = [item.evidence_id for item in self.excerpt_snapshots]
        if len(snapshots) != len(set(snapshots)):
            raise ValueError("Excerpt snapshots must have unique evidence IDs")
        if unknown := set(snapshots) - reference_ids:
            raise ValueError(
                f"Excerpt snapshots reference unsupplied evidence IDs: {sorted(unknown)}"
            )
        if sum(len(item.text) for item in self.excerpt_snapshots) > 24_000:
            raise ValueError("Durable excerpt snapshots exceed the turn text budget")
        if (
            sum(item.text.count("\n") + 1 for item in self.excerpt_snapshots)
            > 180
        ):
            raise ValueError("Durable excerpt snapshots exceed the turn line budget")
        return self


class ConversationRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationSummaryItem(DomainModel):
    text: str = Field(min_length=1, max_length=1000)
    source_ordinals: list[int] = Field(min_length=1, max_length=8)
    finding_ids: list[str] = Field(default_factory=list[str], max_length=12)
    evidence_ids: list[str] = Field(default_factory=list[str], max_length=24)

    @model_validator(mode="after")
    def validate_sources(self) -> ConversationSummaryItem:
        if any(ordinal < 1 for ordinal in self.source_ordinals):
            raise ValueError("Summary-item source ordinals must be positive")
        if self.source_ordinals != sorted(set(self.source_ordinals)):
            raise ValueError("Summary-item source ordinals must be unique and ordered")
        for name, values in (
            ("finding", self.finding_ids),
            ("evidence", self.evidence_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Summary-item {name} references must be unique")
        return self


class ConversationSummary(DomainModel):
    narrative: str = Field(min_length=1, max_length=6000)
    discussed_finding_ids: list[str] = Field(default_factory=list[str], max_length=12)
    discussed_evidence_ids: list[str] = Field(default_factory=list[str], max_length=96)
    user_corrections: list[ConversationSummaryItem] = Field(
        default_factory=list[ConversationSummaryItem],
        max_length=12,
    )
    hypotheticals: list[ConversationSummaryItem] = Field(
        default_factory=list[ConversationSummaryItem],
        max_length=12,
    )
    unresolved_questions: list[ConversationSummaryItem] = Field(
        default_factory=list[ConversationSummaryItem],
        max_length=12,
    )

    @model_validator(mode="after")
    def validate_reference_sets(self) -> ConversationSummary:
        for name, values in (
            ("finding", self.discussed_finding_ids),
            ("evidence", self.discussed_evidence_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Summary {name} references must be unique")
        return self


class ReportConversation(DomainModel):
    conversation_id: str = Field(default_factory=lambda: new_id("conversation"))
    consultation_run_id: str
    case_id: str
    case_revision: int = Field(ge=1)
    atlas_version_id: str | None = None
    policy_index_version_id: str | None = None
    title: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    current_summary: ConversationSummary | None = None
    summary_through_ordinal: int = Field(default=0, ge=0)
    message_count: int = Field(default=0, ge=0)
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_summary_position(self) -> ReportConversation:
        if self.summary_through_ordinal > self.message_count:
            raise ValueError("Conversation summary cannot extend past message history")
        if self.current_summary is None and self.summary_through_ordinal:
            raise ValueError("Conversation summary position requires a typed summary")
        if self.current_summary is not None and self.summary_through_ordinal == 0:
            raise ValueError("A typed conversation summary requires covered history")
        return self


class ConversationMessage(DomainModel):
    message_id: str = Field(default_factory=lambda: new_id("message"))
    conversation_id: str
    ordinal: int = Field(ge=1)
    role: ConversationRole
    text: str = Field(min_length=1, max_length=20_000)
    question_type: str | None = None
    retrieved_context: ConversationRetrievalRecord | None = None
    answer: ConversationAnswer | None = None
    model_identity: str | None = None
    prompt_identities: list[str] = Field(default_factory=list[str])
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_role_payload(self) -> ConversationMessage:
        if self.role == ConversationRole.USER:
            if (
                self.answer is not None
                or self.retrieved_context is not None
                or self.model_identity is not None
                or self.prompt_identities
                or self.question_type is not None
            ):
                raise ValueError("User messages cannot contain assistant audit data")
            return self
        if self.answer is None or self.retrieved_context is None:
            raise ValueError(
                "Assistant messages require a structured answer and retrieval record"
            )
        if self.model_identity is None or not self.model_identity.strip():
            raise ValueError("Assistant messages require a model identity")
        if not self.prompt_identities or any(
            not item.strip() for item in self.prompt_identities
        ):
            raise ValueError("Assistant messages require executed prompt identities")
        if self.question_type is None or not self.question_type.strip():
            raise ValueError("Assistant messages require a question type")
        return self


class ConversationMessageView(DomainModel):
    ordinal: int = Field(ge=1)
    role: ConversationRole
    text: str = Field(max_length=2000)
    relevant_finding_ids: list[str] = Field(default_factory=list[str], max_length=12)
    relevant_evidence_ids: list[str] = Field(default_factory=list[str], max_length=48)
    uncertainty: list[str] = Field(default_factory=list[str], max_length=10)


class ConversationSummaryRevision(DomainModel):
    conversation_id: str
    summary_revision: int = Field(ge=1)
    through_ordinal: int = Field(ge=1)
    summary: ConversationSummary
    model_identity: str = Field(min_length=1)
    prompt_identity: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)


class ConversationErrorRecord(DomainModel):
    error_id: str = Field(default_factory=lambda: new_id("conversation_error"))
    conversation_id: str
    user_message_id: str
    stage: Literal[
        "classification",
        "retrieval",
        "answering",
        "validation",
        "persistence",
        "summarization",
    ]
    errors: list[str] = Field(min_length=1)
    model_identity: str | None = None
    prompt_identities: list[str] = Field(default_factory=list[str])
    question_plan: ReportQuestionPlan | None = None
    retrieval_record: ConversationRetrievalRecord | None = None
    attempted_answer: ConversationAnswer | None = None
    context_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_failed_attempt(self) -> ConversationErrorRecord:
        if self.stage == "validation" and (
            self.question_plan is None
            or self.retrieval_record is None
            or self.attempted_answer is None
            or self.context_hash is None
        ):
            raise ValueError(
                "Validation failures require the complete bounded attempted-answer record"
            )
        return self


class FindingDigest(DomainModel):
    finding_id: str = Field(pattern=r"^FIND-[0-9]{3}$")
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    concern_cluster_id: str | None = None
    importance: FindingImportance
    importance_rationale: str = Field(min_length=1)
    confidence: Confidence
    consequence: str = Field(min_length=1)

    @classmethod
    def from_finding(cls, finding: ArchitecturalFinding) -> FindingDigest:
        return cls(
            finding_id=finding.finding_id,
            title=finding.title,
            summary=finding.summary,
            concern_cluster_id=finding.concern_cluster_id,
            importance=finding.importance,
            importance_rationale=finding.importance_rationale,
            confidence=finding.confidence,
            consequence=finding.consequence,
        )


class PinnedCaseSummary(DomainModel):
    case_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    title: str = Field(min_length=1)
    problem_statement: str = Field(min_length=1)
    desired_outcome: str = Field(min_length=1)
    actors_and_workflows: list[str] = Field(default_factory=list[str])
    functional_requirements: list[str] = Field(default_factory=list[str])
    quality_attributes: list[str] = Field(default_factory=list[str])
    technical_constraints: list[str] = Field(default_factory=list[str])
    organisational_constraints: list[str] = Field(default_factory=list[str])
    derived_constraints: list[str] = Field(default_factory=list[str])
    confirmed_facts: list[str] = Field(default_factory=list[str])
    expected_future_changes: list[str] = Field(default_factory=list[str])
    non_goals: list[str] = Field(default_factory=list[str])
    assumptions: list[str] = Field(default_factory=list[str])


class ReportSummary(DomainModel):
    report_id: str
    disposition: RecommendationDisposition
    decision_summary: SupportedStatement
    problem_and_desired_outcome: str
    important_design_forces: list[DesignForce] = Field(max_length=12)
    recommended_architecture: SupportedStatement
    alternatives: list[CaseAlternative] = Field(max_length=5)
    scenarios: list[ScenarioEvaluation] = Field(max_length=4)
    implementation_sequence: list[SupportedStatement] = Field(max_length=8)
    confidence: Confidence
    reversal_conditions: list[SupportedStatement] = Field(max_length=8)
    revisit_triggers: list[SupportedStatement] = Field(max_length=8)
    policies: list[PolicyEvidenceSummary] = Field(max_length=12)


class ReportQuestionPlanningContext(DomainModel):
    question: str = Field(min_length=1, max_length=4000)
    pinned_case: PinnedCaseSummary
    report_summary: ReportSummary
    finding_digests: list[FindingDigest] = Field(min_length=1, max_length=12)
    conversation_summary: ConversationSummary | None = None
    recent_messages: list[ConversationMessageView] = Field(max_length=8)
    prior_evidence_references: list[ConversationEvidenceReference] = Field(
        default_factory=list[ConversationEvidenceReference],
        max_length=96,
    )


class ConversationAtlasEvidence(DomainModel):
    action: ConversationRetrievalAction
    evidence_references: list[ConversationEvidenceReference] = Field(
        default_factory=list[ConversationEvidenceReference],
        max_length=96,
    )
    query_summary: str = Field(default="", max_length=24_000)
    ordered_node_ids: list[str] = Field(default_factory=list[str], max_length=24)
    nodes: list[AtlasNodeSummary] = Field(default_factory=list[AtlasNodeSummary], max_length=24)
    relationships: list[AtlasRelationshipEvidence] = Field(
        default_factory=list[AtlasRelationshipEvidence],
        max_length=96,
    )
    metrics: list[AtlasMetricValue] = Field(
        default_factory=list[AtlasMetricValue],
        max_length=48,
    )
    signals: list[ObscuritySignal] = Field(
        default_factory=list[ObscuritySignal],
        max_length=24,
    )
    excerpts: list[SourceExcerpt] = Field(
        default_factory=list[SourceExcerpt],
        max_length=8,
    )
    test_ids: list[str] = Field(default_factory=list[str], max_length=24)
    unavailable_reason: str | None = Field(default=None, max_length=24_000)
    truncated: bool = False


class ReportConversationContext(DomainModel):
    conversation_id: str
    run_id: str
    case_id: str
    case_revision: int = Field(ge=1)
    atlas_version_id: str | None = None
    policy_index_version_id: str | None = None
    question: str = Field(min_length=1, max_length=4000)
    question_plan: ReportQuestionPlan
    pinned_case: PinnedCaseSummary
    report_summary: ReportSummary
    finding_digests: list[FindingDigest] = Field(min_length=1, max_length=12)
    conversation_summary: ConversationSummary | None = None
    recent_messages: list[ConversationMessageView] = Field(max_length=8)
    evidence_references: list[ConversationEvidenceReference] = Field(
        default_factory=list[ConversationEvidenceReference],
        max_length=128,
    )
    retrieved_findings: list[ArchitecturalFinding] = Field(max_length=12)
    retrieved_claims: list[Claim] = Field(max_length=16)
    retrieved_concern_analyses: list[ConcernAnalysis] = Field(max_length=4)
    retrieved_atlas_evidence: list[ConversationAtlasEvidence] = Field(max_length=8)
    retrieved_policies: list[RetrievedPolicy] = Field(max_length=8)
    retrieved_alternatives: list[CaseAlternative] = Field(max_length=5)
    retrieved_scenarios: list[ScenarioEvaluation] = Field(max_length=4)
    evidence_scope_notes: list[str] = Field(default_factory=list[str], max_length=8)

    @model_validator(mode="after")
    def validate_evidence_inventory(self) -> ReportConversationContext:
        evidence_ids = [item.evidence_id for item in self.evidence_references]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Conversation context evidence IDs must be unique")
        nested_ids = [
            item.evidence_id
            for result in self.retrieved_atlas_evidence
            for item in result.evidence_references
        ]
        if unknown := set(nested_ids) - set(evidence_ids):
            raise ValueError(
                f"Atlas evidence references are absent from context inventory: "
                f"{sorted(unknown)}"
            )
        return self
