from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from archcompass.domain.core._support import freeze_sequences, require_text


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


@dataclass(frozen=True, slots=True)
class Policy:
    id: str
    title: str
    body: str
    scope: PolicyScope
    strength: PolicyStrength
    content_hash: str
    tags: tuple[str, ...] = ()
    applies_to: str | None = None
    source: str = ""

    def __post_init__(self) -> None:
        freeze_sequences(self, "tags")
        for name, value in (("policy id", self.id), ("title", self.title), ("body", self.body)):
            require_text(value, name)
        require_text(self.content_hash, "policy content hash")

    def applies_in(
        self,
        *,
        user: str | None,
        organisation: str | None,
        repository: str | None,
    ) -> bool:
        if self.scope is PolicyScope.GENERAL:
            return True
        subject = {
            PolicyScope.USER: user,
            PolicyScope.ORGANISATION: organisation,
            PolicyScope.REPOSITORY: repository,
            PolicyScope.ACCEPTED_ADR: repository,
        }[self.scope]
        return self.applies_to is not None and self.applies_to == subject
