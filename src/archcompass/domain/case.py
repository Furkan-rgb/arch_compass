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
    """One question this revision answered, and the line that answered it.

    `recorded_text` rather than a pointer into the snapshot. Only `confirmed_facts` and
    `assumptions` carry statement identity; the other three destinations are lists of bare
    strings with nothing to point at. Storing the text is also the more honest record: this
    is provenance about one immutable revision, so what was written at that revision is a
    fact and cannot rot. A later revision may reword the line without making this wrong.
    """

    #: `Q-n`, resolved by the application against the review's own report. A reference that
    #: review never asked is refused rather than stored (§12.0).
    question_reference: str = Field(pattern=r"^Q-[0-9]+$")
    #: Which list the line joined, so it can be found in the snapshot without scanning five.
    #: Read from the question rather than from the request: the destination is the question's
    #: property, not the answering client's opinion.
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
