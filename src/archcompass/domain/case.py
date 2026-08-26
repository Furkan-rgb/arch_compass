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
    #: The case revision this answer was recorded on, stamped by `with_answers` rather than
    #: supplied — a caller cannot know it, and one that guessed would be recording which
    #: review a person's words belong to on a guess.
    #:
    #: `question.round` alone cannot say it. A review keeps one revision however many rounds
    #: it asks, so round is exact *within* a review and collides across a case's life: review
    #: 2's round 1 and review 3's round 1 are both "round 1" on the same list of answers.
    #: Together the two are the address of a round — which revision asked, and which of its
    #: rounds — and that is what a reader needs to see a case's history as rounds rather than
    #: as one undifferentiated pile.
    #:
    #: Zero on an answer recorded before this field existed, which reads as "unstamped"
    #: rather than as revision zero: a case revision is one or more, so nothing can mistake
    #: it for a real one, and a reader can group what it cannot place under the case itself.
    case_revision: int = 0
    #: The model that drafted these exact words, where a person accepted a draft unchanged.
    #: "" wherever the words are the person's own — typed, picked from the offered options,
    #: or edited from a draft before submitting.
    #:
    #: `actor` cannot say this and must not be made to. It answers *who answered*, and the
    #: answer is still theirs: they were shown a draft, they could have changed a word of it,
    #: and they submitted it. What this adds is that nobody wrote it.
    #:
    #: It exists because of a loop that would otherwise close silently. A reader stuck on a
    #: question can chat to an agent that reads this review, and that agent may draft an
    #: answer; the answer enters the case; the case moves verdicts. Without this field a
    #: model's own reasoning comes back to it as the team's intent, and every surface in the
    #: product would say a person had supplied it. Stated, never weighed: `case_text` puts
    #: it in front of a judgement as a fact and gives no instruction about it.
    #:
    #: Set only on an exact match with the draft. A person who changed anything wrote the
    #: sentence, and a record calling their words a model's would be the same lie pointing
    #: the other way.
    drafted_by: str = ""

    def __post_init__(self) -> None:
        require_text(self.actor, "answer actor")
        if self.status is AnswerStatus.ANSWERED and not (self.value or "").strip():
            raise ValueError("an answered question must have a value")
        if self.status is AnswerStatus.SKIPPED and self.value is not None:
            raise ValueError("a skipped question cannot have a value")
        # A skip has no words in it, so nothing can have drafted them.
        if self.status is AnswerStatus.SKIPPED and self.drafted_by:
            raise ValueError("a skipped question cannot carry a drafted answer")


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
    #: One review's worth of answering. A review opens a revision the first time it records
    #: an answer and keeps adding to it however many times it asks, so the number identifies
    #: what a review was judged against rather than counting clarification rounds.
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

    def open_revision(self, revision: int | None = None) -> ArchitectureCase:
        """Start the next revision of this case, carrying what is already answered.

        A review opens one revision, the first time it has an answer to record, and every
        later round of the same review adds to that one. The number is therefore the
        review's rather than the round's, which is the whole point: a person answering a
        question is completing the revision that asked, not starting another.

        `revision` names the number to take, for the store that knows which numbers are
        free. Left out, it takes the next one — which is right whenever this case is the
        newest revision of itself, and wrong for a revision somebody reopened behind the
        newest one, so the caller that can tell passes the number in.
        """

        number = self.revision + 1 if revision is None else revision
        if number <= self.revision:
            raise ValueError("a case revision must be later than the one it opens from")
        return replace(self, revision=number, updated_at=utc_now())

    def with_answer(self, answer: Answer) -> ArchitectureCase:
        return self.with_answers((answer,))

    def with_answers(self, answers: tuple[Answer, ...]) -> ArchitectureCase:
        """Record a clarification submission on this revision.

        The revision does not move. It moved here once, per submission, which made a review
        that asked twice occupy three case revisions and made the number beside a review
        change while somebody was reading it. Opening a revision is `open_revision`, and a
        review does it once.
        """

        if not answers:
            raise ValueError("a case revision must record at least one answer")
        existing = {item.question.equivalence_key for item in self.answers}
        incoming = [item.question.equivalence_key for item in answers]
        if existing.intersection(incoming) or len(incoming) != len(set(incoming)):
            raise ValueError("this case already records an equivalent question")
        # Stamped here and only here. The revision an answer belongs to is a fact this
        # object holds and the caller does not — `_resume_command` builds an `Answer` from a
        # question and a submission, neither of which knows which revision is open — so
        # recording is where the two meet.
        return replace(
            self,
            answers=(
                *self.answers,
                *(replace(item, case_revision=self.revision) for item in answers),
            ),
            updated_at=utc_now(),
        )

    def validate_continuation_of(self, previous: ArchitectureCase) -> None:
        """Refuse to be treated as a later round of `previous` unless it actually is.

        Rejudging means judging the same candidates against a case that now says more, so
        three things have to hold and each fails differently: it is the same case, the
        answers already recorded are still recorded unchanged, and a round has actually
        happened. A single boolean would collapse "you passed a different case" and "you
        rejudged without anything new to judge on" into one unhelpful `False`.

        Answers rather than the revision number, because one review keeps one revision
        however many rounds it asks. What says a round happened is that the case records
        answers the round before it did not — and they are appended in order, which makes
        the earlier ones a prefix of the later ones and the check exact rather than a count.
        """

        if self.id != previous.id:
            raise ValueError("rejudgement requires the same case")
        earlier = previous.answers
        if self.answers[: len(earlier)] != earlier:
            raise ValueError("rejudgement requires the answers already recorded")
        if len(self.answers) == len(earlier):
            raise ValueError("rejudgement requires answers the previous round did not record")

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
