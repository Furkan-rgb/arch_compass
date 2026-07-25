"""Model-facing synthesis contract.

A `RecommendationReport` is composed by ArchCompass, not returned by a provider. The
report contains a great deal the model does not own: the design forces discovered
earlier, the alternatives and scenarios already evaluated, the canonical policy
evidence from the focused packets, the exact claims produced by concern analysis, and
the identity of every claim and finding.

Asking a provider to reproduce all of that verbatim and then diffing the response
against the truth is what made synthesis brittle. This module describes only what the
synthesis stage uniquely contributes:

* which of the supplied claims support each part of the recommendation,
* any additional reasoning the model wants to state as its own inference,
* the findings, and
* the recommendation prose.

Everything known in advance is referenced by a short, request-local handle whose valid
values are enumerated in the JSON schema, so an invented reference cannot be expressed.
`application/synthesis.py` turns an accepted proposal into the persisted report.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from archcompass.domain.base import DomainModel
from archcompass.domain.case import Confidence
from archcompass.domain.consultation import (
    ClaimClassification,
    FindingImportance,
    RecommendationDisposition,
)

#: Classifications a provider may author on its own authority. Everything else is
#: evidence that must already exist in the supplied claim pool.
AUTHORABLE_CLASSIFICATIONS = frozenset(
    {
        ClaimClassification.ADVISOR_INFERENCE,
        ClaimClassification.DERIVED_CONSTRAINT,
    }
)


class AvailableClaim(DomainModel):
    """One claim offered to synthesis under a request-local handle."""

    ref: str = Field(min_length=1)
    text: str = Field(min_length=1)
    classification: ClaimClassification
    cluster_ref: str | None = None


class ProposedAdvisorClaim(DomainModel):
    """Reasoning the model states as its own, beyond the supplied evidence."""

    ref: str = Field(min_length=1)
    text: str = Field(min_length=1)
    classification: ClaimClassification

    @model_validator(mode="after")
    def require_authorable_classification(self) -> ProposedAdvisorClaim:
        if self.classification not in AUTHORABLE_CLASSIFICATIONS:
            raise ValueError(
                "A provider may author only advisor inference or derived constraints; "
                f"{self.classification} must come from the supplied claim pool"
            )
        return self


class ProposedStatement(DomainModel):
    """Recommendation prose with its support named by claim handle."""

    text: str = Field(min_length=1)
    classification: ClaimClassification
    claim_refs: list[str] = Field(min_length=1)


class ProposedFinding(DomainModel):
    """A canonical architectural finding, less the evidence ArchCompass projects.

    Atlas nodes, source locations, metrics, signals, and policy IDs are derived from
    the cited claims and the finding's own focused packet, so the model neither states
    nor restates them.
    """

    cluster_ref: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    importance: FindingImportance
    importance_rationale: str = Field(min_length=1)
    confidence: Confidence
    consequence: str = Field(min_length=1)
    claim_refs: list[str] = Field(min_length=1)
    recommended_response: str = Field(min_length=1)
    uncertainty: list[str] = Field(default_factory=list[str])


class ProposedADR(DomainModel):
    title: str = Field(min_length=1)
    status: str = "proposed"
    context: str = Field(min_length=1)
    decision: ProposedStatement
    consequences: list[ProposedStatement] = Field(min_length=1)


class ProposedRecommendation(DomainModel):
    """The complete synthesis response.

    Absent by design: design forces, alternatives, scenarios, policy evidence, policy
    conflicts, claim identity, finding identity, section placement, and the report's
    schema version. ArchCompass owns each of those and injects them during composition.
    """

    #: Typed, not free text: the set is closed and known before the request, so the
    #: JSON schema constrains it and an invalid disposition cannot be expressed.
    disposition: RecommendationDisposition
    problem_and_desired_outcome: str = Field(min_length=1)
    confidence: Confidence
    advisor_claims: list[ProposedAdvisorClaim] = Field(
        default_factory=list[ProposedAdvisorClaim],
        max_length=12,
    )
    findings: list[ProposedFinding] = Field(min_length=1, max_length=12)
    decision_summary: ProposedStatement
    recommended_architecture: ProposedStatement
    responsibility_allocation: list[ProposedStatement] = Field(min_length=1)
    conceptual_interfaces: list[ProposedStatement] = Field(default_factory=list[ProposedStatement])
    change_amplification_analysis: ProposedStatement
    trade_offs: list[ProposedStatement] = Field(min_length=1)
    implementation_sequence: list[ProposedStatement] = Field(min_length=1)
    reversal_conditions: list[ProposedStatement] = Field(min_length=1)
    revisit_triggers: list[ProposedStatement] = Field(min_length=1)
    adr: ProposedADR

    @model_validator(mode="after")
    def require_unique_advisor_refs(self) -> ProposedRecommendation:
        refs = [claim.ref for claim in self.advisor_claims]
        if len(refs) != len(set(refs)):
            raise ValueError("Advisor claim handles must be unique")
        return self

    def statements(self) -> list[ProposedStatement]:
        """Every statement in the proposal, in composition order."""

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
