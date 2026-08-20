from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

from archcompass.domain._support import freeze_sequences, require_text, stable_id
from archcompass.domain.values import Evidence, Measurement, Relationship

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
    """A structural pattern that could make a policy relevant — never a violation.

    N-ary by construction: duplicated knowledge is a fact about a set of modules, and a
    type holding one participant would discard the finding while appearing to record it.

    `relationships` is carried rather than derived later because a pattern judged from
    participants in isolation is a lint rather than an architectural finding. Which
    abstraction is implemented by which adapter, and whether the parser or the type checker
    established it, is the placement evidence the verdict actually rests on — and it costs
    a few dozen bytes beside excerpts that cost thousands.
    """

    id: CandidateId
    pattern: str
    summary: str
    participants: tuple[Participant, ...]
    evidence: tuple[Evidence, ...] = ()
    measurements: tuple[Measurement, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    detection_rationale: str = ""
    limitations: str = ""

    def __post_init__(self) -> None:
        freeze_sequences(self, "participants", "evidence", "measurements", "relationships")
        require_text(str(self.id), "candidate id")
        require_text(self.pattern, "candidate pattern")
        require_text(self.summary, "candidate summary")
        if not self.participants:
            raise ValueError("a candidate must have participants")

    def measured(self, name: str) -> Measurement | None:
        """One measurement by name, for code that buckets or compares on a single value."""

        return next((item for item in self.measurements if item.name == name), None)

    @classmethod
    def identified(
        cls,
        *,
        pattern: str,
        summary: str,
        participants: tuple[Participant, ...],
        **details: object,
    ) -> Candidate:
        """Mint the run-independent identity of a detected shape.

        Derived from what the candidate *is* — which detector recognised it and which named
        things participate in it — so the same structural situation produces the same id on
        every run that observes it. Deliberately excludes measurements, evidence and
        relationships: those move under ordinary editing, and an identity that moved with
        them could not anchor a standing decision or a line across revisions.
        """

        names = tuple(sorted(item.qualified_name for item in participants))
        return cls(
            id=CandidateId(stable_id("candidate", pattern, *names)),
            pattern=pattern,
            summary=summary,
            participants=participants,
            **details,  # type: ignore[arg-type]
        )
