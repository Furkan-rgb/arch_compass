"""Atomic commit of a successful run and its resulting case revision."""

from __future__ import annotations

from archcompass.adapters.persistence.case_repository import SQLiteCaseRepository
from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.run_repository import SQLiteRunRepository
from archcompass.domain.case import ArchitectureCase, CaseRevision
from archcompass.domain.consultation import ConsultationRun, ConsultationStatus
from archcompass.domain.errors import CaseRevisionConflictError, PersistenceError


class SQLiteConsultationCommitRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def commit_success(
        self,
        run: ConsultationRun,
        case: ArchitectureCase,
        *,
        expected_revision: int,
    ) -> CaseRevision:
        if run.status != ConsultationStatus.SUCCEEDED:
            raise PersistenceError("Only successful runs can update an architecture case")
        next_revision = expected_revision + 1
        snapshot = case.model_copy(update={"revision": next_revision})
        revision = CaseRevision(
            case_id=case.case_id,
            revision=next_revision,
            snapshot=snapshot,
            event_type="consultation",
            actor="archcompass",
            origin_run_id=run.run_id,
        )
        with self._database.connect() as connection:
            SQLiteRunRepository.insert(connection, run)
            cursor = connection.execute(
                """
                UPDATE cases SET current_revision = ?, updated_at = ?
                WHERE case_id = ? AND current_revision = ?
                """,
                (
                    next_revision,
                    snapshot.updated_at.isoformat(),
                    case.case_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise CaseRevisionConflictError(
                    f"Case {case.case_id} is not at expected revision {expected_revision}"
                )
            SQLiteCaseRepository.insert_revision(connection, revision)
            connection.commit()
        return revision

