"""Policy corpus contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

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
