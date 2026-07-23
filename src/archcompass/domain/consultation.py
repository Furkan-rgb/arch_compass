"""Consultation workflow, evidence, audit, and report contracts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Literal, cast

from pydantic import Field, JsonValue, RootModel, model_validator

from archcompass.domain.atlas import (
    AtlasEdge,
    AtlasNode,
    AtlasQueryPlan,
    MetricProfile,
    SourceExcerpt,
    SourceLocation,
)
from archcompass.domain.base import DomainModel, new_id, utc_now
from archcompass.domain.case import ArchitectureCase, CaseAlternative, Confidence
from archcompass.domain.policy import (
    PolicyConflict,
    PolicyEvidenceSummary,
    PolicyScope,
    PolicyStrength,
    RetrievedPolicy,
)


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    source = cast(Mapping[object, object], value)
    return {str(key): item for key, item in source.items()}


def _objects(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast(list[object], value)


class ClaimClassification(StrEnum):
    CONFIRMED_REQUIREMENT = "confirmed_user_requirement"
    DERIVED_CONSTRAINT = "derived_constraint"
    REPOSITORY_OBSERVATION = "repository_observation"
    POLICY_GUIDANCE = "policy_guidance"
    SCENARIO_ASSUMPTION = "scenario_assumption"
    ADVISOR_INFERENCE = "advisor_inference"


class AtlasEvidenceReference(DomainModel):
    node_id: str = Field(min_length=1)
    # Optional only so schema-v1 reports remain readable. New repository
    # observations are rejected by evidence validation unless this is present.
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
    atlas_summary: str | None = None


class FocusedNodeSummary(DomainModel):
    node_id: str
    path: str = ""
    qualified_name: str = ""
    node_type: str = "unknown"
    location: SourceLocation | None = None
    summary: str = ""

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


class FocusedAnalysisPacket(DomainModel):
    cluster: ConcernCluster
    node_summaries: list[FocusedNodeSummary] = Field(default_factory=list[FocusedNodeSummary])
    metrics: list[MetricProfile] = Field(default_factory=list[MetricProfile])
    relationships: list[AtlasEdge] = Field(default_factory=list[AtlasEdge])
    test_ids: list[str] = Field(default_factory=list[str])
    excerpts: list[SourceExcerpt] = Field(default_factory=list[SourceExcerpt])
    policies: list[RetrievedPolicy] = Field(default_factory=list[RetrievedPolicy])
    assumptions: list[str] = Field(default_factory=list[str])
    uncertainty: list[str] = Field(default_factory=list[str])

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_packet(cls, value: object) -> object:
        data = _mapping(value)
        if data is None or "cluster" in data:
            return value
        query_results = _objects(data.pop("query_results", [])) or []
        force_ids = [str(item) for item in (_objects(data.pop("design_force_ids", [])) or [])]
        concern = str(data.pop("concern", "Legacy concern"))
        reason = str(data.pop("reason", "Loaded from a schema-v1 consultation run"))
        summaries: dict[str, FocusedNodeSummary] = {}
        excerpts: list[object] = []
        for result in query_results:
            result_data = _mapping(result)
            if result_data is None:
                continue
            summary = str(result_data.get("summary", ""))
            for node_id in _objects(result_data.get("node_ids", [])) or []:
                summaries.setdefault(
                    str(node_id),
                    FocusedNodeSummary(node_id=str(node_id), summary=summary),
                )
            excerpts.extend(_objects(result_data.get("excerpts", [])) or [])
        data.update(
            {
                "cluster": {
                    "cluster_id": "cluster_legacy",
                    "title": concern,
                    "rationale": reason,
                    "design_force_ids": force_ids or ["force_legacy"],
                },
                "node_summaries": [
                    summary.model_dump(mode="json") for summary in summaries.values()
                ],
                "metrics": [],
                "relationships": [],
                "test_ids": [],
                "excerpts": excerpts,
            }
        )
        return data

    @property
    def concern(self) -> str:
        return self.cluster.title

    @property
    def reason(self) -> str:
        return self.cluster.rationale

    @property
    def design_force_ids(self) -> list[str]:
        return self.cluster.design_force_ids

    @property
    def surfaced_node_ids(self) -> set[str]:
        return {
            *(summary.node_id for summary in self.node_summaries),
            *(excerpt.node_id for excerpt in self.excerpts),
        }

    @property
    def query_results(self) -> list[FocusedNodeSummary]:
        """Schema-v1 API compatibility without serializing raw query results."""
        return self.node_summaries


class ConcernAnalysis(DomainModel):
    cluster_id: str = "cluster_legacy"
    concern: str = Field(min_length=1)
    findings: list[Claim] = Field(min_length=1)
    implications: list[str] = Field(min_length=1)
    policy_conflicts: list[PolicyConflict] = Field(default_factory=list[PolicyConflict])


class ScenarioEvaluation(DomainModel):
    scenario: str = Field(min_length=1)
    assumptions: list[str]
    alternative_results: dict[str, str] = Field(min_length=1)
    conclusion: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_results(cls, value: object) -> object:
        data = _mapping(value)
        if data is None:
            return value
        results = _objects(data.get("alternative_results"))
        if results is not None:
            data["alternative_results"] = {
                f"legacy_{index}": str(result) for index, result in enumerate(results, start=1)
            }
        return data


class RecommendationDisposition(StrEnum):
    INTRODUCE_BOUNDARY = "introduce_boundary"
    MOVE_RESPONSIBILITY = "move_responsibility"
    KEEP_LOCAL = "keep_local"
    DELAY = "delay"
    PRESERVE = "preserve"
    GATHER_INFORMATION = "gather_information"


class SupportedStatement(DomainModel):
    text: str = Field(min_length=1)
    classification: ClaimClassification
    supporting_claim_ids: list[str] = Field(default_factory=list[str])
    legacy: bool = False

    @model_validator(mode="after")
    def require_support(self) -> SupportedStatement:
        if not self.text.strip():
            raise ValueError("Supported statement text must not be blank")
        if len(self.supporting_claim_ids) != len(set(self.supporting_claim_ids)):
            raise ValueError("Supporting claim IDs must be unique")
        if not self.legacy and not self.supporting_claim_ids:
            raise ValueError("A new supported statement must cite at least one claim")
        return self

    @classmethod
    def legacy_value(cls, text: str) -> SupportedStatement:
        return cls(
            text=text,
            classification=ClaimClassification.ADVISOR_INFERENCE,
            supporting_claim_ids=[],
            legacy=True,
        )

    def casefold(self) -> str:
        """Allow schema-v1 string-style assertions while preserving the typed value."""
        return self.text.casefold()

    def __str__(self) -> str:
        return self.text


def _legacy_statement(value: object) -> object:
    if isinstance(value, str):
        return {
            "text": value,
            "classification": ClaimClassification.ADVISOR_INFERENCE,
            "supporting_claim_ids": [],
            "legacy": True,
        }
    return value


class ADRRecord(DomainModel):
    title: str = Field(min_length=1)
    status: str = "proposed"
    context: str = Field(min_length=1)
    decision: SupportedStatement
    consequences: list[SupportedStatement] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_strings(cls, value: object) -> object:
        data = _mapping(value)
        if data is None:
            return value
        data["decision"] = _legacy_statement(data.get("decision"))
        consequences = _objects(data.get("consequences"))
        if consequences is not None:
            data["consequences"] = [_legacy_statement(item) for item in consequences]
        return data


def _upgrade_scenario_mappings(scenarios: object, alternatives: object) -> object:
    scenario_items = _objects(scenarios)
    alternative_items = _objects(alternatives)
    if scenario_items is None or alternative_items is None:
        return scenarios
    alternative_ids: list[str] = []
    for raw_alternative in alternative_items:
        alternative = _mapping(raw_alternative)
        if alternative is not None and alternative.get("id"):
            alternative_ids.append(str(alternative["id"]))
    upgraded: list[object] = []
    for raw_scenario in scenario_items:
        scenario = _mapping(raw_scenario)
        if scenario is None:
            upgraded.append(raw_scenario)
            continue
        results = _objects(scenario.get("alternative_results"))
        if results is not None and len(results) == len(alternative_ids):
            scenario["alternative_results"] = dict(zip(alternative_ids, results, strict=True))
        upgraded.append(scenario)
    return upgraded


class RecommendationReport(DomainModel):
    schema_version: Literal[2] = 2
    report_id: str = Field(default_factory=lambda: new_id("report"))
    disposition: RecommendationDisposition
    decision_summary: SupportedStatement
    problem_and_desired_outcome: str = Field(min_length=1)
    confirmed_context: list[Claim]
    assumptions_and_unresolved_questions: list[Claim]
    important_design_forces: list[DesignForce] = Field(min_length=1)
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

    @model_validator(mode="before")
    @classmethod
    def upgrade_schema_v1(cls, value: object) -> object:
        data = _mapping(value)
        if data is None:
            return value
        legacy = data.get("schema_version") != 2
        data["schema_version"] = 2
        if not legacy:
            scalar_fields = (
                "decision_summary",
                "recommended_architecture",
                "change_amplification_analysis",
            )
            list_fields = (
                "responsibility_allocation",
                "conceptual_interfaces",
                "trade_offs",
                "implementation_sequence",
                "reversal_conditions",
                "revisit_triggers",
            )
            if any(isinstance(data.get(field), str) for field in scalar_fields):
                raise ValueError("Schema-v2 substantive report prose must use SupportedStatement")
            if any(
                any(isinstance(item, str) for item in (_objects(data.get(field)) or []))
                for field in list_fields
            ):
                raise ValueError("Schema-v2 substantive report lists must use SupportedStatement")
            return data
        text = str(data.get("decision_summary", "")).casefold()
        data.setdefault(
            "disposition",
            (
                RecommendationDisposition.KEEP_LOCAL
                if "keep" in text and "local" in text
                else (
                    RecommendationDisposition.MOVE_RESPONSIBILITY
                    if "provider" in text or "owner" in text
                    else RecommendationDisposition.GATHER_INFORMATION
                )
            ),
        )
        statement_fields = (
            "decision_summary",
            "recommended_architecture",
            "change_amplification_analysis",
        )
        for field in statement_fields:
            data[field] = _legacy_statement(data.get(field))
        list_fields = (
            "responsibility_allocation",
            "conceptual_interfaces",
            "trade_offs",
            "implementation_sequence",
            "reversal_conditions",
            "revisit_triggers",
        )
        for field in list_fields:
            items = _objects(data.get(field))
            if items is not None:
                data[field] = [_legacy_statement(item) for item in items]
        data["scenario_analysis"] = _upgrade_scenario_mappings(
            data.get("scenario_analysis"), data.get("alternatives_considered")
        )
        if "policy_evidence" not in data:
            policy_ids: list[str] = []
            for field in ("relevant_policies", "evidence_appendix"):
                for raw_claim in _objects(data.get(field, [])) or []:
                    claim = _mapping(raw_claim)
                    if claim is not None:
                        policy_ids.extend(
                            str(item)
                            for item in (_objects(claim.get("policy_ids", [])) or [])
                        )
            data["policy_evidence"] = [
                {
                    "id": policy_id,
                    "title": policy_id,
                    "scope": PolicyScope.GENERAL,
                    "strength": PolicyStrength.GUIDANCE,
                    "matched_sections": ["Legacy report; section metadata unavailable"],
                }
                for policy_id in dict.fromkeys(policy_ids)
            ]
        data.setdefault("policy_conflicts", [])
        return data

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
        if (
            any(not statement.legacy for statement in self.supported_statements())
            and not self.evidence_appendix
        ):
            raise ValueError("A schema-v2 report requires a nonempty evidence appendix")
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
    LEGACY_UNKNOWN = "legacy_unknown"


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
    schema_version: Literal[2] = 2
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
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)
    execution_metadata: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])

    @model_validator(mode="before")
    @classmethod
    def upgrade_schema_v1(cls, value: object) -> object:
        data = _mapping(value)
        if data is None:
            return value
        legacy = data.get("schema_version") != 2
        data["schema_version"] = 2
        if not legacy:
            return data
        validation_errors = [
            str(item) for item in (_objects(data.pop("validation_errors", [])) or [])
        ]
        repair_attempted = bool(data.pop("repair_attempted", False))
        data.setdefault("initial_validation_errors", validation_errors)
        data.setdefault("final_validation_errors", validation_errors)
        data.setdefault(
            "repair_actions",
            ["Schema-v1 run recorded a repair attempt"] if repair_attempted else [],
        )
        data.setdefault("clusters", [])
        data.setdefault("concern_analyses", [])
        data.setdefault("stage_timings", {})
        plans = _objects(data.get("query_plans"))
        if plans is not None:
            upgraded_plans: list[object] = []
            for item in plans:
                if isinstance(item, ClusterQueryPlan):
                    upgraded_plans.append(item)
                    continue
                item_data = _mapping(item)
                upgraded_plans.append(
                    item_data
                    if item_data is not None and "plan" in item_data
                    else {"cluster_id": "cluster_legacy", "plan": item}
                )
            data["query_plans"] = upgraded_plans
        if "scenarios" in data:
            data["scenarios"] = _upgrade_scenario_mappings(
                data.get("scenarios"), data.get("alternatives")
            )
        if legacy and data.get("status") == ConsultationStatus.FAILED:
            data.setdefault("failure_stage", ConsultationFailureStage.LEGACY_UNKNOWN)
            data.setdefault(
                "sanitized_errors",
                validation_errors or ["Legacy consultation failed without a recorded error"],
            )
        elif legacy:
            data.setdefault("failure_stage", None)
            data.setdefault("sanitized_errors", [])
        return data

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
            if self.failure_stage is not None or self.sanitized_errors:
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
                    "A successful run requires exactly one packet and analysis "
                    "per concern cluster"
                )
        return self

    @property
    def validation_errors(self) -> list[str]:
        """Schema-v1 read compatibility."""
        return self.final_validation_errors

    @property
    def repair_attempted(self) -> bool:
        """Schema-v1 read compatibility."""
        return bool(self.repair_actions)


class CaseExtraction(DomainModel):
    update: ArchitectureCase
