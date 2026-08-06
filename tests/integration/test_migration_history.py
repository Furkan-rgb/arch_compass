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


def test_the_choice_table_carries_the_columns_the_repository_writes(
    tmp_path: Path,
) -> None:
    """The shape the original fault was actually about, asserted against the whole chain."""

    database = _database(tmp_path)

    with database.connect() as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(reasoning_model_choice)")
        }

    assert {"thinking", "input_token_limit", "output_token_limit"} <= columns
    # The table it replaces is gone rather than left beside it, so nothing can read a stale
    # choice back out of a shape the application no longer writes.
    assert "profile_id" not in columns


def test_a_workspace_stopped_at_021_reaches_the_current_choice_table(tmp_path: Path) -> None:
    """The upgrade path this actually has to serve: a database created before 022 existed.

    The 021-era database is built by running the shipped files up to 021 and recording them,
    which is the one way to get that shape without asserting anything about it: reading the
    migrations is not editing them, and a stub written by hand goes stale the moment a later
    migration widens a table the stub left out — 024 widens two of them.

    The version rows are written without a checksum on purpose. That is what a database of
    this age has, and reaching the current schema from it is exactly what the grandfathering
    in `_verify_unchanged` is for.
    """

    path = tmp_path / ".archcompass" / "db.sqlite"
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
    )
    scripts = sorted(
        (int(item.name.split("_", maxsplit=1)[0]), item)
        for item in MIGRATIONS.iterdir()
        if item.name.endswith(".sql") and int(item.name.split("_", maxsplit=1)[0]) <= 21
    )
    for _, script in scripts:
        connection.executescript(script.read_text(encoding="utf-8"))
    applied = [version for version, _ in scripts]
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
            for row in opened.execute("PRAGMA table_info(reasoning_model_choice)")
        }
    assert {"thinking", "input_token_limit", "output_token_limit"} <= columns
