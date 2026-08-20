from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from archcompass.domain._support import (
    freeze_sequences,
    new_id,
    require_text,
    stable_id,
    utc_now,
)


class CaseFacet(StrEnum):
    GOAL = "goal"
    CONSTRAINT = "constraint"
    DECISION = "decision"
    ASSUMPTION = "assumption"
    EXPECTED_CHANGE = "expected_change"
    NON_GOAL = "non_goal"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class CaseConstraint:
    text: str
    facet: CaseFacet = CaseFacet.CONSTRAINT
    source: str | None = None

    def __post_init__(self) -> None:
        require_text(self.text, "constraint")


@dataclass(frozen=True, slots=True)
class CaseDecision:
    text: str
    source: str | None = None

    def __post_init__(self) -> None:
        require_text(self.text, "decision")


@dataclass(frozen=True, slots=True)
class PolicyContext:
    user: str | None = None
    organisation: str | None = None
    repository: str | None = None


@dataclass(frozen=True, slots=True)
class Question:
    """A question the repository cannot answer, put to a human.

    ``options`` are answers the reasoning model thinks likely, offered so that the common
    case is a click rather than an essay. They are a shortcut, never a closed set: an
    answer's value is free text whichever way it was produced, and the interface always
    offers writing one instead. An empty tuple simply means nothing was proposed.

    They stay out of ``equivalence_key`` deliberately — two rounds asking the same thing of
    the same candidates are the same question even if the model proposes different answers
    the second time, and the point of the key is to stop asking it twice.
    """

    id: str
    text: str
    facet: CaseFacet
    candidate_ids: tuple[str, ...]
    round: int
    equivalence_key: str
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        freeze_sequences(self, "candidate_ids", "options")
        require_text(self.id, "question id")
        require_text(self.text, "question")
        require_text(self.equivalence_key, "question equivalence key")
        if self.round < 1:
            raise ValueError("question round must be positive")
        if not self.candidate_ids:
            raise ValueError("a question must name at least one candidate")
        for option in self.options:
            require_text(option, "question option")
        if len(set(self.options)) != len(self.options):
            raise ValueError("a question cannot offer the same answer twice")

    @classmethod
    def create(
        cls,
        *,
        text: str,
        facet: CaseFacet,
        candidate_ids: tuple[str, ...],
        round: int,
        options: Sequence[str] = (),
    ) -> Question:
        candidates = tuple(sorted(set(candidate_ids)))
        key = stable_id("qeq", facet.value, *candidates)
        # Order is the model's — it proposes the likeliest answer first — so duplicates are
        # dropped where they appear rather than by sorting the offer into another shape.
        seen: set[str] = set()
        offered: list[str] = []
        for option in options:
            text_value = option.strip()
            if not text_value or text_value.casefold() in seen:
                continue
            seen.add(text_value.casefold())
            offered.append(text_value)
        return cls(
            new_id("question"), text, facet, candidates, round, key, tuple(offered)
        )


@dataclass(frozen=True, slots=True)
class Answer:
    question: Question
    status: AnswerStatus
    value: str | None
    actor: str
    answered_at: datetime

    def __post_init__(self) -> None:
        require_text(self.actor, "answer actor")
        if self.status is AnswerStatus.ANSWERED and not (self.value or "").strip():
            raise ValueError("an answered question must have a value")
        if self.status is AnswerStatus.SKIPPED and self.value is not None:
            raise ValueError("a skipped question cannot have a value")


@dataclass(frozen=True, slots=True)
class ArchitectureCase:
    id: str
    revision: int
    goal: str
    constraints: tuple[CaseConstraint, ...] = ()
    decisions: tuple[CaseDecision, ...] = ()
    answers: tuple[Answer, ...] = ()
    policy_context: PolicyContext = PolicyContext()
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        freeze_sequences(self, "constraints", "decisions", "answers")
        require_text(self.id, "case id")
        if self.revision < 1:
            raise ValueError("case revision must be positive")

    @classmethod
    def create(cls, goal: str = "") -> ArchitectureCase:
        now = utc_now()
        return cls(new_id("case"), 1, goal.strip(), created_at=now, updated_at=now)

    def with_answer(self, answer: Answer) -> ArchitectureCase:
        return self.with_answers((answer,))

    def with_answers(self, answers: tuple[Answer, ...]) -> ArchitectureCase:
        """Record one clarification submission as exactly one case revision."""

        if not answers:
            raise ValueError("a case revision must record at least one answer")
        existing = {item.question.equivalence_key for item in self.answers}
        incoming = [item.question.equivalence_key for item in answers]
        if existing.intersection(incoming) or len(incoming) != len(set(incoming)):
            raise ValueError("this case already records an equivalent question")
        return replace(
            self,
            revision=self.revision + 1,
            answers=(*self.answers, *answers),
            updated_at=utc_now(),
        )

    def revise(
        self,
        *,
        goal: str | None = None,
        constraints: tuple[CaseConstraint, ...] | None = None,
        decisions: tuple[CaseDecision, ...] | None = None,
        policy_context: PolicyContext | None = None,
    ) -> ArchitectureCase:
        """Create the next human-authored revision without mutating this snapshot."""

        return replace(
            self,
            revision=self.revision + 1,
            goal=self.goal if goal is None else goal.strip(),
            constraints=self.constraints if constraints is None else constraints,
            decisions=self.decisions if decisions is None else decisions,
            policy_context=(
                self.policy_context if policy_context is None else policy_context
            ),
            updated_at=utc_now(),
        )
