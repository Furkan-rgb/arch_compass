"""SQLite connection lifecycle and migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from importlib.resources import files
from pathlib import Path

from archcompass.domain.errors import PersistenceError


class SQLiteDatabase:
    def __init__(self, path: Path, *, workspace: Path | None = None) -> None:
        self._requested_path = path.expanduser().absolute()
        self._workspace = (
            workspace.expanduser().resolve(strict=True) if workspace is not None else None
        )
        self.path = self._validated_path()

    def initialize(self) -> None:
        self.path = self._validated_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        migration_root = files("archcompass.persistence.sqlite.migrations")
        try:
            with self.connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                # Added after the fact, so a database written before it exists has the
                # column with nothing in it. That is the grandfathered case below.
                if "checksum" not in {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(schema_migrations)")
                }:
                    connection.execute(
                        "ALTER TABLE schema_migrations ADD COLUMN checksum TEXT"
                    )
                connection.commit()
                current_rows = connection.execute(
                    "SELECT version, checksum FROM schema_migrations ORDER BY version"
                ).fetchall()
                current = {int(row[0]): row[1] for row in current_rows}
                for resource in sorted(migration_root.iterdir(), key=lambda item: item.name):
                    if not resource.name.endswith(".sql"):
                        continue
                    version = int(resource.name.split("_", maxsplit=1)[0])
                    script = resource.read_text(encoding="utf-8")
                    if version in current:
                        self._verify_unchanged(
                            resource.name, script, recorded=current[version]
                        )
                        continue
                    self._apply_migration(connection, version=version, script=script)
        except (OSError, sqlite3.Error, ValueError) as error:
            raise PersistenceError(f"Could not initialize database {self.path}: {error}") from error

    @staticmethod
    def _checksum(script: str) -> str:
        return sha256(script.encode("utf-8")).hexdigest()

    @staticmethod
    def _verify_unchanged(name: str, script: str, *, recorded: str | None) -> None:
        """Refuse to run against a database whose history no longer matches these files.

        A migration is only ever read once — the run that applies it — and every run after
        that skips it by version number. So editing an applied migration changes nothing and
        announces nothing: the file says one thing, the database says another, and the two
        disagree until some unrelated query fails. That happened here, with two columns added
        to 021 after it had run, surfacing much later as `no column named input_token_limit`
        from a click on a model — a message about a table, pointing nowhere near the cause.

        A recorded `None` is a row written before this check existed. Grandfathered rather
        than treated as a mismatch: no checksum was stored, so there is nothing to compare,
        and refusing to open every database that predates this would be a worse failure than
        the one it guards against.
        """

        if recorded is None or recorded == SQLiteDatabase._checksum(script):
            return
        raise PersistenceError(
            f"Migration {name} has changed since it was applied to this database. An applied "
            "migration is history and history is append-only: restore the file to what it "
            "was and put the change in a new migration beside it."
        )

    @staticmethod
    def _apply_migration(
        connection: sqlite3.Connection,
        *,
        version: int,
        script: str,
    ) -> None:
        """Apply one migration and its version marker in one SQLite transaction.

        Foreign keys are enforced everywhere else and are off for exactly the length of a
        migration, which is SQLite's own recipe for rebuilding a table and the only way to
        rebuild one that anything points at. A rebuild drops the old table, and `DROP TABLE`
        under `foreign_keys = ON` runs an implicit `DELETE` first: dropping a *parent* is
        therefore an instant `FOREIGN KEY constraint failed` for every child row, before the
        replacement it is about to be renamed into place can exist. That is not hypothetical.
        Migration 019 rebuilds `case_revisions`, which six tables reference, and it died on
        the first workspace that had reviews in it while passing every test, because the
        tests migrated empty databases.

        `PRAGMA defer_foreign_keys` looks like the in-transaction answer and is not: the drop
        registers a violation per orphaned row, and restoring the table does not decrement
        that counter, so the failure simply moves to the commit. The pragma has to be off,
        and it only takes effect outside a transaction — hence the toggle out here rather
        than a line at the top of a migration script, where it would be silently ignored.

        Suspending enforcement means a migration could leave orphans behind, so it is paid
        for rather than merely accepted: `foreign_key_check` runs inside the transaction, and
        anything it finds rolls the migration back. That is a stronger guarantee than the
        per-statement enforcement it replaces, which never checked the rows a migration did
        not itself touch.
        """
        statements = SQLiteDatabase._migration_statements(script)
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at, checksum) "
                    "VALUES (?, ?, ?)",
                    (
                        version,
                        datetime.now(UTC).isoformat(),
                        SQLiteDatabase._checksum(script),
                    ),
                )
                orphaned = connection.execute("PRAGMA foreign_key_check").fetchall()
                if orphaned:
                    # Name the first one. A migration that orphans rows is a bug in the
                    # migration, and the table and rowid are what locates it.
                    table, rowid, parent, _ = orphaned[0]
                    raise PersistenceError(
                        f"Migration {version} left {len(orphaned)} row(s) with no parent: "
                        f"{table} rowid {rowid} references missing {parent}"
                    )
            except (sqlite3.Error, ValueError, PersistenceError):
                connection.rollback()
                raise
            connection.commit()
        finally:
            # Restored on the way out however this ended, so a failed migration cannot leave
            # the connection handed back to the application with enforcement switched off.
            connection.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _migration_statements(script: str) -> list[str]:
        """Split complete SQLite statements without `executescript`'s implicit commit."""
        statements: list[str] = []
        pending = ""
        for line in script.splitlines(keepends=True):
            pending += line
            if sqlite3.complete_statement(pending):
                statement = pending.strip()
                if statement:
                    statements.append(statement)
                pending = ""
        if pending.strip():
            raise ValueError("Migration ends with an incomplete SQL statement")
        return statements

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection]:
        self.path = self._validated_path()
        connection: sqlite3.Connection | None = None
        try:
            connection = self.raw_connect()
            yield connection
        except sqlite3.Error as error:
            if connection is not None:
                connection.rollback()
            raise PersistenceError(f"SQLite operation failed: {error}") from error
        finally:
            if connection is not None:
                connection.close()

    def raw_connect(self, *, check_same_thread: bool = True) -> sqlite3.Connection:
        """A configured connection for adapters whose library owns its lifecycle."""

        self.path = self._validated_path()
        connection = sqlite3.connect(self.path, check_same_thread=check_same_thread)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _validated_path(self) -> Path:
        resolved = self._requested_path.resolve(strict=False)
        if self._workspace is None:
            return resolved
        try:
            relative = self._requested_path.relative_to(self._workspace)
            resolved.relative_to(self._workspace)
        except ValueError as error:
            raise PersistenceError(
                f"State database path escapes workspace {self._workspace}"
            ) from error
        current = self._workspace
        for part in relative.parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise PersistenceError(f"State database path uses symlink: {current}")
        if self._requested_path.is_symlink():
            raise PersistenceError(
                f"State database file is a symlink: {self._requested_path}"
            )
        return resolved
