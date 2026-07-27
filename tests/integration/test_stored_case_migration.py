"""Cases written before ADR-0007 still open, and say what to do when they cannot.

A case is the one stored record nothing can regenerate: it is what someone typed. When the
advisor stopped writing its conclusions back into the case, three fields left the schema
and every snapshot already in a workspace kept them — which the domain, validating the
current schema only (ADR-0002), refuses to read. Migration 011 is what moves those
documents forward.
"""

from __future__ import annotations

import json
import sqlite3
from importlib.resources import files
from pathlib import Path

import pytest

from archcompass.adapters.persistence.case_repository import SQLiteCaseRepository
from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.errors import UnreadableStoredRecordError

ADVISOR_FIELDS = ("advisor_design_forces", "current_recommendation", "confidence")


def _era_snapshot(case: ArchitectureCase) -> str:
    """The same case as an earlier schema wrote it: user intent plus advisor output."""

    document = json.loads(case.model_dump_json())
    document["advisor_design_forces"] = [
        {"id": "stmt_era", "text": "Provider variation is the pressure here", "kind": "force"}
    ]
    document["current_recommendation"] = {"summary": "Keep the port"}
    document["confidence"] = {"level": "medium"}
    return json.dumps(document)


@pytest.fixture
def era_workspace(tmp_path: Path) -> tuple[SQLiteDatabase, ArchitectureCase]:
    """A migrated workspace holding one revision as the superseded schema wrote it.

    The row is written after migration and its version marker removed, rather than by
    stopping the migrations early: `initialize` applies every migration it finds, and the
    point under test is what 011 does to a document, not how far the runner got.
    """

    database = SQLiteDatabase(tmp_path / "archcompass.db")
    database.initialize()
    case = ArchitectureCase(
        title="Provider variation",
        problem_statement="Decide where provider-specific knowledge should live.",
        desired_outcome="One owner for provider differences.",
    )
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO cases(case_id, current_revision, created_at, updated_at) "
            "VALUES (?, 1, ?, ?)",
            (case.case_id, case.created_at.isoformat(), case.updated_at.isoformat()),
        )
        connection.execute(
            "INSERT INTO case_revisions("
            "case_id, revision, event_type, actor, created_at, snapshot_json"
            ") VALUES (?, 1, 'consultation', 'archcompass', ?, ?)",
            (case.case_id, case.created_at.isoformat(), _era_snapshot(case)),
        )
        connection.execute("DELETE FROM schema_migrations WHERE version = 11")
        connection.commit()
    return database, case


def test_an_era_case_is_unreadable_until_the_migration_runs(
    era_workspace: tuple[SQLiteDatabase, ArchitectureCase],
) -> None:
    database, case = era_workspace
    repository = SQLiteCaseRepository(database)

    with pytest.raises(UnreadableStoredRecordError) as failure:
        repository.get(case.case_id)

    # The message has to name an action its reader can take. A case is not re-run: the
    # instruction that fits every other record would be advice nobody can follow.
    assert "write this revision again" in str(failure.value)


def test_the_migration_removes_advisor_output_and_keeps_what_the_user_wrote(
    era_workspace: tuple[SQLiteDatabase, ArchitectureCase],
) -> None:
    database, case = era_workspace

    database.initialize()

    revision = SQLiteCaseRepository(database).get(case.case_id)
    assert revision.snapshot.title == case.title
    assert revision.snapshot.problem_statement == case.problem_statement
    assert revision.snapshot.desired_outcome == case.desired_outcome
    with database.connect() as connection:
        stored = json.loads(
            connection.execute(
                "SELECT snapshot_json FROM case_revisions WHERE case_id = ?",
                (case.case_id,),
            ).fetchone()["snapshot_json"]
        )
    assert not [field for field in ADVISOR_FIELDS if field in stored]
    # Nothing else moved: every field the user authored is byte-identical to what a case
    # written today holds, so the migration cannot be quietly rewriting content.
    assert stored == json.loads(case.model_dump_json())


def test_a_revision_the_advisor_wrote_keeps_its_actor(
    era_workspace: tuple[SQLiteDatabase, ArchitectureCase],
) -> None:
    """The event type has two values now; which subsystem wrote the row is the actor's job.

    Rewritten rather than dropped: a review pins the revision number it judged, and
    renumbering history would move that pin onto a different case.
    """

    database, case = era_workspace

    database.initialize()

    revision = SQLiteCaseRepository(database).get(case.case_id)
    assert revision.event_type == "user_update"
    assert revision.actor == "archcompass"


def test_a_migrated_workspace_has_no_consultation_revisions_left(
    era_workspace: tuple[SQLiteDatabase, ArchitectureCase],
) -> None:
    database, _ = era_workspace

    database.initialize()

    with database.connect() as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM case_revisions WHERE event_type = 'consultation'"
        ).fetchone()[0]
    assert remaining == 0


def test_migrating_twice_changes_nothing(
    era_workspace: tuple[SQLiteDatabase, ArchitectureCase],
) -> None:
    """`json_remove` on an absent path is a no-op, and the guard keeps untouched rows out."""

    database, case = era_workspace
    database.initialize()
    with database.connect() as connection:
        once = connection.execute(
            "SELECT snapshot_json FROM case_revisions WHERE case_id = ?", (case.case_id,)
        ).fetchone()["snapshot_json"]
        connection.execute("DELETE FROM schema_migrations WHERE version = 11")
        connection.commit()

    database.initialize()

    with database.connect() as connection:
        twice = connection.execute(
            "SELECT snapshot_json FROM case_revisions WHERE case_id = ?", (case.case_id,)
        ).fetchone()["snapshot_json"]
    assert twice == once


def test_a_case_written_today_is_untouched_by_the_migration(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "archcompass.db")
    database.initialize()
    repository = SQLiteCaseRepository(database)
    case = ArchitectureCase(
        title="Current schema",
        problem_statement="A case written after ADR-0007.",
        desired_outcome="It reads back exactly as written.",
    )
    repository.create(case, actor="test")

    with database.connect() as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version = 11")
        connection.commit()
    database.initialize()

    assert repository.get(case.case_id).snapshot.title == "Current schema"


def test_the_workspace_database_applies_every_migration(tmp_path: Path) -> None:
    """A fresh workspace applies every shipped migration exactly once, in order.

    Deliberately not "the versions are contiguous". That assertion used to be here, and it
    caused the failure it was meant to prevent: a withdrawn migration left a gap, the gap
    was closed by renumbering a later migration down into the free slot, and every workspace
    that had already recorded that number then skipped the renumbered one — so the table it
    created was missing in exactly the workspaces that had data in them.

    A migration number is an identifier, not a position. What matters is that each shipped
    file runs once and that ordering is respected; a retired number is a gap that must stay
    open.
    """

    database = SQLiteDatabase(tmp_path / "archcompass.db")
    database.initialize()

    shipped = sorted(
        int(resource.name.split("_", maxsplit=1)[0])
        for resource in files("archcompass.adapters.persistence.migrations").iterdir()
        if resource.name.endswith(".sql")
    )
    with database.connect() as connection:
        versions = [
            int(row[0])
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]

    assert versions == shipped
    assert len(versions) == len(set(versions))
    assert max(versions) >= 11


def test_a_migration_number_is_never_reused(tmp_path: Path) -> None:
    """A workspace that recorded a since-withdrawn version still reaches the full schema.

    This is the regression for a real failure: reusing a retired number meant the migration
    never ran where it was most needed, and the first sign of it was a review dying on
    `no such table` in a workspace that had been working the day before.
    """

    path = tmp_path / "archcompass.db"
    SQLiteDatabase(path).initialize()
    with sqlite3.connect(path) as connection:
        # Stand in for a workspace that applied a version this build no longer ships.
        retired = 15
        connection.execute("DELETE FROM schema_migrations WHERE version >= ?", (retired,))
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (retired, "2026-01-01T00:00:00+00:00"),
        )
        connection.execute("DROP TABLE IF EXISTS atlas_module_facts")
        connection.commit()

    SQLiteDatabase(path).initialize()

    with sqlite3.connect(path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "atlas_module_facts" in tables


def test_sqlite_supports_the_json_functions_the_migration_needs() -> None:
    """Named rather than assumed: without JSON1 the migration would be a silent no-op."""

    connection = sqlite3.connect(":memory:")
    try:
        result = connection.execute(
            """SELECT json_remove('{"keep":1,"drop":2}', '$.drop')"""
        ).fetchone()[0]
    finally:
        connection.close()
    assert json.loads(result) == {"keep": 1}
