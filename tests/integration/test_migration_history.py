"""An applied migration is history, and history is append-only.

The failure this holds shut, and why editing one is silent, is written where the check is:
`SQLiteDatabase._verify_unchanged`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.domain.errors import PersistenceError

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
    assert "001_initial.sql" in message
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


def test_the_selection_table_carries_the_columns_the_repository_writes(
    tmp_path: Path,
) -> None:
    """The shape the original fault was actually about, asserted against the whole chain."""

    database = _database(tmp_path)

    with database.connect() as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(reasoning_model_selection)")
        }

    assert {"input_token_limit", "output_token_limit"} <= columns


def test_a_workspace_stopped_at_021_gains_the_columns_from_022(tmp_path: Path) -> None:
    """The upgrade path this actually has to serve: a database created before 022 existed.

    Built by hand at that older shape rather than by rewinding the shipped files, because a
    test that edits a migration to prove migrations must not be edited would be arguing with
    itself.
    """

    path = tmp_path / ".archcompass" / "db.sqlite"
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        CREATE TABLE reasoning_model_selection (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            profile_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            selected_at TEXT NOT NULL,
            failed_at TEXT,
            failure_detail TEXT NOT NULL DEFAULT ''
        );
        """
    )
    applied = sorted(
        int(item.name.split("_", maxsplit=1)[0])
        for item in MIGRATIONS.iterdir()
        if item.name.endswith(".sql") and int(item.name.split("_", maxsplit=1)[0]) <= 21
    )
    connection.executemany(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, '2026-08-01T00:00:00Z')",
        [(version,) for version in applied],
    )
    connection.commit()
    connection.close()

    SQLiteDatabase(path, workspace=tmp_path).initialize()

    with sqlite3.connect(path) as opened:
        columns = {
            str(row[1])
            for row in opened.execute("PRAGMA table_info(reasoning_model_selection)")
        }
    assert {"input_token_limit", "output_token_limit"} <= columns
