"""SQLite connection lifecycle and migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
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
        migration_root = files("archcompass.adapters.persistence.migrations")
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
                current_rows = connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
                current = {int(row[0]) for row in current_rows}
                for resource in sorted(migration_root.iterdir(), key=lambda item: item.name):
                    if not resource.name.endswith(".sql"):
                        continue
                    version = int(resource.name.split("_", maxsplit=1)[0])
                    if version in current:
                        continue
                    connection.executescript(resource.read_text(encoding="utf-8"))
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, datetime.now(UTC).isoformat()),
                    )
                connection.commit()
        except (OSError, sqlite3.Error, ValueError) as error:
            raise PersistenceError(f"Could not initialize database {self.path}: {error}") from error

    @contextmanager
    def connect(self, *, load_vectors: bool = False) -> Generator[sqlite3.Connection]:
        self.path = self._validated_path()
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA journal_mode = WAL")
            if load_vectors:
                import sqlite_vec

                connection.enable_load_extension(True)
                sqlite_vec.load(connection)
                connection.enable_load_extension(False)
            yield connection
        except sqlite3.Error as error:
            if connection is not None:
                connection.rollback()
            raise PersistenceError(f"SQLite operation failed: {error}") from error
        finally:
            if connection is not None:
                connection.close()

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
