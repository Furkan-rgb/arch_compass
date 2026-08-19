"""Immutable review snapshots for the replacement workflow."""

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
