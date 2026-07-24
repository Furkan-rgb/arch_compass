"""Policy corpus contracts."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from archcompass.domain.base import DomainModel, new_id, utc_now


class PolicyScope(StrEnum):
    GENERAL = "general"
    USER = "user"
    ORGANISATION = "organisation"
    REPOSITORY = "repository"
    ACCEPTED_ADR = "accepted_adr"


class PolicyStrength(StrEnum):
    GUIDANCE = "guidance"
    PREFERRED = "preferred"
    REQUIRED = "required"


class PolicySource(DomainModel):
    author: str
    inspiration: list[str] = Field(default_factory=list[str])


class PolicyApplicabilityContext(DomainModel):
    """Subjects in whose context scoped policies may be retrieved."""

    user: str | None = None
    organisation: str | None = None
    repository: str | None = None

    @field_validator("user", "organisation", "repository")
    @classmethod
    def normalize_subject(cls, subject: str | None) -> str | None:
        if subject is None:
            return None
        normalized = subject.strip()
        if not normalized:
            raise ValueError("Policy applicability subjects must be nonempty")
        return normalized


class PolicyDocument(DomainModel):
    schema_version: Literal[2] = 2
    id: str
    title: str
    scope: PolicyScope
    applies_to: str | None = None
    strength: PolicyStrength
    tags: list[str]
    source: PolicySource
    body: str
    source_path: str
    content_hash: str

    @field_validator("applies_to")
    @classmethod
    def normalize_applies_to(cls, subject: str | None) -> str | None:
        if subject is None:
            return None
        normalized = subject.strip()
        if not normalized:
            raise ValueError("Policy applicability subjects must be nonempty")
        return normalized

    def applies_in(self, context: PolicyApplicabilityContext | None = None) -> bool:
        """Return whether this policy is applicable without widening missing identity."""

        if self.scope is PolicyScope.GENERAL:
            return True
        if self.applies_to is None or context is None:
            return False
        if self.scope is PolicyScope.USER:
            return self.applies_to == context.user
        if self.scope is PolicyScope.ORGANISATION:
            return self.applies_to == context.organisation
        return self.applies_to == context.repository


class PolicyChunk(DomainModel):
    chunk_id: str
    policy_id: str
    section: str
    ordinal: int = Field(ge=0)
    text: str
    content_hash: str


class PolicyIndexVersion(DomainModel):
    schema_version: Literal[2] = 2
    version_id: str = Field(default_factory=lambda: new_id("pidx"))
    embedding_provider: str
    embedding_model: str
    dimensions: int = Field(gt=0)
    corpus_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class RetrievedPolicy(DomainModel):
    policy: PolicyDocument
    chunks: list[PolicyChunk]
    distance: float


class PolicySourceRegistration(DomainModel):
    canonical_path: str = Field(min_length=1)
    registered_at: datetime = Field(default_factory=utc_now)


class PolicyEvidenceSummary(DomainModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    scope: PolicyScope
    applies_to: str | None = None
    strength: PolicyStrength
    matched_sections: list[str] = Field(min_length=1)

    @field_validator("matched_sections")
    @classmethod
    def normalize_matched_sections(cls, sections: list[str]) -> list[str]:
        unique: dict[str, str] = {}
        for section in sections:
            normalized = " ".join(section.split())
            if not normalized:
                raise ValueError("Matched policy sections must be nonempty")
            unique.setdefault(normalized.casefold(), normalized)
        if len(unique) > 3:
            raise ValueError("At most three matched sections may be retained per policy")
        return list(unique.values())

    @classmethod
    def from_retrieved(cls, retrieved: RetrievedPolicy) -> PolicyEvidenceSummary:
        return cls(
            id=retrieved.policy.id,
            title=retrieved.policy.title,
            scope=retrieved.policy.scope,
            applies_to=retrieved.policy.applies_to,
            strength=retrieved.policy.strength,
            matched_sections=[chunk.section for chunk in retrieved.chunks],
        )


def canonical_policy_evidence(
    retrieved_policies: Iterable[RetrievedPolicy],
) -> list[PolicyEvidenceSummary]:
    """Merge repeated cross-cluster retrievals into stable policy evidence."""

    documents: dict[str, PolicyDocument] = {}
    sections: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for retrieved in retrieved_policies:
        policy = retrieved.policy
        previous = documents.get(policy.id)
        if previous is None:
            documents[policy.id] = policy
            sections[policy.id] = {}
            order.append(policy.id)
        elif (
            previous.title,
            previous.scope,
            previous.applies_to,
            previous.strength,
        ) != (
            policy.title,
            policy.scope,
            policy.applies_to,
            policy.strength,
        ):
            raise ValueError(
                f"Retrieved policy {policy.id} has inconsistent canonical metadata"
            )
        for chunk in retrieved.chunks:
            normalized = " ".join(chunk.section.split())
            if normalized:
                sections[policy.id].setdefault(normalized.casefold(), normalized)

    summaries: list[PolicyEvidenceSummary] = []
    for policy_id in order:
        policy = documents[policy_id]
        matched_sections = list(sections[policy_id].values())[:3]
        if not matched_sections:
            raise ValueError(
                f"Retrieved policy {policy_id} has no matched section evidence"
            )
        summaries.append(
            PolicyEvidenceSummary(
                id=policy.id,
                title=policy.title,
                scope=policy.scope,
                applies_to=policy.applies_to,
                strength=policy.strength,
                matched_sections=matched_sections,
            )
        )
    return summaries


class PolicyConflict(DomainModel):
    policy_ids: list[str] = Field(min_length=2)
    explanation: str = Field(min_length=1)
    reconciliation: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_distinct_policy_ids(self) -> PolicyConflict:
        if len(set(self.policy_ids)) < 2:
            raise ValueError("A policy conflict must cite at least two distinct policies")
        return self
