"""SQLite persistence for queued consultation jobs and progress events."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import JsonValue

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.domain.errors import PersistenceError
from archcompass.domain.execution import (
    ConsultationJob,
    ConsultationJobStatus,
    ConsultationProgressEvent,
    ProgressEventType,
)


class SQLiteConsultationJobRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def create(self, job: ConsultationJob) -> ConsultationJob:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO consultation_jobs(
                    run_id, case_id, input_case_revision, repository_root,
                    status, current_stage, created_at, updated_at, started_at,
                    completed_at, warning, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._values(job),
            )
            connection.commit()
        return job

    def get(self, run_id: str) -> ConsultationJob:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM consultation_jobs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise PersistenceError(f"Consultation job {run_id} was not found")
        return self._row_to_job(row)

    def list(self, *, limit: int = 50) -> list[ConsultationJob]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM consultation_jobs
                ORDER BY created_at DESC, run_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def update(
        self,
        run_id: str,
        *,
        status: ConsultationJobStatus,
        current_stage: str | None = None,
        warning: str | None = None,
        error: str | None = None,
    ) -> ConsultationJob:
        current = self.get(run_id)
        now = datetime.now(UTC)
        started_at = (
            current.started_at
            if current.started_at is not None
            else (now if status == ConsultationJobStatus.RUNNING else None)
        )
        terminal = status in {
            ConsultationJobStatus.SUCCEEDED,
            ConsultationJobStatus.SUCCEEDED_WITH_WARNINGS,
            ConsultationJobStatus.FAILED,
            ConsultationJobStatus.INTERRUPTED,
        }
        updated = current.model_copy(
            update={
                "status": status,
                "current_stage": current_stage,
                "updated_at": now,
                "started_at": started_at,
                "completed_at": now if terminal else None,
                "warning": warning,
                "error": error,
            }
        )
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE consultation_jobs
                SET status = ?, current_stage = ?, updated_at = ?, started_at = ?,
                    completed_at = ?, warning = ?, error = ?
                WHERE run_id = ?
                """,
                (
                    updated.status,
                    updated.current_stage,
                    updated.updated_at.isoformat(),
                    (
                        updated.started_at.isoformat()
                        if updated.started_at is not None
                        else None
                    ),
                    (
                        updated.completed_at.isoformat()
                        if updated.completed_at is not None
                        else None
                    ),
                    updated.warning,
                    updated.error,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise PersistenceError(f"Consultation job {run_id} was not found")
            connection.commit()
        return updated

    def append_event(
        self,
        run_id: str,
        *,
        event_type: ProgressEventType,
        stage: str | None,
        title: str,
        summary: str = "",
        data: dict[str, JsonValue] | None = None,
    ) -> ConsultationProgressEvent:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS sequence
                FROM consultation_progress_events
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            sequence = int(row["sequence"]) + 1
            event = ConsultationProgressEvent(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                stage=stage,
                title=title,
                summary=summary,
                data=data or {},
            )
            connection.execute(
                """
                INSERT INTO consultation_progress_events(run_id, sequence, event_json)
                VALUES (?, ?, ?)
                """,
                (run_id, sequence, event.model_dump_json()),
            )
            connection.commit()
        return event

    def events(
        self, run_id: str, *, after_sequence: int = 0
    ) -> list[ConsultationProgressEvent]:
        self.get(run_id)
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT event_json FROM consultation_progress_events
                WHERE run_id = ? AND sequence > ?
                ORDER BY sequence
                """,
                (run_id, after_sequence),
            ).fetchall()
        return [
            ConsultationProgressEvent.model_validate_json(row["event_json"])
            for row in rows
        ]

    def interrupt_unfinished(self) -> int:
        unfinished = [
            job
            for job in self.list(limit=10000)
            if job.status
            in {ConsultationJobStatus.QUEUED, ConsultationJobStatus.RUNNING}
        ]
        for job in unfinished:
            self.update(
                job.run_id,
                status=ConsultationJobStatus.INTERRUPTED,
                current_stage=job.current_stage,
                error="The local web process stopped before this consultation completed.",
            )
            self.append_event(
                job.run_id,
                event_type=ProgressEventType.FAILED,
                stage=job.current_stage,
                title="Consultation interrupted",
                summary="Start a new consultation to run it again.",
            )
        return len(unfinished)

    @staticmethod
    def _values(job: ConsultationJob) -> tuple[object, ...]:
        return (
            job.run_id,
            job.case_id,
            job.input_case_revision,
            job.repository_root,
            job.status,
            job.current_stage,
            job.created_at.isoformat(),
            job.updated_at.isoformat(),
            job.started_at.isoformat() if job.started_at is not None else None,
            job.completed_at.isoformat() if job.completed_at is not None else None,
            job.warning,
            job.error,
        )

    @staticmethod
    def _row_to_job(row: object) -> ConsultationJob:
        return ConsultationJob(
            run_id=str(row["run_id"]),  # type: ignore[index]
            case_id=str(row["case_id"]),  # type: ignore[index]
            input_case_revision=int(row["input_case_revision"]),  # type: ignore[index]
            repository_root=row["repository_root"],  # type: ignore[index]
            status=row["status"],  # type: ignore[index]
            current_stage=row["current_stage"],  # type: ignore[index]
            created_at=datetime.fromisoformat(str(row["created_at"])),  # type: ignore[index]
            updated_at=datetime.fromisoformat(str(row["updated_at"])),  # type: ignore[index]
            started_at=(  # type: ignore[index]
                datetime.fromisoformat(str(row["started_at"]))  # type: ignore[index]
                if row["started_at"] is not None  # type: ignore[index]
                else None
            ),
            completed_at=(
                datetime.fromisoformat(str(row["completed_at"]))  # type: ignore[index]
                if row["completed_at"] is not None  # type: ignore[index]
                else None
            ),
            warning=row["warning"],  # type: ignore[index]
            error=row["error"],  # type: ignore[index]
        )
