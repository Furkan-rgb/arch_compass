"""Consultation workflow and report contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from archcompass.domain.atlas import AtlasQueryPlan, AtlasQueryResult, SourceLocation
from archcompass.domain.base import DomainModel, new_id, utc_now
from archcompass.domain.case import (
    ArchitectureCase,
    CaseAlternative,
    Confidence,
)
from archcompass.domain.policy import RetrievedPolicy


class ClaimClassification(StrEnum):
    CONFIRMED_REQUIREMENT = "confirmed_user_requirement"
    DERIVED_CONSTRAINT = "derived_constraint"
    REPOSITORY_OBSERVATION = "repository_observation"
    POLICY_GUIDANCE = "policy_guidance"
    SCENARIO_ASSUMPTION = "scenario_assumption"
    ADVISOR_INFERENCE = "advisor_inference"


class AtlasEvidenceReference(DomainModel):
    node_id: str
    location: SourceLocation | None = None


class Claim(DomainModel):
    claim_id: str = Field(default_factory=lambda: new_id("claim"))
    text: str
    classification: ClaimClassification
    atlas_references: list[AtlasEvidenceReference] = Field(
        default_factory=list[AtlasEvidenceReference]
    )
    policy_ids: list[str] = Field(default_factory=list[str])


class DesignForce(DomainModel):
    force_id: str = Field(default_factory=lambda: new_id("force"))
    title: str
    description: str
    importance: str


class GlobalContext(DomainModel):
    case_id: str
    revision: int
    title: str
    problem: str
    desired_outcome: str
    goals: list[str]
    constraints: list[str]
    future_changes: list[str]
    non_goals: list[str]
    confirmed_facts: list[str]
    assumptions: list[str]
    atlas_summary: str | None = None


class FocusedAnalysisPacket(DomainModel):
    concern: str
    reason: str
    design_force_ids: list[str]
    query_results: list[AtlasQueryResult]
    policies: list[RetrievedPolicy]
    assumptions: list[str]
    uncertainty: list[str]


class ConcernAnalysis(DomainModel):
    concern: str
    findings: list[Claim]
    implications: list[str]


class ScenarioEvaluation(DomainModel):
    scenario: str
    assumptions: list[str]
    alternative_results: list[str]
    conclusion: str


class ADRRecord(DomainModel):
    title: str
    status: str = "proposed"
    context: str
    decision: str
    consequences: list[str]


class RecommendationReport(DomainModel):
    report_id: str = Field(default_factory=lambda: new_id("report"))
    decision_summary: str
    problem_and_desired_outcome: str
    confirmed_context: list[Claim]
    assumptions_and_unresolved_questions: list[Claim]
    important_design_forces: list[DesignForce]
    repository_observations: list[Claim]
    relevant_policies: list[Claim]
    recommended_architecture: str
    responsibility_allocation: list[str]
    conceptual_interfaces: list[str]
    alternatives_considered: list[CaseAlternative]
    scenario_analysis: list[ScenarioEvaluation]
    change_amplification_analysis: str
    trade_offs: list[str]
    implementation_sequence: list[str]
    confidence: Confidence
    reversal_conditions: list[str]
    revisit_triggers: list[str]
    adr: ADRRecord
    evidence_appendix: list[Claim]


class ConsultationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ConsultationRun(DomainModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    status: ConsultationStatus
    case_id: str
    input_case_revision: int
    result_case_revision: int | None = None
    atlas_version_id: str | None = None
    policy_index_version_id: str | None = None
    reasoning_model: str
    embedding_model: str
    config_hash: str
    prompt_identities: list[str]
    design_forces: list[DesignForce]
    query_plans: list[AtlasQueryPlan]
    focused_packets: list[FocusedAnalysisPacket]
    alternatives: list[CaseAlternative]
    scenarios: list[ScenarioEvaluation]
    report: RecommendationReport | None = None
    markdown_report: str | None = None
    validation_errors: list[str] = Field(default_factory=list[str])
    repair_attempted: bool = False
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)
    execution_metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict[str, str | int | float | bool | None]
    )


class CaseExtraction(DomainModel):
    update: ArchitectureCase
