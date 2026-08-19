"""Case snapshots, stored one row per revision and never rewritten."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from archcompass.domain import ArchitectureCase
from archcompass.domain.errors import CaseNotFoundError
from archcompass.persistence.sqlite.codecs import DataclassRecordCodec


class SQLiteCoreCaseRepository:
    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        self._codec = DataclassRecordCodec(ArchitectureCase)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_case_snapshots (
                    case_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    case_json TEXT NOT NULL,
                    PRIMARY KEY(case_id, revision)
                )
                """
            )

    def record(self, case: ArchitectureCase) -> ArchitectureCase:
        document = self._codec.encode(case)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO core_case_snapshots(case_id, revision, case_json) "
                "VALUES (?, ?, ?) ON CONFLICT(case_id, revision) DO NOTHING",
                (case.id, case.revision, document),
            )
            row = connection.execute(
                "SELECT case_json FROM core_case_snapshots "
                "WHERE case_id = ? AND revision = ?",
                (case.id, case.revision),
            ).fetchone()
        assert row is not None
        return self._codec.decode(str(row[0]), description=f"Case {case.id}")

    def get(self, case_id: str, revision: int | None = None) -> ArchitectureCase:
        query = "SELECT case_json FROM core_case_snapshots WHERE case_id = ?"
        parameters: tuple[object, ...] = (case_id,)
        if revision is None:
            query += " ORDER BY revision DESC LIMIT 1"
        else:
            query += " AND revision = ?"
            parameters = (case_id, revision)
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        if row is None:
            raise CaseNotFoundError(f"Architecture case {case_id} was not found")
        return self._codec.decode(str(row[0]), description=f"Case {case_id}")

    def history(self, case_id: str) -> tuple[ArchitectureCase, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT case_json FROM core_case_snapshots WHERE case_id = ? "
                "ORDER BY revision",
                (case_id,),
            ).fetchall()
        if not rows:
            raise CaseNotFoundError(f"Architecture case {case_id} was not found")
        return tuple(
            self._codec.decode(str(row[0]), description=f"Case {case_id}")
            for row in rows
        )

    def list(self, *, limit: int = 100) -> tuple[ArchitectureCase, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT snapshots.case_json FROM core_case_snapshots AS snapshots "
                "JOIN (SELECT case_id, MAX(revision) AS revision "
                "FROM core_case_snapshots GROUP BY case_id) AS latest "
                "ON snapshots.case_id = latest.case_id "
                "AND snapshots.revision = latest.revision "
                "ORDER BY snapshots.case_id LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Stored case") for row in rows
        )
