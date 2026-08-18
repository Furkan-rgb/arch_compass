from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

from archcompass.domain._support import (
    freeze_pairs,
    freeze_sequences,
    require_text,
    stable_id,
)
from archcompass.domain.values import Evidence

CandidateId = NewType("CandidateId", str)


@dataclass(frozen=True, slots=True)
class Participant:
    qualified_name: str
    role: str

    def __post_init__(self) -> None:
        require_text(self.qualified_name, "participant name")
        require_text(self.role, "participant role")


@dataclass(frozen=True, slots=True)
class Candidate:
    id: CandidateId
    pattern: str
    summary: str
    participants: tuple[Participant, ...]
    evidence: tuple[Evidence, ...] = ()
    measurements: tuple[tuple[str, str], ...] = ()
    detection_rationale: str = ""
    limitations: str = ""

    def __post_init__(self) -> None:
        freeze_sequences(self, "participants", "evidence")
        freeze_pairs(self, "measurements")
        require_text(str(self.id), "candidate id")
        require_text(self.pattern, "candidate pattern")
        require_text(self.summary, "candidate summary")
        if not self.participants:
            raise ValueError("a candidate must have participants")

    @classmethod
    def identified(
        cls,
        *,
        pattern: str,
        summary: str,
        participants: tuple[Participant, ...],
        **details: object,
    ) -> Candidate:
        names = tuple(sorted(item.qualified_name for item in participants))
        return cls(
            id=CandidateId(stable_id("candidate", pattern, *names)),
            pattern=pattern,
            summary=summary,
            participants=participants,
            **details,  # type: ignore[arg-type]
        )
