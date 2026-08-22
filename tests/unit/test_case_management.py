from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from archcompass.domain import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    CaseFacet,
    PolicyContext,
    Question,
)
from archcompass.domain._support import utc_now
from archcompass.domain.errors import CaseRevisionConflictError
from archcompass.persistence.cases import SQLiteCoreCaseRepository
from archcompass.persistence.reviews import SQLiteCoreReviewRepository
from archcompass.workflow.cases import ArchitectureCaseService


class NoBranchParents:
    def parent_of(self, branch_id: str) -> str | None:
        return None


def test_case_service_creates_immutable_revisions(tmp_path: Path) -> None:
    database = tmp_path / "cases.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cases = SQLiteCoreCaseRepository(connect)
    service = ArchitectureCaseService(
        cases, SQLiteCoreReviewRepository(connect), NoBranchParents()  # type: ignore[arg-type]
    )
    created = service.create()
    revised = service.rescope(
        created.id, policy_context=PolicyContext(organisation="acme")
    )

    assert created.revision == 1
    assert created.answers == ()
    # The only thing a person can still write directly. Intent is not among it: it arrives
    # as an answer to a question a judgement raised, and there is no method to bypass that.
    assert revised.revision == 2
    assert revised.policy_context.organisation == "acme"
    assert service.history(created.id) == (created, revised)


def test_a_case_has_no_way_to_be_told_anything_but_an_answer() -> None:
    """The removal, held as a rule rather than as an absence.

    Constraints and decisions were a channel nothing in the product could feed: no surface
    offered writing one and no review ever produced one, so the only way in was
    hand-authored YAML. What a review needs to know now arrives the way the charter says it
    should — as a reply to a question a judgement raised, carrying who answered and when.

    This fails the moment somebody adds a field to `ArchitectureCase` that a person can
    state up front, which is the shape of the bug this is guarding against.
    """

    stated = {
        name
        for name in ArchitectureCase.__dataclass_fields__
        if name not in {"id", "revision", "created_at", "updated_at"}
    }

    assert stated == {"answers", "policy_context"}


def test_a_revision_number_is_taken_from_the_store_not_from_the_case(
    tmp_path: Path,
) -> None:
    """A review opened from an older revision writes beside it rather than over it.

    Answering used to bump the revision the run was holding and insert it with `DO NOTHING`.
    Open a case at revision 2 while revision 3 already existed, and the answers went to a
    number that was taken: the insert did nothing, the read handed back somebody else's
    revision, and nothing anywhere said so.
    """

    database = tmp_path / "cases.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cases = SQLiteCoreCaseRepository(connect)
    first = cases.record(ArchitectureCase.create())
    second = cases.record(first.open_revision())
    cases.record(second.open_revision())

    assert cases.next_revision(first.id) == 4
    # What the reviser does with the older revision it was handed.
    reopened = cases.get(first.id, revision=2)
    forked = cases.record(reopened.open_revision(cases.next_revision(first.id)))

    assert forked.revision == 4
    assert cases.get(first.id).revision == 4
    assert [item.revision for item in cases.history(first.id)] == [1, 2, 3, 4]


def test_writing_a_different_revision_over_one_already_stored_is_an_error(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cases.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cases = SQLiteCoreCaseRepository(connect)
    stored = cases.record(ArchitectureCase.create())
    question = Question.create(
        text="Who owns this boundary?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate-1",),
        round=1,
    )
    answered = stored.with_answer(
        Answer(question, AnswerStatus.ANSWERED, "Platform", "reader", utc_now())
    )

    # Recording the same revision again is a resumed graph replaying a node, and says
    # nothing. Recording a different one under that number is a lost answer.
    assert cases.record(stored) == stored
    with pytest.raises(CaseRevisionConflictError):
        cases.record(answered)
