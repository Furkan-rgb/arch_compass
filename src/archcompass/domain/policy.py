"""Policy corpus contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from archcompass.domain.base import DomainModel, utc_now


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
    description: str | None = None
    scope: PolicyScope
    applies_to: str | None = None
    strength: PolicyStrength
    tags: list[str]
    source: PolicySource
    body: str
    source_path: str
    content_hash: str

    @field_validator("description")
    @classmethod
    def normalize_description(cls, description: str | None) -> str | None:
        if description is None:
            return None
        normalized = description.strip()
        if not normalized:
            raise ValueError("Policy description must be nonempty when present")
        return normalized

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


class PolicySourceRegistration(DomainModel):
    canonical_path: str = Field(min_length=1)
    registered_at: datetime = Field(default_factory=utc_now)
