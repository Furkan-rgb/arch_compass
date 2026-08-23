"""Validated policy authoring and catalog boundary records."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from archcompass.domain.policy import PolicyScope, PolicyStrength
from archcompass.records import BoundaryDTO, utc_now


class PolicyOrigin(StrEnum):
    """Whose file a policy is.

    A fact about where the Markdown lives, not a permission: `WORKSPACE` means this
    workspace's own authored directory wrote it and can rewrite it, and everything read
    from the bundled corpus or from a registered source is somebody else's file. Stamped
    when the catalog is composed, because only the service knows which directory is which
    — a parser handed one path cannot tell.
    """

    EXTERNAL = "external"
    WORKSPACE = "workspace"


class PolicySource(BoundaryDTO):
    author: str
    inspiration: list[str] = Field(default_factory=list[str])


class PolicyDocument(BoundaryDTO):
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
    origin: PolicyOrigin = PolicyOrigin.EXTERNAL

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

class PolicySourceRegistration(BoundaryDTO):
    canonical_path: str = Field(min_length=1)
    registered_at: datetime = Field(default_factory=utc_now)


def policy_slug(title: str) -> str:
    """The identifier a title is filed under, which is also its file name.

    Derived rather than asked for. An id is cited by every review that weighed the policy
    and is the name a `## Related policies` section points at, so it is a thing the corpus
    agrees on rather than a second field an author has to keep consistent with the first.
    """

    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:80].strip("-")


class PolicyDraft(BoundaryDTO):
    """A policy as its author states it, before it is a file.

    Scope is absent because it is not a choice: a policy written here is `general`, and the
    scoped kinds are declared by where their file lives (`applies_to`, or a repository's own
    `.archcompass/policies`) rather than by a form. Author and id are absent for the same
    reason — both are the workspace's to state.
    """

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1200)
    body: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list[str], max_length=12)
    strength: PolicyStrength

    @field_validator("title", "description", "body")
    @classmethod
    def normalize_prose(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("title")
    @classmethod
    def title_yields_an_identifier(cls, title: str) -> str:
        if not policy_slug(title):
            raise ValueError(
                "Title must contain letters or digits: the policy id is derived from it"
            )
        return title

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        normalized = [tag.strip() for tag in tags]
        if any(not tag or len(tag) > 40 for tag in normalized):
            raise ValueError("Each tag must be a nonempty string of at most 40 characters")
        return list(dict.fromkeys(normalized))

    @field_validator("title", "description", "tags")
    @classmethod
    def stays_inside_front_matter(cls, value: str | list[str]) -> str | list[str]:
        # These three are written as YAML above the body's `---`, and a `---` inside one of
        # them ends the front matter early — the file then parses as a different document, or
        # as none. The body sits after that fence and may contain anything.
        entries = [value] if isinstance(value, str) else value
        if any("---" in entry for entry in entries):
            raise ValueError("Must not contain '---', which would end the front matter")
        return value
