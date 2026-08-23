"""Execution identity and lifecycle for a running review graph."""

from __future__ import annotations

from dataclasses import dataclass

from archcompass.domain import Review
from archcompass.domain.errors import ReviewNotFoundError
from archcompass.persistence.sqlite.database import Transaction


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """Which lineage a run belongs to, as the row records it.

    Every identifier a review is filed under — the repository, the branch, the case — is
    known the moment a run begins, which is what lets a run be addressed as the next
    revision of that lineage long before there is a review to be one.
    """

    thread_id: str
    repository_id: str
    branch_id: str
    case_id: str


class SQLiteReviewExecutionRepository:
    """Execution identity and lifecycle, deliberately separate from review lineage."""

    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction
        with self._transaction() as connection:
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
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO review_executions(thread_id, repository_id, branch_id, "
                "case_id, status) VALUES (?, ?, ?, ?, 'running')",
                (thread_id, repository_id, branch_id, case_id),
            )

    def bind(self, thread_id: str, review: Review) -> None:
        with self._transaction() as connection:
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
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT thread_id FROM review_execution_aliases WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise ReviewNotFoundError(f"Review {review_id} has no resumable execution")
        return str(row[0])

    def current_review_id(self, thread_id: str) -> str | None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT current_review_id FROM review_executions WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if row is None:
            raise ReviewNotFoundError(f"Review execution {thread_id} was not found")
        return None if row[0] is None else str(row[0])

    def record(self, thread_id: str) -> ExecutionRecord | None:
        """The lineage this run belongs to, or `None` where no such run was started."""

        with self._transaction() as connection:
            row = connection.execute(
                "SELECT thread_id, repository_id, branch_id, case_id FROM review_executions "
                "WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return None if row is None else _record(row)

    def in_flight(self, *, limit: int = 50) -> tuple[ExecutionRecord, ...]:
        """Runs that have begun and are not finished, newest first.

        The one query the reviews listing needs and could not ask before. A run is only
        addressable while somebody is holding its id, so a reader who navigated away from
        the page that started it had no way back to it — and the run it names may take an
        hour, because that is what a batch takes.

        `status = 'running'` and nothing else. It used to also require `current_review_id
        IS NULL`, which read as "one row per thing" and behaved as a disappearance: a review
        is bound here as soon as the graph records one, which is several nodes before the run
        ends, so the run left the listing while it was still judging. A watcher then could
        not tell a run that had finished from a run that had never existed — the listing had
        the same answer for both — and the review it was waiting for was not in the reviews
        listing yet either.

        A run that has bound a review and is still working is therefore listed with that
        review's id on it, which is what a rejudgement after a clarification round looks
        like: the answers are being judged against the snapshot the reader is holding. A
        listing showing both keys them on the review id rather than showing two rows.

        `running` is only ever written by `begin` and `resume`, and every way out of a run
        writes something else over it, so this is "not finished" rather than a guess at it.

        No timestamp is stored, so the order is insertion order, which is start order.
        """

        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT thread_id, repository_id, branch_id, case_id FROM review_executions "
                "WHERE status = 'running' ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(_record(row) for row in rows)

    def status(self, thread_id: str) -> str:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT status FROM review_executions WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        if row is None:
            raise ReviewNotFoundError(f"Review execution {thread_id} was not found")
        return str(row[0])

    def resume(self, thread_id: str) -> None:
        """Put a waiting run back in flight, because rejudging answers is a run of its own.

        A review that asked a question left this row saying `awaiting_answers`, which was
        the truth right up to the moment somebody answered. What follows is minutes of
        judging on the same thread, and a row still claiming the review is waiting would
        keep that work out of every listing that asks what is running.
        """

        with self._transaction() as connection:
            connection.execute(
                "UPDATE review_executions SET status = 'running' WHERE thread_id = ?",
                (thread_id,),
            )

    def fail(self, thread_id: str) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE review_executions SET status = 'failed' WHERE thread_id = ?",
                (thread_id,),
            )

    def cancel(self, thread_id: str) -> None:
        """Record that somebody stopped this run, rather than that it broke.

        `cancelled` and not `failed`: a run that was stopped on purpose is not a run with a
        defect in it, and a reader who cannot tell those apart goes looking for a cause that
        does not exist. It is the same word the domain already uses for a review somebody
        stopped, and it is written here rather than nowhere so the id a person was handed
        still answers with what became of the work.
        """

        with self._transaction() as connection:
            connection.execute(
                "UPDATE review_executions SET status = 'cancelled' WHERE thread_id = ?",
                (thread_id,),
            )

    def abandon_running(self) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE review_executions SET status = 'failed' WHERE status = 'running'"
            )


def _record(row: tuple[object, ...]) -> ExecutionRecord:
    return ExecutionRecord(
        thread_id=str(row[0]),
        repository_id=str(row[1]),
        branch_id=str(row[2]),
        case_id=str(row[3]),
    )
