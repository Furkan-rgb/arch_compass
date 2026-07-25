"""Immutable consultation run persistence."""

from __future__ import annotations

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.stored_records import decode_stored_json
from archcompass.domain.consultation import ConsultationRun
from archcompass.domain.errors import RunNotFoundError
from archcompass.domain.workspace import RunSummary


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
            raise RunNotFoundError(f"Consultation run {run_id} was not found")
        return decode_stored_json(
            ConsultationRun,
            row["run_json"],
            description=f"Consultation run {run_id}",
        )

    def list(
        self,
        *,
        case_id: str | None = None,
        limit: int = 100,
    ) -> list[RunSummary]:
        query = (
            """
            SELECT run_json FROM consultation_runs
            WHERE case_id = ?
            ORDER BY completed_at DESC, run_id
            LIMIT ?
            """
            if case_id is not None
            else """
            SELECT run_json FROM consultation_runs
            ORDER BY completed_at DESC, run_id
            LIMIT ?
            """
        )
        parameters: tuple[object, ...] = (
            (case_id, limit) if case_id is not None else (limit,)
        )
        with self._database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        summaries: list[RunSummary] = []
        for row in rows:
            run = decode_stored_json(
                ConsultationRun,
                row["run_json"],
                description="A stored consultation run",
            )
            summaries.append(
                RunSummary(
                    run_id=run.run_id,
                    case_id=run.case_id,
                    status=run.status,
                    input_case_revision=run.input_case_revision,
                    result_case_revision=run.result_case_revision,
                    disposition=(run.report.disposition if run.report is not None else None),
                    failure_stage=run.failure_stage,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                )
            )
        return summaries

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
