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
    """The human context a review is judged against: answers, and nothing else.

    Three fields have been removed from this record over its life — a free-text goal, then
    hand-authored constraints and decisions — and all three failed the same way. Each was a
    box asking a person to state their intent before they had seen a finding, so each was
    almost always empty; where one was filled in it duplicated what the policy corpus
    already says, in prose nothing could retrieve against. Constraints and decisions failed
    twice over: no surface in the product ever offered to write one, and no review ever
    produced one, so they were a channel that could only be fed by hand-authoring YAML.

    What is left is the channel that fills itself. When a judgement turns on something the
    repository cannot answer, the model states a hinge, the review stops and asks, and the
    reply is recorded here as an `Answer` — carrying the question it replies to, who
    answered, and when. That is the charter's "ask rather than assume", and it is the only
    way intent enters a case. Everything else a review is judged against is the policy
    corpus, which is authored where policies live and retrieved per candidate.

    `policy_context` is not intent. It scopes which policies are retrievable — a user, an
    organisation, a repository — and is the one thing here a person still sets directly.
    """

    id: str
    revision: int
    answers: tuple[Answer, ...] = ()
    policy_context: PolicyContext = PolicyContext()
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        freeze_sequences(self, "answers")
        require_text(self.id, "case id")
        if self.revision < 1:
            raise ValueError("case revision must be positive")

    @classmethod
    def create(cls) -> ArchitectureCase:
        now = utc_now()
        return cls(new_id("case"), 1, created_at=now, updated_at=now)

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

    def revise(self, *, policy_context: PolicyContext) -> ArchitectureCase:
        """Re-scope which policies are retrievable, as the next revision.

        All this can still change is the policy scope. Intent arrives through `with_answers`
        and nowhere else, so there is no longer a general "revise the case" operation for a
        person to reach for — which is the point, not an omission.
        """

        return replace(
            self,
            revision=self.revision + 1,
            policy_context=policy_context,
            updated_at=utc_now(),
        )
