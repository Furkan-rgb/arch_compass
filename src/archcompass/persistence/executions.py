"""Execution identity and lifecycle for a running review graph."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from archcompass.domain import Review
from archcompass.domain.errors import ReviewNotFoundError


@dataclass(frozen=True, slots=True)
class InFlightExecution:
    """A run that has started and has no review yet, as the row records it."""

    thread_id: str
    repository_id: str
    branch_id: str
    case_id: str


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

    def in_flight(self, *, limit: int = 50) -> tuple[InFlightExecution, ...]:
        """Runs that have begun and have not yet produced a review, newest first.

        The one query the reviews listing needs and could not ask before. A run is only
        addressable while somebody is holding its id, so a reader who navigated away from
        the page that started it had no way back to it — and the run it names may take an
        hour, because that is what a batch takes.

        `current_review_id IS NULL` rather than `status = 'running'` alone, because a review
        composed mid-run is bound here the moment it exists: from then on the run is a review
        and belongs in the listing as one, not twice.

        No timestamp is stored, so the order is insertion order, which is start order.
        """

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT thread_id, repository_id, branch_id, case_id FROM review_executions "
                "WHERE status = 'running' AND current_review_id IS NULL "
                "ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(
            InFlightExecution(
                thread_id=str(row[0]),
                repository_id=str(row[1]),
                branch_id=str(row[2]),
                case_id=str(row[3]),
            )
            for row in rows
        )

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
