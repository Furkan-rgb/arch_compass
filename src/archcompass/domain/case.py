"""Architecture case and revision contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from archcompass.domain.base import DomainModel, new_id, utc_now
from archcompass.domain.policy import PolicyApplicabilityContext


class StatementKind(StrEnum):
    FACT = "fact"
    DERIVED_CONSTRAINT = "derived_constraint"
    ASSUMPTION = "assumption"
    QUESTION = "question"
    FORCE = "force"


class CaseField(StrEnum):
    """The fields an elicited answer may enter, as a closed set (master plan 6C.2).

    A review that asks for the case says where each answer belongs, and this is the whole
    range of that answer. It is an enumeration rather than a string because the model picks
    the slot: a free-text field name is an identifier written by a model, which 12.0 forbids
    for exactly the reason it would fail here — a plausible misspelling routes an answer to
    a field that does not exist, and nothing downstream can tell that from a field the case
    simply has not got.

    Five of the case's fields, not all of them. These are the ones that decide whether a
    boundary is earning its place — what is coming, what is settled, what is ruled out, and
    what is being taken on trust. A title or a list of actors cannot flip a verdict, so
    offering them as a destination would only give a wrong answer somewhere to go.
    """

    EXPECTED_FUTURE_CHANGES = "expected_future_changes"
    CONFIRMED_FACTS = "confirmed_facts"
    TECHNICAL_CONSTRAINTS = "technical_constraints"
    NON_GOALS = "non_goals"
    ASSUMPTIONS = "assumptions"


class CaseStatement(DomainModel):
    id: str = Field(default_factory=lambda: new_id("stmt"))
    text: str = Field(min_length=1)
    kind: StatementKind
    source: str | None = None


class Clarification(DomainModel):
    """One question a review asked, and the answer the user gave it, kept as a pair.

    The answer used to be composed into a line and appended to one of the five fields
    `CaseField` names — the question's subject joined to the reply with a dash, so that the
    reply still meant something read alone. That composition was a workaround for the pair
    not being representable. It cost twice: the questions surface showed the reader an answer
    that restated the question they were looking at, and the re-judging stages, which see the
    case and nothing else, were given the join rather than the question — so the one piece of
    context that made the answer legible was the one thing they could not read.

    Kept as a pair, both halves say who wrote them. `question` is advisor-authored and
    labelled as such wherever it is shown; `answer` is the user's words and theirs alone,
    which is what invariant 25 and §6C.4 are about. A pair is also why the join no longer has
    to be guessed at: nothing has to infer the subject of "not for now, no", because the
    question it answers is beside it.

    `bears_on` is the force the answer carries, read from the review's own report rather than
    accepted from whoever submitted the answer (§12.0 — the application decides). A judging
    stage weighs a clarification bearing on `technical_constraints` exactly as it weighs an
    entry in that list, which is what keeps this a widening of the case rather than a second,
    weaker place for the same facts to live.
    """

    id: str = Field(default_factory=lambda: new_id("clar"))
    #: The review's question, verbatim. Advisor-authored, so it is never edited into the
    #: user's voice: a reader has to be able to tell which half they wrote.
    question: str = Field(min_length=1)
    #: The user's answer, as they typed it. Never composed, never rephrased, never pre-filled
    #: — the whole of what enters the case from a round of answering (invariant 25).
    answer: str = Field(min_length=1)
    #: Which of the five deciding fields this answer carries the force of. Not a destination
    #: any more, because the pair is not moved anywhere: it says how the answer should be
    #: weighed, which is what the destination was ever standing in for.
    bears_on: CaseField


class RepositoryReference(DomainModel):
    root_path: str = Field(min_length=1)
    atlas_version_id: str | None = None


class CaseAlternative(DomainModel):
    id: str = Field(default_factory=lambda: new_id("alt"))
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class ArchitectureCase(DomainModel):
    schema_version: Literal[2] = 2
    case_id: str = Field(default_factory=lambda: new_id("case"))
    title: str = Field(min_length=1)
    #: Both optional, and empty is the ordinary state of a case nobody has written yet.
    #: Requiring them made authoring a case the price of seeing a single verdict, which is
    #: the tax elicitation exists to remove (master plan §6C.1): a review can run against a
    #: repository alone and ask for what it lacked.
    #:
    #: Relaxing rather than removing, so nothing stored has to move. A case already holding
    #: these validates unchanged, which is why `schema_version` stays at 2 — widening what a
    #: field accepts breaks no document, unlike the narrowing ADR-0002 governs.
    #:
    #: `title` stays required. It is how a case is picked out of a listing, and a repository
    #: supplies one without anybody inventing intent.
    problem_statement: str = ""
    desired_outcome: str = ""
    actors_and_workflows: list[str] = Field(default_factory=list[str])
    functional_requirements: list[str] = Field(default_factory=list[str])
    quality_attributes: list[str] = Field(default_factory=list[str])
    technical_constraints: list[str] = Field(default_factory=list[str])
    organisational_constraints: list[str] = Field(default_factory=list[str])
    expected_future_changes: list[str] = Field(default_factory=list[str])
    non_goals: list[str] = Field(default_factory=list[str])
    confirmed_facts: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    derived_constraints: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    assumptions: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    unresolved_questions: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    design_forces: list[CaseStatement] = Field(default_factory=list[CaseStatement])
    #: What a review asked and what the user answered, in pairs (§6C.4). Its own field rather
    #: than five composed lines, because the question is the context that makes the answer
    #: legible and the second pass sees the case alone — a line that had to carry its own
    #: subject was the only way an answer could survive the trip, and it survived it badly.
    #:
    #: Additive, so `schema_version` stays at 2 for the reason the comment on
    #: `problem_statement` gives: a field with a default breaks no stored document, and every
    #: case already in a workspace validates unchanged with this list empty. ADR-0002 governs
    #: narrowing, which this is not.
    clarifications: list[Clarification] = Field(default_factory=list[Clarification])
    repository: RepositoryReference | None = None
    policy_applicability: PolicyApplicabilityContext = Field(
        default_factory=PolicyApplicabilityContext
    )
    referenced_policy_ids: list[str] = Field(default_factory=list[str])
    candidate_alternatives: list[CaseAlternative] = Field(default_factory=list[CaseAlternative])
    reversal_conditions: list[str] = Field(default_factory=list[str])
    revisit_triggers: list[str] = Field(default_factory=list[str])
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    revision: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_statement_kinds(self) -> ArchitectureCase:
        expected = (
            ("confirmed_facts", self.confirmed_facts, StatementKind.FACT),
            (
                "derived_constraints",
                self.derived_constraints,
                StatementKind.DERIVED_CONSTRAINT,
            ),
            ("assumptions", self.assumptions, StatementKind.ASSUMPTION),
            (
                "unresolved_questions",
                self.unresolved_questions,
                StatementKind.QUESTION,
            ),
            ("design_forces", self.design_forces, StatementKind.FORCE),
        )
        for field, statements, kind in expected:
            wrong = [statement.id for statement in statements if statement.kind != kind]
            if wrong:
                raise ValueError(f"{field} contains statements with the wrong kind: {wrong}")
        user_force_ids = [statement.id for statement in self.design_forces]
        duplicate_user_force_ids = sorted(
            force_id for force_id in set(user_force_ids) if user_force_ids.count(force_id) > 1
        )
        if duplicate_user_force_ids:
            raise ValueError(
                f"design_forces contains duplicate user-authored IDs: {duplicate_user_force_ids}"
            )
        return self


class CaseUpdate(DomainModel):
    title: str | None = None
    problem_statement: str | None = None
    desired_outcome: str | None = None
    actors_and_workflows: list[str] | None = None
    functional_requirements: list[str] | None = None
    quality_attributes: list[str] | None = None
    technical_constraints: list[str] | None = None
    organisational_constraints: list[str] | None = None
    expected_future_changes: list[str] | None = None
    non_goals: list[str] | None = None
    confirmed_facts: list[CaseStatement] | None = None
    derived_constraints: list[CaseStatement] | None = None
    assumptions: list[CaseStatement] | None = None
    unresolved_questions: list[CaseStatement] | None = None
    design_forces: list[CaseStatement] | None = None
    #: Editable and removable like every other list here. A reader who wants to withdraw an
    #: answer, or reword one, does it the way they revise anything else in their case — and a
    #: request that leaves the key out keeps what is there, which is what lets the case form
    #: submit without knowing about the round that produced these.
    clarifications: list[Clarification] | None = None
    repository: RepositoryReference | None = None
    policy_applicability: PolicyApplicabilityContext | None = None
    referenced_policy_ids: list[str] | None = None
    candidate_alternatives: list[CaseAlternative] | None = None
    reversal_conditions: list[str] | None = None
    revisit_triggers: list[str] | None = None

    @model_validator(mode="after")
    def validate_statement_kinds(self) -> CaseUpdate:
        expected = (
            ("confirmed_facts", self.confirmed_facts, StatementKind.FACT),
            (
                "derived_constraints",
                self.derived_constraints,
                StatementKind.DERIVED_CONSTRAINT,
            ),
            ("assumptions", self.assumptions, StatementKind.ASSUMPTION),
            (
                "unresolved_questions",
                self.unresolved_questions,
                StatementKind.QUESTION,
            ),
            ("design_forces", self.design_forces, StatementKind.FORCE),
        )
        for field, statements, kind in expected:
            if statements is None:
                continue
            wrong = [statement.id for statement in statements if statement.kind != kind]
            if wrong:
                raise ValueError(f"{field} contains statements with the wrong kind: {wrong}")
        return self


class RecordedAnswer(DomainModel):
    """One question this revision answered, and the answer the user gave it.

    `recorded_text` rather than a pointer at the `Clarification` this revision wrote. The
    snapshot's clarifications carry identity and could be pointed at, but this is provenance
    about one immutable revision: what was answered at that revision is a fact and cannot
    rot, while a later revision may reword the answer or delete the pair outright without
    making this record wrong. A pointer would go stale in exactly that case, which is the one
    the provenance exists for.

    It is the raw answer, the same words the pair holds — not a line composed from the
    question and the reply, which is what this field carried while the case had no way to
    represent the pair.
    """

    #: `Q-n`, resolved by the application against the review's own report. A reference that
    #: review never asked is refused rather than stored (§12.0).
    question_reference: str = Field(pattern=r"^Q-[0-9]+$")
    #: Which of the five deciding fields the answer bears on, read from the question rather
    #: than from the request: it is the question's property, not the answering client's
    #: opinion. Kept here as well as on the pair so the round can be read off the revision
    #: without resolving anything against the snapshot.
    answer_belongs_in: CaseField
    recorded_text: str = Field(min_length=1)


class AnsweredQuestions(DomainModel):
    """What prompted this revision: one round of answering one review's questions.

    `review_id` sits here rather than on each answer because one round of answering produces
    one revision against one review. Repeating it per entry would admit a state where the
    entries disagree about which review they came from, and there is no such state.

    Skipped questions are absent rather than flagged. Which ones they were is the review's
    questions minus these, so a stored flag would be a second copy of a fact the application
    can compute — the rule `ReviewAnswer.grounded` already follows.
    """

    review_id: str = Field(min_length=1)
    answers: list[RecordedAnswer] = Field(min_length=1)

    @model_validator(mode="after")
    def each_question_is_answered_once(self) -> AnsweredQuestions:
        references = [item.question_reference for item in self.answers]
        duplicated = sorted({item for item in references if references.count(item) > 1})
        if duplicated:
            raise ValueError(f"A revision answers each question once, but repeats: {duplicated}")
        return self

    def skipped_references(self, asked: list[str]) -> list[str]:
        """Which of a review's questions this round left unanswered.

        Takes the asked set rather than reading it, because a revision does not hold the
        review — the caller has it, and passing it keeps this a domain calculation rather
        than a repository lookup hidden inside a model.
        """

        answered = {item.question_reference for item in self.answers}
        return [reference for reference in asked if reference not in answered]


class CaseRevision(DomainModel):
    case_id: str
    revision: int = Field(ge=1)
    snapshot: ArchitectureCase
    event_type: Literal["created", "user_update"]
    actor: str
    #: Present where this revision came from answering a review's questions, absent where it
    #: was authored by hand — and that absence is the only thing that tells the two apart
    #: (§6C.4). Provenance, never write-back: nothing here is model-written, and the answer
    #: is still the user's (invariant 25). Distinct from the `origin_run_id` ADR 0007
    #: removed, which marked revisions authored *by a run* rather than prompted by one.
    answered: AnsweredQuestions | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_snapshot_identity(self) -> CaseRevision:
        if self.snapshot.case_id != self.case_id:
            raise ValueError("Case revision snapshot must have the same case ID")
        if self.snapshot.revision != self.revision:
            raise ValueError("Case revision snapshot must have the same revision number")
        return self
