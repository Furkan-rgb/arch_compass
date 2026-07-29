"""Architecture case use cases."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from archcompass.domain.base import DomainModel, utc_now
from archcompass.domain.case import (
    AnsweredQuestions,
    ArchitectureCase,
    CaseField,
    CaseRevision,
    CaseUpdate,
    RecordedAnswer,
    RepositoryReference,
    StatementKind,
)
from archcompass.domain.errors import CaseValidationError
from archcompass.domain.review import BoundaryReview
from archcompass.domain.workspace import CaseSummary
from archcompass.ports.repositories import CaseRepository

#: The two answer destinations whose entries are statements rather than plain lines. Which
#: kind a statement carries is decided by the list it joins, so it is set from this rather
#: than asked for — the same rule the case form and the questions surface already follow.
_STATEMENT_KINDS: dict[CaseField, StatementKind] = {
    CaseField.CONFIRMED_FACTS: StatementKind.FACT,
    CaseField.ASSUMPTIONS: StatementKind.ASSUMPTION,
}


class WrittenAnswer(DomainModel):
    """One answer as the reader submitted it: which question, and the line they saw.

    Carries no destination. Where an answer belongs is the question's property and is read
    from the review, so a client cannot route an answer into a field its question never
    named (§12.0 — the application decides what to look at).
    """

    question_reference: str = Field(pattern=r"^Q-[0-9]+$")
    recorded_text: str = Field(min_length=1)


def _title_for(root: Path) -> str:
    """A name for a case nobody has named, taken from the repository it is about.

    Derived rather than invented, and that distinction is the whole of why this is allowed.
    A repository's own directory name is a fact about what is being reviewed; a problem
    statement written on the user's behalf would be intent they never stated, which the case
    exists to hold and only they can supply (invariant 23).
    """

    name = root.expanduser().resolve().name or str(root)
    return f"Boundaries in {name}"


class CaseService:
    def __init__(self, repository: CaseRepository) -> None:
        self._repository = repository

    def create(self, case: ArchitectureCase, *, actor: str = "user") -> CaseRevision:
        normalized = case.model_copy(update={"revision": 1})
        return self._repository.create(normalized, actor=actor)

    def start_from_repository(
        self,
        root: Path,
        *,
        actor: str = "user",
    ) -> CaseRevision:
        """A case holding nothing but which repository it is about (master plan §6C.1).

        The entry point for someone who has not written a case and should not have to. The
        review runs on the repository alone, and what it could not weigh comes back as the
        questions it asks — so the case is filled in by answering rather than before
        anything has been seen.

        Empty rather than pre-filled. A placeholder problem statement would be read by the
        judging stage as intent the user never expressed, and a verdict resting on it would
        be resting on this function's prose.
        """

        return self.create(
            ArchitectureCase(
                title=_title_for(root),
                repository=RepositoryReference(root_path=str(root.expanduser().resolve())),
            ),
            actor=actor,
        )

    def show(self, case_id: str, revision: int | None = None) -> CaseRevision:
        return self._repository.get(case_id, revision)

    def update(
        self,
        case_id: str,
        update: CaseUpdate,
        *,
        actor: str = "user",
    ) -> CaseRevision:
        current = self._repository.get(case_id)
        case_data = current.snapshot.model_dump()
        changes = update.model_dump(exclude_unset=True)
        changes["updated_at"] = utc_now()
        case_data.update(changes)
        # Pydantic's model_copy(update=...) deliberately skips validation.
        # Case updates contain nested statements, so reconstruct the aggregate
        # to turn their serialized dictionaries back into domain models before
        # the revision validators inspect them.
        next_case = ArchitectureCase.model_validate(case_data)
        return self._repository.append(
            next_case,
            expected_revision=current.revision,
            event_type="user_update",
            actor=actor,
        )

    def answer(
        self,
        review: BoundaryReview,
        written: list[WrittenAnswer],
        *,
        actor: str = "user",
    ) -> CaseRevision:
        """Record a round of answers as one revision that says what it answered.

        One call rather than the two the browser used to make. Composing the update in the
        client and patching the case worked, but it made provenance optional by
        construction: a caller that forgot to send it produced a revision that had silently
        lost the link to the question it came from, and nothing could tell afterwards.

        The client sends the reference and the final text and nothing else. Which case field
        an answer joins is the question's own property, so it is read from the review's
        report rather than accepted from the request — a client that could choose the
        destination could route an answer into a field the question never named, and there
        would be no way to tell that from a question that named it.

        The text is the client's because it has to be: the reader edits the composed line
        before saving, and that edited line is the one that must be recorded (§6C.4).
        """

        report = review.report
        if report is None:
            raise CaseValidationError(f"Review {review.review_id} asked nothing to answer")
        asked = {item.reference: item for item in report.overview.open_questions}
        if not written:
            raise CaseValidationError("Answering records at least one answer")

        answers: list[RecordedAnswer] = []
        grouped: dict[CaseField, list[str]] = {}
        for item in written:
            question = asked.get(item.question_reference)
            if question is None:
                known = ", ".join(asked) or "none"
                raise CaseValidationError(
                    f"Review {review.review_id} asked no question "
                    f"{item.question_reference} (it asked: {known})"
                )
            text = item.recorded_text.strip()
            if not text:
                raise CaseValidationError(
                    f"The answer to {item.question_reference} is blank; "
                    "leave a question out rather than answering it with nothing"
                )
            answers.append(
                RecordedAnswer(
                    question_reference=question.reference,
                    answer_belongs_in=question.answer_belongs_in,
                    recorded_text=text,
                )
            )
            grouped.setdefault(question.answer_belongs_in, []).append(text)

        current = self._repository.get(review.case_id, review.case_revision)
        return self._repository.append(
            self._with_answers(current.snapshot, grouped),
            expected_revision=current.revision,
            event_type="user_update",
            actor=actor,
            answered=AnsweredQuestions(review_id=review.review_id, answers=answers),
        )

    @staticmethod
    def _with_answers(
        snapshot: ArchitectureCase,
        grouped: dict[CaseField, list[str]],
    ) -> ArchitectureCase:
        """The case with each answer appended to the list its question named.

        Appended, never replaced, and only to the fields that were answered. A reader who
        answers one of five questions must not have their other four lists rewritten, which
        is what submitting the whole case form does and the reason answering does not go
        through it.
        """

        case_data = snapshot.model_dump()
        for field, texts in grouped.items():
            existing = list(case_data.get(field.value) or [])
            # The kind is fixed by which list a statement joins, so it is set here rather
            # than asked for — the domain rejects a statement whose kind does not match.
            kind = _STATEMENT_KINDS.get(field)
            case_data[field.value] = existing + [
                {"text": text, "kind": kind.value} if kind else text for text in texts
            ]
        case_data["updated_at"] = utc_now()
        return ArchitectureCase.model_validate(case_data)

    def history(self, case_id: str) -> list[CaseRevision]:
        return self._repository.history(case_id)

    def list(self, *, limit: int = 100) -> list[CaseSummary]:
        return self._repository.list(limit=limit)
