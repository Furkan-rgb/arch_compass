"""Immutable review snapshots for the replacement workflow."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from archcompass.adapters.persistence.dataclass_records import DataclassRecordCodec
from archcompass.domain import (
    ArchitectureCase,
    CandidateId,
    Review,
    StandingDecision,
)
from archcompass.domain.errors import CaseNotFoundError, ReviewNotFoundError


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


class SQLiteCoreReviewRepository:
    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        self._codec = DataclassRecordCodec(Review)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_review_snapshots (
                    review_id TEXT PRIMARY KEY REFERENCES core_review_snapshots(review_id)
                        ON DELETE CASCADE,
                    repository_id TEXT NOT NULL,
                    branch_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    review_json TEXT NOT NULL,
                    UNIQUE(repository_id, branch_id, sequence)
                )
                """
            )

    def record(self, review: Review) -> Review:
        document = self._codec.encode(review)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO core_review_snapshots(
                    review_id, repository_id, branch_id, sequence, status, review_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_id) DO NOTHING
                """,
                (
                    review.id,
                    review.repository.id,
                    review.repository.branch_id,
                    review.sequence,
                    review.status.value,
                    document,
                ),
            )
            row = connection.execute(
                "SELECT review_json FROM core_review_snapshots WHERE review_id = ?",
                (review.id,),
            ).fetchone()
        assert row is not None
        return self._codec.decode(str(row[0]), description=f"Review {review.id}")

    def get(self, review_id: str) -> Review:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT review_json FROM core_review_snapshots WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise ReviewNotFoundError(f"Review {review_id} was not found")
        return self._codec.decode(str(row[0]), description=f"Review {review_id}")

    def latest_for_branch(self, branch_id: str) -> Review | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT review_json FROM core_review_snapshots "
                "WHERE branch_id = ? ORDER BY sequence DESC LIMIT 1",
                (branch_id,),
            ).fetchone()
        return (
            None
            if row is None
            else self._codec.decode(str(row[0]), description="Latest branch review")
        )

    def history_for_branch(self, branch_id: str) -> tuple[Review, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT review_json FROM core_review_snapshots "
                "WHERE branch_id = ? ORDER BY sequence DESC, review_id DESC",
                (branch_id,),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Branch review history")
            for row in rows
        )

    def list(self, *, limit: int = 100) -> tuple[Review, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT review_json FROM core_review_snapshots "
                "ORDER BY sequence DESC, review_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Stored review") for row in rows
        )

    def delete(self, review_id: str) -> None:
        # Review deletion is an explicit user operation. Provenance and checkpoints are
        # otherwise append-only and are never cleaned up as a side effect of startup.
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM core_review_snapshots WHERE review_id = ?", (review_id,)
            )
        if cursor.rowcount != 1:
            raise ReviewNotFoundError(f"Review {review_id} was not found")


class SQLiteReviewExecutionRepository:
    """Execution identity and lifecycle, deliberately separate from review lineage."""

    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_executions (
                    thread_id TEXT PRIMARY KEY,
                    current_review_id TEXT,
                    repository_id TEXT NOT NULL,
                    branch_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    UNIQUE(current_review_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_execution_aliases (
                    review_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL REFERENCES review_executions(thread_id)
                )
                """
            )

    def begin(
        self,
        *,
        thread_id: str,
        repository_id: str,
        branch_id: str,
        case_id: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO review_executions(thread_id, repository_id, branch_id, "
                "case_id, status) VALUES (?, ?, ?, ?, 'running')",
                (thread_id, repository_id, branch_id, case_id),
            )

    def bind(self, thread_id: str, review: Review) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE review_executions SET current_review_id = ?, status = ? "
                "WHERE thread_id = ?",
                (review.id, review.status.value, thread_id),
            )
            connection.execute(
                "INSERT INTO review_execution_aliases(review_id, thread_id) VALUES (?, ?) "
                "ON CONFLICT(review_id) DO NOTHING",
                (review.id, thread_id),
            )

    def thread_for_review(self, review_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT thread_id FROM review_execution_aliases WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise ReviewNotFoundError(f"Review {review_id} has no resumable execution")
        return str(row[0])

    def current_review_id(self, thread_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT current_review_id FROM review_executions WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if row is None:
            raise ReviewNotFoundError(f"Review execution {thread_id} was not found")
        return None if row[0] is None else str(row[0])

    def status(self, thread_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM review_executions WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        if row is None:
            raise ReviewNotFoundError(f"Review execution {thread_id} was not found")
        return str(row[0])

    def fail(self, thread_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE review_executions SET status = 'failed' WHERE thread_id = ?",
                (thread_id,),
            )

    def abandon_running(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE review_executions SET status = 'failed' WHERE status = 'running'"
            )


class SQLiteCoreStandingDecisionRepository:
    """Append-only human decisions keyed by branch and stable candidate identity."""

    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        self._codec = DataclassRecordCodec(StandingDecision)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_standing_decisions (
                    decision_id TEXT PRIMARY KEY,
                    branch_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    review_id TEXT NOT NULL REFERENCES core_review_snapshots(review_id)
                        ON DELETE CASCADE,
                    decision_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS core_decisions_branch_candidate "
                "ON core_standing_decisions(branch_id, candidate_id, decided_at)"
            )

    def record(self, decision: StandingDecision) -> StandingDecision:
        return self.record_many((decision,))[0]

    def record_many(
        self, decisions: tuple[StandingDecision, ...]
    ) -> tuple[StandingDecision, ...]:
        with self._connect() as connection:
            connection.executemany(
                "INSERT INTO core_standing_decisions(decision_id, branch_id, "
                "candidate_id, decided_at, review_id, decision_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                tuple(
                    (
                        decision.id,
                        decision.branch_id,
                        str(decision.candidate_id),
                        decision.decided_at.isoformat(),
                        decision.review_id,
                        self._codec.encode(decision),
                    )
                    for decision in decisions
                ),
            )
        return decisions

    def latest_for_branch(self, branch_id: str) -> tuple[StandingDecision, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT decision_json FROM core_standing_decisions AS decisions "
                "WHERE branch_id = ? AND decided_at = ("
                "SELECT MAX(decided_at) FROM core_standing_decisions "
                "WHERE branch_id = decisions.branch_id "
                "AND candidate_id = decisions.candidate_id) "
                "ORDER BY candidate_id",
                (branch_id,),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Standing decision")
            for row in rows
        )

    def history(
        self, branch_id: str, candidate_id: CandidateId
    ) -> tuple[StandingDecision, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT decision_json FROM core_standing_decisions "
                "WHERE branch_id = ? AND candidate_id = ? "
                "ORDER BY decided_at, decision_id",
                (branch_id, str(candidate_id)),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Standing decision history")
            for row in rows
        )
