"""Architecture case and revision contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from archcompass.domain.base import DomainModel, new_id, utc_now
from archcompass.domain.policy import PolicyApplicabilityContext


class StatementKind(StrEnum):
    FACT = "fact"
    DERIVED_CONSTRAINT = "derived_constraint"
    ASSUMPTION = "assumption"
    QUESTION = "question"
    FORCE = "force"


class CaseStatement(DomainModel):
    id: str = Field(default_factory=lambda: new_id("stmt"))
    text: str = Field(min_length=1)
    kind: StatementKind
    source: str | None = None


class RepositoryReference(DomainModel):
    root_path: str = Field(min_length=1)
    atlas_version_id: str | None = None


class CaseAlternative(DomainModel):
    id: str = Field(default_factory=lambda: new_id("alt"))
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class RecommendationState(DomainModel):
    summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    run_id: str | None = None
    disposition: str | None = None


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Confidence(DomainModel):
    level: ConfidenceLevel
    rationale: str = Field(min_length=1)


class ArchitectureCase(DomainModel):
    schema_version: Literal[2] = 2
    case_id: str = Field(default_factory=lambda: new_id("case"))
    title: str = Field(min_length=1)
    problem_statement: str = Field(min_length=1)
    desired_outcome: str = Field(min_length=1)
    actors_and_workflows: list[str] = Field(default_factory=list[str])
    functional_requirements: list[str] = Field(default_factory=list[str])
    quality_attributes: list[str] = Field(default_factory=list[str])
    technical_constraints: list[str] = Field(default_factory=list[str])
    organisational_constraints: list[str] = Field(default_factory=list[str])
    expected_future_changes: list[str] = Field(default_factory=list[str])
    non_goals: list[str] = Field(default_factory=list[str])
    confirmed_facts: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    derived_constraints: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    assumptions: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    unresolved_questions: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    design_forces: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    advisor_design_forces: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    repository: RepositoryReference | None = None
    policy_applicability: PolicyApplicabilityContext = Field(
        default_factory=PolicyApplicabilityContext
    )
    referenced_policy_ids: list[str] = Field(default_factory=list[str])
    candidate_alternatives: list[CaseAlternative] = Field(default_factory=list[CaseAlternative])
    current_recommendation: RecommendationState | None = None
    confidence: Confidence | None = None
    reversal_conditions: list[str] = Field(default_factory=list[str])
    revisit_triggers: list[str] = Field(default_factory=list[str])
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    revision: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_statement_kinds(self) -> ArchitectureCase:
        expected = (
            ("confirmed_facts", self.confirmed_facts, StatementKind.FACT),
            (
                "derived_constraints",
                self.derived_constraints,
                StatementKind.DERIVED_CONSTRAINT,
            ),
            ("assumptions", self.assumptions, StatementKind.ASSUMPTION),
            (
                "unresolved_questions",
                self.unresolved_questions,
                StatementKind.QUESTION,
            ),
            ("design_forces", self.design_forces, StatementKind.FORCE),
            (
                "advisor_design_forces",
                self.advisor_design_forces,
                StatementKind.FORCE,
            ),
        )
        for field, statements, kind in expected:
            wrong = [statement.id for statement in statements if statement.kind != kind]
            if wrong:
                raise ValueError(f"{field} contains statements with the wrong kind: {wrong}")
        user_force_ids = [statement.id for statement in self.design_forces]
        duplicate_user_force_ids = sorted(
            force_id for force_id in set(user_force_ids) if user_force_ids.count(force_id) > 1
        )
        if duplicate_user_force_ids:
            raise ValueError(
                f"design_forces contains duplicate user-authored IDs: {duplicate_user_force_ids}"
            )
        return self


class CaseUpdate(DomainModel):
    title: str | None = None
    problem_statement: str | None = None
    desired_outcome: str | None = None
    actors_and_workflows: list[str] | None = None
    functional_requirements: list[str] | None = None
    quality_attributes: list[str] | None = None
    technical_constraints: list[str] | None = None
    organisational_constraints: list[str] | None = None
    expected_future_changes: list[str] | None = None
    non_goals: list[str] | None = None
    confirmed_facts: list[CaseStatement] | None = None
    derived_constraints: list[CaseStatement] | None = None
    assumptions: list[CaseStatement] | None = None
    unresolved_questions: list[CaseStatement] | None = None
    design_forces: list[CaseStatement] | None = None
    advisor_design_forces: list[CaseStatement] | None = None
    repository: RepositoryReference | None = None
    policy_applicability: PolicyApplicabilityContext | None = None
    referenced_policy_ids: list[str] | None = None
    candidate_alternatives: list[CaseAlternative] | None = None
    current_recommendation: RecommendationState | None = None
    confidence: Confidence | None = None
    reversal_conditions: list[str] | None = None
    revisit_triggers: list[str] | None = None

    @model_validator(mode="after")
    def validate_statement_kinds(self) -> CaseUpdate:
        expected = (
            ("confirmed_facts", self.confirmed_facts, StatementKind.FACT),
            (
                "derived_constraints",
                self.derived_constraints,
                StatementKind.DERIVED_CONSTRAINT,
            ),
            ("assumptions", self.assumptions, StatementKind.ASSUMPTION),
            (
                "unresolved_questions",
                self.unresolved_questions,
                StatementKind.QUESTION,
            ),
            ("design_forces", self.design_forces, StatementKind.FORCE),
            (
                "advisor_design_forces",
                self.advisor_design_forces,
                StatementKind.FORCE,
            ),
        )
        for field, statements, kind in expected:
            if statements is None:
                continue
            wrong = [statement.id for statement in statements if statement.kind != kind]
            if wrong:
                raise ValueError(f"{field} contains statements with the wrong kind: {wrong}")
        return self


class CaseRevision(DomainModel):
    case_id: str
    revision: int = Field(ge=1)
    snapshot: ArchitectureCase
    event_type: Literal["created", "user_update", "consultation"]
    actor: str
    created_at: datetime = Field(default_factory=utc_now)
    origin_run_id: str | None = None

    @model_validator(mode="after")
    def validate_snapshot_identity(self) -> CaseRevision:
        if self.snapshot.case_id != self.case_id:
            raise ValueError("Case revision snapshot must have the same case ID")
        if self.snapshot.revision != self.revision:
            raise ValueError("Case revision snapshot must have the same revision number")
        if self.event_type == "consultation" and self.origin_run_id is None:
            raise ValueError("Consultation revisions require an originating run ID")
        return self
