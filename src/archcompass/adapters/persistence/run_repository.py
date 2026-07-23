"""Immutable consultation run persistence."""

from __future__ import annotations

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.domain.consultation import ConsultationRun
from archcompass.domain.errors import PersistenceError


class SQLiteRunRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, run: ConsultationRun) -> None:
        with self._database.connect() as connection:
            self.insert(connection, run)
            connection.commit()

    def get(self, run_id: str) -> ConsultationRun:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT run_json FROM consultation_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise PersistenceError(f"Consultation run {run_id} was not found")
        return ConsultationRun.model_validate_json(row["run_json"])

    @staticmethod
    def insert(connection: object, run: ConsultationRun) -> None:
        connection.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO consultation_runs(
                run_id, case_id, input_case_revision, status, completed_at, run_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.case_id,
                run.input_case_revision,
                run.status,
                run.completed_at.isoformat(),
                run.model_dump_json(),
            ),
        )
