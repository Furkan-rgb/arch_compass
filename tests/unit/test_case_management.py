from __future__ import annotations

import sqlite3
from pathlib import Path

from archcompass.domain import ArchitectureCase, PolicyContext
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
