"""Immutable review snapshots: several per revision, one of them current."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from archcompass.domain import Review
from archcompass.domain.errors import ReviewNotFoundError
from archcompass.persistence.sqlite.codecs import DataclassRecordCodec


class SQLiteCoreReviewRepository:
    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        self._codec = DataclassRecordCodec(Review)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_review_snapshots (
                    review_id TEXT PRIMARY KEY,
                    repository_id TEXT NOT NULL,
                    branch_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    round INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    review_json TEXT NOT NULL
                )
                """
            )

    def record(self, review: Review) -> Review:
        document = self._codec.encode(review)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO core_review_snapshots(
                    review_id, repository_id, branch_id, sequence, round, status,
                    review_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_id) DO NOTHING
                """,
                (
                    review.id,
                    review.repository.id,
                    review.repository.branch_id,
                    review.sequence,
                    review.round,
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

    #: The newest snapshot of each revision, and only that one.
    #:
    #: A revision is recorded more than once — each round it waited for an answer in, and
    #: the record it finished as — and the older ones are superseded rather than separate:
    #: a listing that showed them would show one review three times, under one number, with
    #: the last two saying it was still waiting. They stay readable by id, because a link
    #: somebody already holds must not stop working, and they stay out of every listing.
    #:
    #: `rowid` orders them because it is insertion order, which is exactly what "superseded"
    #: means here. Status cannot: a review can finish as completed, failed or cancelled.
    _NEWEST_PER_REVISION = (
        "snapshots.rowid = (SELECT MAX(newer.rowid) FROM core_review_snapshots AS newer "
        "WHERE newer.repository_id = snapshots.repository_id "
        "AND newer.branch_id = snapshots.branch_id "
        "AND newer.sequence = snapshots.sequence)"
    )

    def latest_for_branch(self, branch_id: str) -> Review | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT review_json FROM core_review_snapshots "
                "WHERE branch_id = ? ORDER BY sequence DESC, rowid DESC LIMIT 1",
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
                "SELECT snapshots.review_json FROM core_review_snapshots AS snapshots "
                f"WHERE snapshots.branch_id = ? AND {self._NEWEST_PER_REVISION} "
                "ORDER BY snapshots.sequence DESC",
                (branch_id,),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Branch review history")
            for row in rows
        )

    def list(self, *, limit: int = 100) -> tuple[Review, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT snapshots.review_json FROM core_review_snapshots AS snapshots "
                f"WHERE {self._NEWEST_PER_REVISION} "
                "ORDER BY snapshots.sequence DESC, snapshots.rowid DESC LIMIT ?",
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
