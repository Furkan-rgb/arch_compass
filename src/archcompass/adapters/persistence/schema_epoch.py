"""Explicit clean-break workspace epoch detection, export, and recoverable reset."""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from archcompass.domain.errors import LegacySchemaError, PersistenceError

CLEAN_BREAK_EPOCH = 2
LEGACY_DATABASE_NAME = "archcompass.db"
CLEAN_BREAK_DATABASE_NAME = "archcompass-v2.db"


@dataclass(frozen=True, slots=True)
class WorkspaceSchemaEpoch:
    state_directory: Path

    @property
    def legacy_database(self) -> Path:
        return self.state_directory / LEGACY_DATABASE_NAME

    @property
    def database(self) -> Path:
        return self.state_directory / CLEAN_BREAK_DATABASE_NAME

    def require_current_or_empty(self) -> None:
        if self.database.exists():
            return
        if self.legacy_database.exists():
            raise LegacySchemaError(
                "This workspace uses ArchCompass's legacy database schema. Nothing was "
                "changed. Run `archcompass workspace export-legacy PATH` before "
                "`archcompass workspace reset`, or continue with the older ArchCompass "
                "version that created it."
            )

    def initialize(self) -> Path:
        self.require_current_or_empty()
        self.state_directory.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS archcompass_schema_epoch ("
                "epoch INTEGER PRIMARY KEY CHECK(epoch = 2), created_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO archcompass_schema_epoch(epoch, created_at) VALUES (?, ?) "
                "ON CONFLICT(epoch) DO NOTHING",
                (CLEAN_BREAK_EPOCH, datetime.now(UTC).isoformat()),
            )
        return self.database

    def export_legacy(self, destination: Path) -> Path:
        source = self.legacy_database.resolve(strict=False)
        if not source.is_file():
            raise LegacySchemaError(f"No legacy database exists at {source}")
        target = destination.expanduser().resolve(strict=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise PersistenceError(f"Refusing to overwrite existing export {target}")
        try:
            with sqlite3.connect(source) as old, sqlite3.connect(target) as exported:
                old.backup(exported)
        except sqlite3.Error as error:
            target.unlink(missing_ok=True)
            raise PersistenceError(f"Could not export legacy database: {error}") from error
        return target

    def reset(self) -> Path | None:
        """Archive legacy state after an explicit command; never erase it."""

        if not self.legacy_database.exists():
            self.initialize()
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        archive = self.state_directory / "legacy-backups" / stamp
        archive.mkdir(parents=True, exist_ok=False)
        shutil.move(str(self.legacy_database), archive / self.legacy_database.name)
        for suffix in ("-wal", "-shm"):
            companion = Path(f"{self.legacy_database}{suffix}")
            if companion.exists():
                shutil.move(str(companion), archive / companion.name)
        self.initialize()
        return archive
