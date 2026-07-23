"""Policy corpus contracts."""

from __future__ import annotations

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


class PolicyDocument(DomainModel):
    schema_version: Literal[2] = 2
    id: str
    title: str
    scope: PolicyScope
    strength: PolicyStrength
    tags: list[str]
    source: PolicySource
    body: str
    source_path: str
    content_hash: str


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
            strength=retrieved.policy.strength,
            matched_sections=[chunk.section for chunk in retrieved.chunks],
        )


class PolicyConflict(DomainModel):
    policy_ids: list[str] = Field(min_length=2)
    explanation: str = Field(min_length=1)
    reconciliation: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_distinct_policy_ids(self) -> PolicyConflict:
        if len(set(self.policy_ids)) < 2:
            raise ValueError("A policy conflict must cite at least two distinct policies")
        return self
