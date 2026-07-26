"""Boundary-review persistence: written once, but present from the moment a run starts."""

from __future__ import annotations

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.stored_records import decode_stored_json
from archcompass.domain.base import utc_now
from archcompass.domain.errors import ReviewNotFoundError, ReviewStillRunningError
from archcompass.domain.review import BoundaryReview, ReviewStatus
from archcompass.domain.workspace import BoundaryReviewSummary

_LISTING_COLUMNS = """
    review_id, case_id, case_revision, atlas_version_id, status,
    boundaries_detected, boundaries_reviewed, boundaries_material,
    created_at, updated_at, case_title
"""


class SQLiteBoundaryReviewRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def begin(self, review: BoundaryReview) -> None:
        """Record a run that has started, before it can say anything about its outcome.

        Written after the case, the atlas and its freshness are settled, so the row's
        foreign keys are already true and a review that exists is one that could run. What
        it cannot yet say is how much there is to do: detection has not happened, and
        `boundaries_detected` stays null rather than claiming zero.
        """

        now = review.created_at.isoformat()
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO boundary_reviews(
                    review_id, case_id, case_revision, atlas_version_id, status,
                    reasoning_model, boundaries_detected, boundaries_reviewed,
                    boundaries_material, created_at, updated_at, case_title, review_json
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 0, 0, ?, ?, NULL, ?)
                """,
                (
                    review.review_id,
                    review.case_id,
                    review.case_revision,
                    review.atlas_version_id,
                    review.status.value,
                    review.reasoning_model,
                    now,
                    now,
                    review.model_dump_json(),
                ),
            )
            connection.commit()

    def record_progress(
        self,
        review_id: str,
        *,
        detected: int | None = None,
        reviewed: int | None = None,
        material: int | None = None,
    ) -> None:
        """Move the counts a running review reports, leaving the ones not supplied alone.

        Columns rather than the stored document: a listing reads columns, and rewriting the
        whole review once per model call to move an integer would make watching a run cost
        more than running it.
        """

        assignments = ["updated_at = ?"]
        values: list[object] = [utc_now().isoformat()]
        for column, value in (
            ("boundaries_detected", detected),
            ("boundaries_reviewed", reviewed),
            ("boundaries_material", material),
        ):
            if value is not None:
                assignments.append(f"{column} = ?")
                values.append(value)
        values.append(review_id)
        with self._database.connect() as connection:
            connection.execute(
                f"UPDATE boundary_reviews SET {', '.join(assignments)} WHERE review_id = ?",
                tuple(values),
            )
            connection.commit()

    def complete(self, review: BoundaryReview) -> None:
        """Write the judgement, exactly once, over the row the run has been holding.

        Unconditional on the current status. A run that was reported abandoned because the
        workspace restarted under it may still be alive in another process, and the process
        that did the work is the one entitled to say how it ended.
        """

        report = review.report
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE boundary_reviews
                SET status = ?, reasoning_model = ?, boundaries_detected = ?,
                    boundaries_reviewed = ?, boundaries_material = ?, updated_at = ?,
                    case_title = ?, review_json = ?
                WHERE review_id = ?
                """,
                (
                    review.status.value,
                    review.reasoning_model,
                    0 if report is None else len(report.reviewed),
                    0 if report is None else len(report.reviewed),
                    0 if report is None else len(report.material),
                    utc_now().isoformat(),
                    None if report is None else report.case_title,
                    review.model_dump_json(),
                    review.review_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ReviewNotFoundError(
                    f"Boundary review {review.review_id} was not begun before completing"
                )
            connection.commit()

    def cancel(self, review_id: str) -> bool:
        """Mark a running review cancelled, and say whether there was one to mark.

        The record is what stops the run: there is no channel to the thread doing the work,
        and inventing one would mean shared mutable state outliving the request that owns
        it. The run reads this row between model calls, so cancelling takes effect within
        one call rather than immediately — which is also why it is guarded on `running`. A
        review that finished a moment ago is a review that finished.
        """

        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT review_json FROM boundary_reviews "
                "WHERE review_id = ? AND status = 'running'",
                (review_id,),
            ).fetchone()
            if row is None:
                return False
            document = row["review_json"]
            try:
                stored = BoundaryReview.model_validate_json(document)
            except ValueError:
                pass
            else:
                document = stored.model_copy(
                    update={"status": ReviewStatus.CANCELLED, "report": None}
                ).model_dump_json()
            connection.execute(
                """
                UPDATE boundary_reviews
                SET status = 'cancelled', updated_at = ?, review_json = ?
                WHERE review_id = ? AND status = 'running'
                """,
                (utc_now().isoformat(), document, review_id),
            )
            connection.commit()
        return True

    def is_running(self, review_id: str) -> bool:
        """Whether the run may continue. One small read between model calls."""

        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM boundary_reviews WHERE review_id = ? AND status = 'running'",
                (review_id,),
            ).fetchone()
        return row is not None

    def delete(self, review_id: str) -> None:
        """Remove a review and the question threads hung off it.

        Immutability is about not rewriting what a review said, which deletion does not do:
        it removes the record entirely rather than leaving one that says something else. The
        threads go with it — a thread whose review is gone has nothing to be about, and
        every answer in it cited boundaries that no longer exist.
        """

        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT status FROM boundary_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()
            if row is None:
                raise ReviewNotFoundError(f"Boundary review {review_id} was not found")
            if str(row["status"]) == ReviewStatus.RUNNING.value:
                # Deleting the row a live run is holding would have that run fail on its own
                # record when it tries to finish. Cancelling first is one click, and it is
                # the honest order: stop the work, then remove what it produced.
                raise ReviewStillRunningError(
                    f"Boundary review {review_id} is still running. Cancel it first, then "
                    "delete it."
                )
            connection.execute(
                "DELETE FROM review_conversations WHERE review_id = ?", (review_id,)
            )
            connection.execute(
                "DELETE FROM boundary_reviews WHERE review_id = ?", (review_id,)
            )
            connection.commit()

    def abandon_running(self, *, reason: str) -> int:
        """Report runs left behind by a workspace that stopped, and say how many.

        A run lives inside the request or command that started it and cannot outlive its
        process, so a row still marked running when the workspace starts belongs to a
        process that is gone. Rows are marked rather than deleted: the reader asked for that
        review and deserves to be told what happened to it.

        This can be wrong exactly once — a review running in another process at this
        moment is marked too — and that mistake corrects itself, because `complete` writes
        the real outcome over it when the run finishes.
        """

        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT review_id, review_json FROM boundary_reviews WHERE status = 'running'"
            ).fetchall()
            for row in rows:
                review_id = str(row["review_id"])
                # Rewritten from the row's own document, so the review keeps the case, atlas
                # and model it named and stays openable. A document an older schema wrote is
                # left as it is: the status still moves, and the row already reports itself
                # as unreadable when someone opens it.
                document = row["review_json"]
                try:
                    stored = BoundaryReview.model_validate_json(document)
                except ValueError:
                    pass
                else:
                    document = stored.model_copy(
                        update={
                            "status": ReviewStatus.FAILED,
                            "report": None,
                            "sanitized_errors": [*stored.sanitized_errors, reason],
                        }
                    ).model_dump_json()
                connection.execute(
                    """
                    UPDATE boundary_reviews
                    SET status = 'failed', updated_at = ?, review_json = ?
                    WHERE review_id = ? AND status = 'running'
                    """,
                    (utc_now().isoformat(), document, review_id),
                )
            connection.commit()
        return len(rows)

    def get(self, review_id: str) -> BoundaryReview:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT review_json FROM boundary_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise ReviewNotFoundError(f"Boundary review {review_id} was not found")
        return decode_stored_json(
            BoundaryReview,
            row["review_json"],
            description=f"Boundary review {review_id}",
            remedy=(
                "A review is derived from a case and an atlas, so run the review again "
                "from the case it names."
            ),
        )

    def list(
        self,
        *,
        case_id: str | None = None,
        limit: int = 100,
    ) -> list[BoundaryReviewSummary]:
        # Counts are read from their own columns rather than from the decoded document:
        # a listing is the one place that must stay cheap as reviews accumulate, and the
        # columns exist precisely so it does not have to parse every stored report.
        query = f"SELECT {_LISTING_COLUMNS} FROM boundary_reviews"
        parameters: tuple[object, ...]
        if case_id is not None:
            query += " WHERE case_id = ?"
            parameters = (case_id, limit)
        else:
            parameters = (limit,)
        query += " ORDER BY created_at DESC, review_id LIMIT ?"
        with self._database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            BoundaryReviewSummary(
                review_id=str(row["review_id"]),
                case_id=str(row["case_id"]),
                case_revision=int(row["case_revision"]),
                atlas_version_id=str(row["atlas_version_id"]),
                status=str(row["status"]),
                boundaries_detected=(
                    None
                    if row["boundaries_detected"] is None
                    else int(row["boundaries_detected"])
                ),
                boundaries_reviewed=int(row["boundaries_reviewed"]),
                boundaries_material=int(row["boundaries_material"]),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
                case_title=(None if row["case_title"] is None else str(row["case_title"])),
            )
            for row in rows
        ]
