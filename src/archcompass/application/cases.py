"""Architecture case use cases."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from archcompass.application.standings import branch_chain
from archcompass.domain.base import DomainModel, utc_now
from archcompass.domain.case import (
    AnsweredQuestions,
    ArchitectureCase,
    CaseRevision,
    CaseUpdate,
    Clarification,
    RecordedAnswer,
    RepositoryReference,
)
from archcompass.domain.errors import CaseNotFoundError, CaseValidationError
from archcompass.domain.review import BoundaryReview
from archcompass.domain.workspace import CaseSummary
from archcompass.ports.repositories import (
    BoundaryReviewRepository,
    CaseRepository,
    LineageRepository,
)


class WrittenAnswer(DomainModel):
    """One answer as the reader submitted it: which question, and what they typed.

    Carries no question and no destination. Both are the question's own properties and are
    read from the review, so a client cannot pair an answer with a question the review never
    asked, nor give it a force its question never named (§12.0 — the application decides what
    to look at). What the client is authoritative about is the one thing only the reader
    could supply, which is the answer.

    `recorded_text` is the answer verbatim. It used to be a line the browser composed by
    joining the question's subject to the reply, because the case had nowhere to put the pair;
    the case has somewhere now, so the reader types an answer and nothing else.
    """

    question_reference: str = Field(pattern=r"^Q-[0-9]+$")
    recorded_text: str = Field(min_length=1)


#: Leaf names that name a layout rather than a project. Every bundled example lives at
#: `eval/cases/<name>/repository`, so titling by the leaf alone gave four loaded examples
#: four cases all called "Boundaries in repository" — one history, unreadable.
_LAYOUT_NAMES = frozenset({"repository", "repo", "src", "source", "code"})


def _title_for(root: Path) -> str:
    """A name for a case nobody has named, taken from the repository it is about.

    Derived rather than invented, and that distinction is the whole of why this is allowed.
    A repository's own directory name is a fact about what is being reviewed; a problem
    statement written on the user's behalf would be intent they never stated, which the case
    exists to hold and only they can supply (invariant 23). A leaf that names a layout
    rather than a project is skipped for the same reason it would fail as a title: it is a
    fact about directory convention, not about what is being reviewed.
    """

    resolved = root.expanduser().resolve()
    for part in reversed(resolved.parts):
        if part and part.casefold() not in _LAYOUT_NAMES:
            return f"Boundaries in {part}"
    return f"Boundaries in {resolved.name or root}"


class CaseService:
    def __init__(
        self,
        repository: CaseRepository,
        reviews: BoundaryReviewRepository,
        lineages: LineageRepository,
    ) -> None:
        self._repository = repository
        self._reviews = reviews
        self._lineages = lineages

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

    def continue_from_repository(
        self,
        root: Path,
        *,
        branch_id: str | None,
        actor: str = "user",
    ) -> CaseRevision:
        """The case a repeat visit to this branch carries on with, or a first one.

        A review is a conversation, not a transaction. The first pass asks what the code
        cannot settle, the reader answers, and the answers become clarifications on the case
        — so a second visit that composed a fresh case would throw all of that away and ask
        the very questions it had already been given answers to. Worse, silently: the reader
        sees the same five questions and no sign that anything they typed was kept.

        So the newest case reviewed on this branch is reused, at whatever revision it has
        reached. Everything else then follows from machinery that already exists: the verdict
        cache keys on what the case says and the revision it says it at, so an unchanged
        branch re-judged against an unchanged case pays for no model call; and the elicitation
        stage, reading a case that now holds the answers, finds nothing left unstated and the
        run concludes in one pass instead of stopping to ask. Nothing in the review had to
        learn about any of this — a run is still one case, one atlas — which is why continuity
        belongs here and not in a branch inside the run.

        The **branch** rather than the repository, because a branch is the scope everything
        durable already lives in: its standing decisions, its line of revisions, and now its
        case. Two branches of one repository are two pieces of work, and one of them must not
        be able to append answers to the other's backbone.

        A branch with nothing of its own reads through to the branch it came from, which is the
        same rule the standings follow and is here for the same reason. A feature branch cut
        from `main` this morning is not a repository nobody has ever discussed: the answers on
        `main`'s case are about this code, and starting blank would ask the reader every
        question their colleagues already answered. What the branch does *not* do is write back
        — the first review on it appends a revision under its own branch, so the two lines
        diverge from the moment either has something to say, and `main`'s case is never edited
        by a pull request.

        Reviews rather than cases are what is searched, and a durable id rather than the path.
        A case nobody ever reviewed is one somebody started and left, and stepping into it
        would resume a conversation that never happened; the branch's durable identity is what
        makes the continuation survive the checkout being moved or cloned again.

        A checkout with no lineage, or a chain nothing has been run on, starts a case exactly
        as a first visit does — as does a run whose case has since gone. There is no error to
        report in any of those: the reader asked to review a repository, and a first case is
        the honest answer to that.
        """

        continuing = self.continuing_case(branch_id=branch_id)
        if continuing is not None:
            return continuing
        return self.start_from_repository(root, actor=actor)

    def continuing_case(self, *, branch_id: str | None) -> CaseRevision | None:
        """The case this branch would carry on with, or `None` if it would start one.

        The lookup half of `continue_from_repository`, without the creation half, for a caller
        that needs to know which case a run *would* use without a run having happened. The
        pre-flight check is that caller: it works out whether a new revision would find
        anything, and a check that opened a blank case on the way to answering "nothing has
        changed" would have changed something itself.

        `None` is therefore not an error and not a fallback — it is the answer that this
        branch has nothing behind it, which is precisely what makes its next revision a first
        one.
        """

        for candidate in branch_chain(self._lineages, branch_id):
            continuing = self._reviews.latest_case_for_branch(candidate)
            if continuing is None:
                continue
            try:
                return self._repository.get(continuing)
            except CaseNotFoundError:
                # The case this branch was reviewing has been deleted. The base may still
                # have one worth continuing, so the walk goes on rather than falling straight
                # through to a blank case.
                continue
        return None

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

        The client sends the reference and the answer and nothing else. The question half of
        each pair is taken from the review's own report, verbatim, and so is the force the
        answer carries — a client that could supply either could pair an answer with a
        question nobody asked, or give it a weight its question never named, and there would
        be no way afterwards to tell that from a question that did.

        An answer is free text and nothing here checks it against anything. Where the question
        offered `answer_options`, a reader who picked one sent its text and nothing else: it
        arrives indistinguishable from an answer they typed, no record says which option was
        taken, and no code branches on one. That is deliberate — an option is model-written, so
        keying anything off it would break §12.0 in the one place it would be hardest to see,
        and validating an answer against the set would turn an offer into a menu.

        Both halves are kept together as a `Clarification` rather than composed into a line in
        one of the five deciding lists. The composition existed because the case had no shape
        for a pair, and it was paid for twice: the reader was shown an answer that restated
        the question above it, and the stages that re-judge the case saw the join instead of
        the question, so the context that made the answer readable was the one thing they
        could not read.
        """

        report = review.report
        if report is None:
            raise CaseValidationError(f"Review {review.review_id} asked nothing to answer")
        asked = {item.reference: item for item in report.overview.open_questions}
        if not written:
            raise CaseValidationError("Answering records at least one answer")

        answers: list[RecordedAnswer] = []
        recorded: list[Clarification] = []
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
            # The question's text, never its `Q-n`. A reference code is this application's own
            # identifier and means nothing to a stage reading the case months later, which is
            # the whole of §12.0's rule about them; the provenance above is where the code
            # belongs, because that record is about this review.
            recorded.append(
                Clarification(
                    question=question.question,
                    answer=text,
                    bears_on=question.answer_belongs_in,
                )
            )

        current = self._repository.get(review.case_id, review.case_revision)
        return self._repository.append(
            self._with_answers(current.snapshot, recorded),
            expected_revision=current.revision,
            event_type="user_update",
            actor=actor,
            answered=AnsweredQuestions(review_id=review.review_id, answers=answers),
        )

    @staticmethod
    def _with_answers(
        snapshot: ArchitectureCase,
        recorded: list[Clarification],
    ) -> ArchitectureCase:
        """The case with this round's pairs added to the clarifications it already held.

        Appended, never replaced, and nothing else on the case is touched. A reader who
        answers one of five questions must not have the rest of their case rewritten, which
        is what submitting the whole case form does and the reason answering does not go
        through it. Earlier rounds stay where they are: a case accumulates the exchanges that
        built it, and the pair from the first round is still the reason a verdict came out the
        way it did in the second.
        """

        case_data = snapshot.model_dump()
        case_data["clarifications"] = [
            *(case_data.get("clarifications") or []),
            *(item.model_dump() for item in recorded),
        ]
        case_data["updated_at"] = utc_now()
        return ArchitectureCase.model_validate(case_data)

    def history(self, case_id: str) -> list[CaseRevision]:
        return self._repository.history(case_id)

    def list(self, *, limit: int = 100) -> list[CaseSummary]:
        return self._repository.list(limit=limit)
