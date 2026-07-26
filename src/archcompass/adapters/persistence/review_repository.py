"""Immutable boundary-review persistence."""

from __future__ import annotations

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.stored_records import decode_stored_json
from archcompass.domain.errors import RunNotFoundError
from archcompass.domain.review import BoundaryReview
from archcompass.domain.workspace import BoundaryReviewSummary


class SQLiteBoundaryReviewRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, review: BoundaryReview) -> None:
        report = review.report
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO boundary_reviews(
                    review_id, case_id, case_revision, atlas_version_id, status,
                    reasoning_model, boundaries_reviewed, boundaries_material,
                    created_at, review_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    review.case_id,
                    review.case_revision,
                    review.atlas_version_id,
                    review.status.value,
                    review.reasoning_model,
                    0 if report is None else len(report.reviewed),
                    0 if report is None else len(report.material),
                    review.created_at.isoformat(),
                    review.model_dump_json(),
                ),
            )
            connection.commit()

    def get(self, review_id: str) -> BoundaryReview:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT review_json FROM boundary_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise RunNotFoundError(f"Boundary review {review_id} was not found")
        return decode_stored_json(
            BoundaryReview,
            row["review_json"],
            description=f"Boundary review {review_id}",
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
        query = """
            SELECT review_id, case_id, case_revision, atlas_version_id, status,
                   boundaries_reviewed, boundaries_material, created_at
            FROM boundary_reviews
        """
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
                boundaries_reviewed=int(row["boundaries_reviewed"]),
                boundaries_material=int(row["boundaries_material"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]
