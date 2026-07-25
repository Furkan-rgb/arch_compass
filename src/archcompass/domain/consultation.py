"""Consultation workflow, evidence, audit, and report contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, RootModel, model_validator

from archcompass.domain.atlas import (
    AtlasEdge,
    AtlasMetricValue,
    AtlasNode,
    AtlasNodeEvidence,
    AtlasNodeSummary,
    AtlasOverview,
    AtlasQueryPlan,
    AtlasRelationshipEvidence,
    AtlasSelectionReason,
    MetricProfile,
    ObscuritySignal,
    SourceExcerpt,
    SourceLocation,
)
from archcompass.domain.base import DomainModel, new_id, utc_now
from archcompass.domain.case import CaseAlternative, Confidence
from archcompass.domain.diagnostics import FailureDiagnostic, FailureDiagnosticCode
from archcompass.domain.policy import (
    PolicyApplicabilityContext,
    PolicyConflict,
    PolicyEvidenceSummary,
    RetrievedPolicy,
)


class ClaimClassification(StrEnum):
    CONFIRMED_REQUIREMENT = "confirmed_user_requirement"
    DERIVED_CONSTRAINT = "derived_constraint"
    REPOSITORY_OBSERVATION = "repository_observation"
    POLICY_GUIDANCE = "policy_guidance"
    SCENARIO_ASSUMPTION = "scenario_assumption"
    ADVISOR_INFERENCE = "advisor_inference"


class AtlasEvidenceReference(DomainModel):
    node_id: str = Field(min_length=1)
    # Optional because non-repository claims may cite a node without a span.
    # Evidence validation rejects a repository observation that omits it.
    location: SourceLocation | None = None


class Claim(DomainModel):
    claim_id: str = Field(default_factory=lambda: new_id("claim"), min_length=1)
    text: str = Field(min_length=1)
    classification: ClaimClassification
    atlas_references: list[AtlasEvidenceReference] = Field(
        default_factory=list[AtlasEvidenceReference]
    )
    policy_ids: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def require_unique_references(self) -> Claim:
        if not self.text.strip():
            raise ValueError("Claim text must not be blank")
        node_ids = [reference.node_id for reference in self.atlas_references]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Claim atlas references must be unique")
        if len(self.policy_ids) != len(set(self.policy_ids)):
            raise ValueError("Claim policy references must be unique")
        return self


class DesignForce(DomainModel):
    force_id: str = Field(default_factory=lambda: new_id("force"), min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    importance: str = Field(min_length=1)


class ConcernCluster(DomainModel):
    cluster_id: str = Field(default_factory=lambda: new_id("cluster"), min_length=1)
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    design_force_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_force_ids(self) -> ConcernCluster:
        if len(self.design_force_ids) != len(set(self.design_force_ids)):
            raise ValueError("A concern cluster may reference each design force only once")
        return self


class ConcernClusterList(RootModel[list[ConcernCluster]]):
    root: list[ConcernCluster] = Field(min_length=1, max_length=4)


def cluster_partition_errors(
    forces: list[DesignForce], clusters: list[ConcernCluster]
) -> list[str]:
    """Return deterministic errors when clusters are not an exact force partition."""
    errors: list[str] = []
    if not 1 <= len(clusters) <= 4:
        errors.append("Concern clustering must contain between one and four clusters")
    force_ids = [force.force_id for force in forces]
    expected = set(force_ids)
    assigned = [force_id for cluster in clusters for force_id in cluster.design_force_ids]
    unknown = sorted(set(assigned) - expected)
    missing = sorted(expected - set(assigned))
    duplicates = sorted(force_id for force_id in set(assigned) if assigned.count(force_id) > 1)
    if unknown:
        errors.append(f"Concern clusters reference unknown force IDs: {unknown}")
    if missing:
        errors.append(f"Concern clusters omit force IDs: {missing}")
    if duplicates:
        errors.append(f"Concern clusters assign force IDs more than once: {duplicates}")
    cluster_ids = [cluster.cluster_id for cluster in clusters]
    if len(cluster_ids) != len(set(cluster_ids)):
        errors.append("Concern cluster IDs must be unique")
    return errors


def cluster_partition_diagnostics(
    forces: list[DesignForce], clusters: list[ConcernCluster]
) -> list[FailureDiagnostic]:
    """Describe an invalid partition without exposing model text or internal IDs."""
    diagnostics: list[FailureDiagnostic] = []
    if not 1 <= len(clusters) <= 4:
        diagnostics.append(
            FailureDiagnostic(
                code=FailureDiagnosticCode.CLUSTER_COUNT_OUT_OF_RANGE,
                count=len(clusters),
            )
        )
    handle_by_id = {
        force.force_id: f"F{ordinal}" for ordinal, force in enumerate(forces, start=1)
    }
    expected = set(handle_by_id)
    assigned = [force_id for cluster in clusters for force_id in cluster.design_force_ids]
    unknown_count = sum(force_id not in expected for force_id in assigned)
    if unknown_count:
        diagnostics.append(
            FailureDiagnostic(
                code=FailureDiagnosticCode.UNKNOWN_FORCE_REFERENCES,
                count=unknown_count,
            )
        )
    missing_handles = [
        handle
        for force_id, handle in handle_by_id.items()
        if force_id not in set(assigned)
    ]
    if missing_handles:
        diagnostics.append(
            FailureDiagnostic(
                code=FailureDiagnosticCode.MISSING_FORCE_REFERENCES,
                force_handles=missing_handles,
            )
        )
    duplicate_handles = [
        handle
        for force_id, handle in handle_by_id.items()
        if assigned.count(force_id) > 1
    ]
    if duplicate_handles:
        diagnostics.append(
            FailureDiagnostic(
                code=FailureDiagnosticCode.DUPLICATE_FORCE_REFERENCES,
                force_handles=duplicate_handles,
            )
        )
    cluster_ids = [cluster.cluster_id for cluster in clusters]
    duplicate_cluster_count = sum(
        cluster_ids.count(cluster_id) > 1 for cluster_id in set(cluster_ids)
    )
    if duplicate_cluster_count:
        diagnostics.append(
            FailureDiagnostic(
                code=FailureDiagnosticCode.DUPLICATE_CLUSTER_IDS,
                count=duplicate_cluster_count,
            )
        )
    return diagnostics


class GlobalContext(DomainModel):
    case_id: str
    revision: int = Field(ge=1)
    title: str
    problem: str
    desired_outcome: str
    actors_and_workflows: list[str] = Field(default_factory=list[str])
    goals: list[str]
    constraints: list[str]
    future_changes: list[str]
    non_goals: list[str]
    confirmed_facts: list[str]
    assumptions: list[str]
    unresolved_questions: list[str] = Field(default_factory=list[str])
    user_design_forces: list[str] = Field(default_factory=list[str])
    policy_applicability: PolicyApplicabilityContext = Field(
        default_factory=PolicyApplicabilityContext
    )
    atlas_overview: AtlasOverview | None = None
    atlas_summary: str | None = None


class FocusedNodeSummary(DomainModel):
    node_id: str
    path: str = ""
    qualified_name: str = ""
    node_type: str = "unknown"
    location: SourceLocation | None = None
    summary: str = ""
    selection_reasons: list[AtlasSelectionReason] = Field(
        default_factory=list[AtlasSelectionReason]
    )

    @classmethod
    def from_node(cls, node: AtlasNode, *, summary: str = "") -> FocusedNodeSummary:
        location = (
            SourceLocation(
                path=node.path,
                start_line=node.start_line,
                end_line=node.end_line,
            )
            if node.start_line is not None and node.end_line is not None
            else None
        )
        return cls(
            node_id=node.atlas_id,
            path=node.path,
            qualified_name=node.qualified_name,
            node_type=node.node_type,
            location=location,
            summary=summary,
        )

    @classmethod
    def from_summary(
        cls,
        node: AtlasNodeSummary,
        *,
        summary: str = "",
        selection_reasons: list[AtlasSelectionReason] | None = None,
    ) -> FocusedNodeSummary:
        return cls(
            node_id=node.node_id,
            path=node.path,
            qualified_name=node.qualified_name,
            node_type=node.node_type,
            location=node.location,
            summary=summary,
            selection_reasons=selection_reasons or [],
        )


class FocusedAnalysisPacket(DomainModel):
    cluster: ConcernCluster
    node_summaries: list[FocusedNodeSummary] = Field(default_factory=list[FocusedNodeSummary])
    node_evidence: list[AtlasNodeEvidence] = Field(default_factory=list[AtlasNodeEvidence])
    metrics: list[MetricProfile] = Field(default_factory=list[MetricProfile])
    relationships: list[AtlasEdge] = Field(default_factory=list[AtlasEdge])
    relationship_evidence: list[AtlasRelationshipEvidence] = Field(
        default_factory=list[AtlasRelationshipEvidence]
    )
    test_ids: list[str] = Field(default_factory=list[str])
    test_evidence: list[AtlasNodeSummary] = Field(default_factory=list[AtlasNodeSummary])
    excerpts: list[SourceExcerpt] = Field(default_factory=list[SourceExcerpt])
    policies: list[RetrievedPolicy] = Field(default_factory=list[RetrievedPolicy])
    assumptions: list[str] = Field(default_factory=list[str])
    uncertainty: list[str] = Field(min_length=1)

    @property
    def concern(self) -> str:
        return self.cluster.title

    @property
    def design_force_ids(self) -> list[str]:
        return self.cluster.design_force_ids

    @property
    def surfaced_node_ids(self) -> set[str]:
        return {
            *(summary.node_id for summary in self.node_summaries),
            *(excerpt.node_id for excerpt in self.excerpts),
        }


class ConcernAnalysis(DomainModel):
    cluster_id: str = Field(min_length=1)
    concern: str = Field(min_length=1)
    findings: list[Claim] = Field(min_length=1)
    implications: list[str] = Field(min_length=1)
    policy_conflicts: list[PolicyConflict] = Field(default_factory=list[PolicyConflict])


class ScenarioEvaluation(DomainModel):
    scenario: str = Field(min_length=1)
    assumptions: list[str]
    alternative_results: dict[str, str] = Field(min_length=1)
    conclusion: str = Field(min_length=1)


class RecommendationDisposition(StrEnum):
    INTRODUCE_BOUNDARY = "introduce_boundary"
    MOVE_RESPONSIBILITY = "move_responsibility"
    KEEP_LOCAL = "keep_local"
    DELAY = "delay"
    PRESERVE = "preserve"
    GATHER_INFORMATION = "gather_information"


class FindingImportance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ArchitecturalFinding(DomainModel):
    finding_id: str = Field(pattern=r"^FIND-[0-9]{3}$")
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    concern_cluster_id: str | None = None
    importance: FindingImportance
    importance_rationale: str = Field(min_length=1)
    confidence: Confidence
    consequence: str = Field(min_length=1)
    claim_ids: list[str] = Field(min_length=1)
    atlas_node_ids: list[str] = Field(default_factory=list[str])
    policy_ids: list[str] = Field(default_factory=list[str])
    affected_locations: list[AtlasNodeSummary] = Field(
        default_factory=list[AtlasNodeSummary]
    )
    metric_observations: list[AtlasMetricValue] = Field(
        default_factory=list[AtlasMetricValue]
    )
    obscurity_signals: list[ObscuritySignal] = Field(
        default_factory=list[ObscuritySignal]
    )
    recommended_response: str = Field(min_length=1)
    uncertainty: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def validate_references(self) -> ArchitecturalFinding:
        for name, values in (
            ("claim", self.claim_ids),
            ("Atlas node", self.atlas_node_ids),
            ("policy", self.policy_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Architectural finding {name} references must be unique")
        surfaced = set(self.atlas_node_ids)
        nested_node_ids = {
            *(item.node_id for item in self.affected_locations),
            *(item.node_id for item in self.metric_observations),
            *(item.node_id for item in self.obscurity_signals),
        }
        if unknown := nested_node_ids - surfaced:
            raise ValueError(
                "Architectural finding evidence references absent Atlas nodes: "
                f"{sorted(unknown)}"
            )
        if any(not item.strip() for item in self.uncertainty):
            raise ValueError("Architectural finding uncertainty must not be blank")
        return self


class SupportedStatement(DomainModel):
    text: str = Field(min_length=1)
    classification: ClaimClassification
    supporting_claim_ids: list[str] = Field(json_schema_extra={"minItems": 1})

    @model_validator(mode="after")
    def require_support(self) -> SupportedStatement:
        if not self.text.strip():
            raise ValueError("Supported statement text must not be blank")
        if len(self.supporting_claim_ids) != len(set(self.supporting_claim_ids)):
            raise ValueError("Supporting claim IDs must be unique")
        if not self.supporting_claim_ids:
            raise ValueError("A supported statement must cite at least one claim")
        return self

    def __str__(self) -> str:
        return self.text


class ADRRecord(DomainModel):
    title: str = Field(min_length=1)
    status: str = "proposed"
    context: str = Field(min_length=1)
    decision: SupportedStatement
    consequences: list[SupportedStatement] = Field(min_length=1)


class RecommendationReport(DomainModel):
    schema_version: Literal[3]
    report_id: str = Field(default_factory=lambda: new_id("report"))
    disposition: RecommendationDisposition
    decision_summary: SupportedStatement
    problem_and_desired_outcome: str = Field(min_length=1)
    confirmed_context: list[Claim]
    assumptions_and_unresolved_questions: list[Claim]
    important_design_forces: list[DesignForce] = Field(min_length=1)
    findings: list[ArchitecturalFinding] = Field(min_length=1, max_length=12)
    repository_observations: list[Claim]
    relevant_policies: list[Claim]
    policy_evidence: list[PolicyEvidenceSummary] = Field(
        default_factory=list[PolicyEvidenceSummary]
    )
    policy_conflicts: list[PolicyConflict] = Field(default_factory=list[PolicyConflict])
    recommended_architecture: SupportedStatement
    responsibility_allocation: list[SupportedStatement] = Field(min_length=1)
    conceptual_interfaces: list[SupportedStatement]
    alternatives_considered: list[CaseAlternative] = Field(min_length=1)
    scenario_analysis: list[ScenarioEvaluation] = Field(min_length=1)
    change_amplification_analysis: SupportedStatement
    trade_offs: list[SupportedStatement] = Field(min_length=1)
    implementation_sequence: list[SupportedStatement] = Field(min_length=1)
    confidence: Confidence
    reversal_conditions: list[SupportedStatement] = Field(min_length=1)
    revisit_triggers: list[SupportedStatement] = Field(min_length=1)
    adr: ADRRecord
    evidence_appendix: list[Claim]

    @model_validator(mode="after")
    def validate_report_contract(self) -> RecommendationReport:
        if not self.problem_and_desired_outcome.strip():
            raise ValueError("Problem and desired outcome must not be blank")
        prose = [
            self.confidence.rationale,
            self.adr.title,
            self.adr.status,
            self.adr.context,
            *[
                text
                for force in self.important_design_forces
                for text in (force.title, force.description, force.importance)
            ],
            *[
                text
                for alternative in self.alternatives_considered
                for text in (alternative.title, alternative.summary)
            ],
            *[
                text
                for scenario in self.scenario_analysis
                for text in (
                    scenario.scenario,
                    scenario.conclusion,
                    *scenario.assumptions,
                    *scenario.alternative_results.values(),
                )
            ],
            *[
                text
                for conflict in self.policy_conflicts
                for text in (conflict.explanation, conflict.reconciliation)
            ],
            *[item.title for item in self.policy_evidence],
        ]
        if any(not text.strip() for text in prose):
            raise ValueError("Report prose must not contain blank content")
        if any(not scenario.assumptions for scenario in self.scenario_analysis):
            raise ValueError("Every scenario requires at least one explicit assumption")
        if not self.evidence_appendix:
            raise ValueError("A recommendation report requires a nonempty evidence appendix")
        section_kinds = (
            (
                "confirmed_context",
                self.confirmed_context,
                {ClaimClassification.CONFIRMED_REQUIREMENT},
            ),
            (
                "assumptions_and_unresolved_questions",
                self.assumptions_and_unresolved_questions,
                {ClaimClassification.SCENARIO_ASSUMPTION},
            ),
            (
                "repository_observations",
                self.repository_observations,
                {ClaimClassification.REPOSITORY_OBSERVATION},
            ),
            (
                "relevant_policies",
                self.relevant_policies,
                {ClaimClassification.POLICY_GUIDANCE},
            ),
        )
        for name, claims, allowed in section_kinds:
            wrong = [claim.claim_id for claim in claims if claim.classification not in allowed]
            if wrong:
                raise ValueError(
                    f"{name} contains claims with inconsistent classifications: {wrong}"
                )
        alternative_ids = [item.id for item in self.alternatives_considered]
        if len(alternative_ids) != len(set(alternative_ids)):
            raise ValueError("Alternative IDs must be unique")
        expected = set(alternative_ids)
        for scenario in self.scenario_analysis:
            actual = set(scenario.alternative_results)
            if actual != expected:
                raise ValueError(
                    f"Scenario alternative coverage mismatch; missing={sorted(expected - actual)}, "
                    f"extra={sorted(actual - expected)}"
                )
        policy_ids = {item.id for item in self.policy_evidence}
        if len(policy_ids) != len(self.policy_evidence):
            raise ValueError("Policy evidence IDs must be unique")
        cited_policy_ids = {
            policy_id
            for claim in [*self.relevant_policies, *self.evidence_appendix]
            for policy_id in claim.policy_ids
        }
        missing_policy_evidence = cited_policy_ids - policy_ids
        if missing_policy_evidence:
            raise ValueError(
                "Cited policies are absent from canonical policy evidence: "
                f"{sorted(missing_policy_evidence)}"
            )
        if any(
            not section.strip()
            for item in self.policy_evidence
            for section in item.matched_sections
        ):
            raise ValueError("Policy evidence matched sections must not be blank")
        for conflict in self.policy_conflicts:
            unknown = set(conflict.policy_ids) - policy_ids
            if unknown:
                raise ValueError(
                    f"Report policy conflict references policies absent from evidence: "
                    f"{sorted(unknown)}"
                )
        claim_registry = {
            claim.claim_id: claim
            for claim in [
                *self.confirmed_context,
                *self.assumptions_and_unresolved_questions,
                *self.repository_observations,
                *self.relevant_policies,
                *self.evidence_appendix,
            ]
        }
        finding_ids = [finding.finding_id for finding in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("Architectural finding IDs must be unique")
        for finding in self.findings:
            if unknown_claims := set(finding.claim_ids) - set(claim_registry):
                raise ValueError(
                    f"Finding {finding.finding_id} references unknown claims: "
                    f"{sorted(unknown_claims)}"
                )
            cited_claims = [claim_registry[claim_id] for claim_id in finding.claim_ids]
            supported_nodes = {
                reference.node_id
                for claim in cited_claims
                for reference in claim.atlas_references
            }
            supported_policies = {
                policy_id for claim in cited_claims for policy_id in claim.policy_ids
            }
            if unknown_nodes := set(finding.atlas_node_ids) - supported_nodes:
                raise ValueError(
                    f"Finding {finding.finding_id} references unsupported Atlas nodes: "
                    f"{sorted(unknown_nodes)}"
                )
            if unknown_policies := set(finding.policy_ids) - supported_policies:
                raise ValueError(
                    f"Finding {finding.finding_id} references unsupported policies: "
                    f"{sorted(unknown_policies)}"
                )
        return self

    def supported_statements(self) -> list[SupportedStatement]:
        return [
            self.decision_summary,
            self.recommended_architecture,
            *self.responsibility_allocation,
            *self.conceptual_interfaces,
            self.change_amplification_analysis,
            *self.trade_offs,
            *self.implementation_sequence,
            *self.reversal_conditions,
            *self.revisit_triggers,
            self.adr.decision,
            *self.adr.consequences,
        ]


class ConsultationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ConsultationFailureStage(StrEnum):
    ATLAS_RESOLUTION = "atlas_resolution"
    POLICY = "policy"
    DESIGN_FORCES = "design_forces"
    CLUSTERING = "clustering"
    QUERY_PLANNING = "query_planning"
    QUERY_EXECUTION = "query_execution"
    POLICY_RETRIEVAL = "policy_retrieval"
    CONCERN_ANALYSIS = "concern_analysis"
    ALTERNATIVES = "alternatives"
    SCENARIOS = "scenarios"
    SYNTHESIS = "synthesis"
    VALIDATION = "validation"
    RENDERING = "rendering"
    COMMIT = "commit"


class ClusterQueryPlan(DomainModel):
    cluster_id: str
    plan: AtlasQueryPlan

    @property
    def iteration(self) -> int:
        return self.plan.iteration

    @property
    def rationale(self) -> str:
        return self.plan.rationale

    @property
    def queries(self) -> list[object]:
        return list(self.plan.queries)


class ConsultationRun(DomainModel):
    schema_version: Literal[3]
    run_id: str = Field(default_factory=lambda: new_id("run"))
    status: ConsultationStatus
    case_id: str
    input_case_revision: int = Field(ge=1)
    result_case_revision: int | None = Field(default=None, ge=2)
    atlas_version_id: str | None = None
    policy_index_version_id: str | None = None
    reasoning_model: str
    embedding_model: str
    config_hash: str
    prompt_identities: list[str] = Field(default_factory=list[str])
    design_forces: list[DesignForce] = Field(default_factory=list[DesignForce])
    clusters: list[ConcernCluster] = Field(default_factory=list[ConcernCluster])
    query_plans: list[ClusterQueryPlan] = Field(default_factory=list[ClusterQueryPlan])
    focused_packets: list[FocusedAnalysisPacket] = Field(
        default_factory=list[FocusedAnalysisPacket]
    )
    concern_analyses: list[ConcernAnalysis] = Field(default_factory=list[ConcernAnalysis])
    alternatives: list[CaseAlternative] = Field(default_factory=list[CaseAlternative])
    scenarios: list[ScenarioEvaluation] = Field(default_factory=list[ScenarioEvaluation])
    report: RecommendationReport | None = None
    markdown_report: str | None = None
    initial_validation_errors: list[str] = Field(default_factory=list[str])
    repair_actions: list[str] = Field(default_factory=list[str])
    final_validation_errors: list[str] = Field(default_factory=list[str])
    stage_timings: dict[str, float] = Field(default_factory=dict[str, float])
    failure_stage: ConsultationFailureStage | None = None
    sanitized_errors: list[str] = Field(default_factory=list[str])
    failure_diagnostics: list[FailureDiagnostic] = Field(
        default_factory=list[FailureDiagnostic]
    )
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)
    execution_metadata: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])

    @model_validator(mode="after")
    def validate_run_contract(self) -> ConsultationRun:
        if self.completed_at < self.started_at:
            raise ValueError("A consultation cannot complete before it starts")
        if any(duration < 0 for duration in self.stage_timings.values()):
            raise ValueError("Stage timings must be non-negative")
        if self.status == ConsultationStatus.SUCCEEDED:
            if self.result_case_revision != self.input_case_revision + 1:
                raise ValueError("A successful run must produce the next case revision")
            if self.report is None or not self.markdown_report:
                raise ValueError("A successful run requires structured and Markdown reports")
            if (
                self.failure_stage is not None
                or self.sanitized_errors
                or self.failure_diagnostics
            ):
                raise ValueError("A successful run cannot contain terminal failure details")
            if self.final_validation_errors:
                raise ValueError("A successful run cannot retain final validation errors")
            if self.initial_validation_errors and not self.repair_actions:
                raise ValueError(
                    "A successful repaired run must record deterministic repair actions"
                )
        else:
            if self.result_case_revision is not None:
                raise ValueError("A failed run cannot produce a case revision")
            if self.failure_stage is None or not self.sanitized_errors:
                raise ValueError("A failed run requires a failure stage and sanitized error")
        cluster_ids = {cluster.cluster_id for cluster in self.clusters}
        if self.status == ConsultationStatus.SUCCEEDED and self.clusters:
            partition_errors = cluster_partition_errors(self.design_forces, self.clusters)
            if partition_errors:
                raise ValueError("; ".join(partition_errors))
            unknown_plans = {
                item.cluster_id for item in self.query_plans if item.cluster_id not in cluster_ids
            }
            unknown_packets = {
                item.cluster.cluster_id
                for item in self.focused_packets
                if item.cluster.cluster_id not in cluster_ids
            }
            if unknown_plans or unknown_packets:
                raise ValueError("Run query plans and packets must reference persisted clusters")
            packet_ids = [packet.cluster.cluster_id for packet in self.focused_packets]
            analysis_ids = [analysis.cluster_id for analysis in self.concern_analyses]
            if (
                set(packet_ids) != cluster_ids
                or len(packet_ids) != len(set(packet_ids))
                or set(analysis_ids) != cluster_ids
                or len(analysis_ids) != len(set(analysis_ids))
            ):
                raise ValueError(
                    "A successful run requires exactly one packet and analysis per concern cluster"
                )
            if self.report is not None:
                unknown_finding_clusters = {
                    finding.concern_cluster_id
                    for finding in self.report.findings
                    if finding.concern_cluster_id is not None
                    and finding.concern_cluster_id not in cluster_ids
                }
                if unknown_finding_clusters:
                    raise ValueError(
                        "Report findings reference unknown concern clusters: "
                        f"{sorted(unknown_finding_clusters)}"
                    )
        return self
