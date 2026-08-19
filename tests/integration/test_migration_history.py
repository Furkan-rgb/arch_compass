"""An applied migration is history, and history is append-only.

The failure this holds shut, and why editing one is silent, is written where the check is:
`SQLiteDatabase._verify_unchanged`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.domain.errors import PersistenceError
from archcompass.persistence.sqlite.database import SQLiteDatabase

MIGRATIONS = Path(__file__).resolve().parents[2] / (
    "src/archcompass/adapters/persistence/migrations"
)


def _database(tmp_path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / ".archcompass" / "db.sqlite", workspace=tmp_path)
    database.initialize()
    return database


def test_every_applied_migration_records_what_it_ran(tmp_path: Path) -> None:
    database = _database(tmp_path)

    with database.connect() as connection:
        rows = connection.execute(
            "SELECT version, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert rows, "a fresh database applies the shipped migrations"
    assert all(row["checksum"] for row in rows), "each records the text it actually ran"


def test_reinitializing_an_unchanged_database_is_silent(tmp_path: Path) -> None:
    """The ordinary case: every subsequent start re-reads the files and finds them intact."""

    database = _database(tmp_path)

    database.initialize()
    database.initialize()


def test_a_migration_edited_after_it_ran_is_refused_by_name(tmp_path: Path) -> None:
    """Named at startup, where the cause is, rather than at a query that has moved on.

    The message has to say which file and what to do about it, because the fix is neither
    obvious nor local: restore the file, and put the change in a new migration beside it.
    """

    database = _database(tmp_path)
    with database.connect() as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = 'not-what-the-file-says' WHERE version = 1"
        )
        connection.commit()

    with pytest.raises(PersistenceError) as failure:
        database.initialize()

    message = str(failure.value)
    assert "001_clean_break_support.sql" in message
    assert "new migration" in message


def test_a_database_written_before_this_check_still_opens(tmp_path: Path) -> None:
    """Grandfathered deliberately.

    Nothing recorded a checksum for those rows, so there is nothing to compare — and
    refusing to open every workspace that predates the check would be a worse failure than
    the one it guards against.
    """

    database = _database(tmp_path)
    with database.connect() as connection:
        connection.execute("UPDATE schema_migrations SET checksum = NULL")
        connection.commit()

    database.initialize()


def test_clean_break_support_schema_contains_no_retired_review_tables(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    with database.connect() as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "atlas_versions" in tables
    assert "repository_lineages" in tables
    assert "boundary_reviews" not in tables
    assert "case_revisions" not in tables
    assert "consultation_runs" not in tables
