from __future__ import annotations

import sqlite3
from pathlib import Path

from archcompass.adapters.persistence.core_review_repository import (
    SQLiteCoreCaseRepository,
    SQLiteCoreReviewRepository,
)
from archcompass.application.case_management import ArchitectureCaseService
from archcompass.domain import CaseConstraint, CaseFacet


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
    created = service.create(goal="Keep change local")
    revised = service.revise(
        created.id,
        constraints=(CaseConstraint("No new service", CaseFacet.CONSTRAINT),),
    )

    assert created.revision == 1
    assert created.constraints == ()
    assert revised.revision == 2
    assert revised.constraints[0].text == "No new service"
    assert service.history(created.id) == (created, revised)
