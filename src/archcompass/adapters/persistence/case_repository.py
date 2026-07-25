"""Append-only SQLite architecture case repository."""

from __future__ import annotations

from datetime import datetime

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.stored_records import decode_stored_json
from archcompass.domain.case import ArchitectureCase, CaseRevision
from archcompass.domain.errors import CaseNotFoundError, CaseRevisionConflictError
from archcompass.domain.workspace import CaseSummary


class SQLiteCaseRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def create(self, case: ArchitectureCase, *, actor: str) -> CaseRevision:
        revision = CaseRevision(
            case_id=case.case_id,
            revision=1,
            snapshot=case.model_copy(update={"revision": 1}),
            event_type="created",
            actor=actor,
        )
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO cases(case_id, current_revision, created_at, updated_at)
                VALUES (?, 1, ?, ?)
                """,
                (case.case_id, case.created_at.isoformat(), case.updated_at.isoformat()),
            )
            self.insert_revision(connection, revision)
            connection.commit()
        return revision

    def get(self, case_id: str, revision: int | None = None) -> CaseRevision:
        with self._database.connect() as connection:
            if revision is None:
                row = connection.execute(
                    """
                    SELECT revision, event_type, actor, origin_run_id, created_at, snapshot_json
                    FROM case_revisions
                    WHERE case_id = ?
                    ORDER BY revision DESC LIMIT 1
                    """,
                    (case_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT revision, event_type, actor, origin_run_id, created_at, snapshot_json
                    FROM case_revisions WHERE case_id = ? AND revision = ?
                    """,
                    (case_id, revision),
                ).fetchone()
        if row is None:
            suffix = "" if revision is None else f" revision {revision}"
            raise CaseNotFoundError(f"Architecture case {case_id}{suffix} was not found")
        return self._row_to_revision(case_id, row)

    def append(
        self,
        case: ArchitectureCase,
        *,
        expected_revision: int,
        event_type: str,
        actor: str,
        origin_run_id: str | None = None,
    ) -> CaseRevision:
        next_revision = expected_revision + 1
        snapshot = case.model_copy(update={"revision": next_revision})
        revision = CaseRevision(
            case_id=case.case_id,
            revision=next_revision,
            snapshot=snapshot,
            event_type=event_type,  # type: ignore[arg-type]
            actor=actor,
            origin_run_id=origin_run_id,
        )
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE cases
                SET current_revision = ?, updated_at = ?
                WHERE case_id = ? AND current_revision = ?
                """,
                (next_revision, snapshot.updated_at.isoformat(), case.case_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise CaseRevisionConflictError(
                    f"Case {case.case_id} is not at expected revision {expected_revision}"
                )
            self.insert_revision(connection, revision)
            connection.commit()
        return revision

    def history(self, case_id: str) -> list[CaseRevision]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT revision, event_type, actor, origin_run_id, created_at, snapshot_json
                FROM case_revisions WHERE case_id = ? ORDER BY revision
                """,
                (case_id,),
            ).fetchall()
        if not rows:
            raise CaseNotFoundError(f"Architecture case {case_id} was not found")
        return [self._row_to_revision(case_id, row) for row in rows]

    def list(self, *, limit: int = 100) -> list[CaseSummary]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT r.case_id, r.revision, r.snapshot_json
                FROM case_revisions r
                JOIN cases c
                  ON c.case_id = r.case_id
                 AND c.current_revision = r.revision
                ORDER BY c.updated_at DESC, r.case_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        summaries: list[CaseSummary] = []
        for row in rows:
            snapshot = decode_stored_json(
                ArchitectureCase,
                row["snapshot_json"],
                description="A stored case revision",
            )
            summaries.append(
                CaseSummary(
                    case_id=snapshot.case_id,
                    revision=int(row["revision"]),
                    title=snapshot.title,
                    problem_statement=snapshot.problem_statement,
                    repository_root=(
                        snapshot.repository.root_path if snapshot.repository is not None else None
                    ),
                    current_recommendation=snapshot.current_recommendation,
                    confidence=snapshot.confidence,
                    updated_at=snapshot.updated_at,
                )
            )
        return summaries

    @staticmethod
    def insert_revision(connection: object, revision: CaseRevision) -> None:
        connection.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO case_revisions(
                case_id, revision, event_type, actor, origin_run_id, created_at, snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision.case_id,
                revision.revision,
                revision.event_type,
                revision.actor,
                revision.origin_run_id,
                revision.created_at.isoformat(),
                revision.snapshot.model_dump_json(),
            ),
        )

    @staticmethod
    def _row_to_revision(case_id: str, row: object) -> CaseRevision:
        return CaseRevision(
            case_id=case_id,
            revision=int(row["revision"]),  # type: ignore[index]
            snapshot=ArchitectureCase.model_validate_json(row["snapshot_json"]),  # type: ignore[index]
            event_type=row["event_type"],  # type: ignore[index]
            actor=row["actor"],  # type: ignore[index]
            origin_run_id=row["origin_run_id"],  # type: ignore[index]
            created_at=datetime.fromisoformat(row["created_at"]),  # type: ignore[index]
        )
