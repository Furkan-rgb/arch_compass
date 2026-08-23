"""Immutable review snapshots: several per revision, one of them current."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from archcompass.domain import RepositoryRef, Review
from archcompass.domain.errors import ReviewNotFoundError
from archcompass.persistence.sqlite.codecs import DataclassRecordCodec
from archcompass.persistence.sqlite.database import Transaction


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    """One review as a listing reads it, assembled without opening the review.

    A listing shows a handful of facts about a review, and a stored review is most of a
    repository's atlas — several megabytes of it. Listing a hundred used to decode a
    hundred of those documents into a full object graph so that five integers could be
    counted off it, which is the same work as opening every review at once and then
    throwing all of them away.

    So this is read out of the stored document by SQLite: the columns where there is a
    column, `json_extract` and `json_each` where there is not, and the blob never enters
    Python at all. `repository` is the real domain record because every field of it is one
    `json_extract` away and a listing already knows how to render one.

    Deliberately not a `Review` with the expensive fields left empty. A record that says it
    is a review and has no findings would eventually be handed to something that needs
    them, and would answer that there are none.
    """

    id: str
    sequence: int
    round: int
    status: str
    repository: RepositoryRef
    case_id: str
    case_revision: int
    started_at: datetime
    finished_at: datetime | None = None
    previous_review_id: str | None = None
    #: How many questions this review's case has answers on. A revision number says which
    #: case a run will continue and not how much is in it, and "continues revision 4" with no
    #: second number is the same sentence for a case somebody has filled in and one that was
    #: opened and never answered.
    answer_count: int = 0
    finding_count: int = 0
    material_count: int = 0
    held_count: int = 0
    cleared_count: int = 0
    question_count: int = 0
    unchanged_count: int = 0
    changed_count: int = 0
    new_count: int = 0
    addressed_count: int = 0


class SQLiteCoreReviewRepository:
    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction
        self._codec = DataclassRecordCodec(Review)
        with self._transaction() as connection:
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
        with self._transaction() as connection:
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

    def sequence_of(self, review_id: str) -> int | None:
        """The number one review carries, without decoding the review to find it.

        It is a column, and reading it as one matters more than it looks. The run endpoint
        wants this integer and nothing else, and it was getting it by decoding the whole
        stored document — which on a review of a real repository is megabytes of JSON, on
        every poll of a run somebody is watching. That decode is most of what made the POST
        that answers a clarification round miss a thirty-second deadline.
        """

        with self._transaction() as connection:
            row = connection.execute(
                "SELECT sequence FROM core_review_snapshots WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        return None if row is None else int(row[0])

    def get(self, review_id: str) -> Review:
        with self._transaction() as connection:
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
        with self._transaction() as connection:
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
        with self._transaction() as connection:
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
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT snapshots.review_json FROM core_review_snapshots AS snapshots "
                f"WHERE {self._NEWEST_PER_REVISION} "
                "ORDER BY snapshots.sequence DESC, snapshots.rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Stored review") for row in rows
        )

    #: Everything a listing shows, read off the stored document without decoding it.
    #:
    #: Four of the values are columns and the rest are `json_extract`, which parses the
    #: document — so the calls are kept to what a listing genuinely reads, and the verdict
    #: tally is one `json_each` per verdict rather than a scan per finding. SQLite keeps a
    #: small cache of recently parsed JSON, and every call in one row is over the same text,
    #: so the row costs about one parse rather than one per column.
    _SUMMARY_COLUMNS = """
        snapshots.review_id,
        snapshots.sequence,
        snapshots.round,
        snapshots.status,
        json_extract(snapshots.review_json, '$.repository.id'),
        json_extract(snapshots.review_json, '$.repository.path'),
        snapshots.branch_id,
        json_extract(snapshots.review_json, '$.repository.content_id'),
        json_extract(snapshots.review_json, '$.repository.remote_url'),
        json_extract(snapshots.review_json, '$.repository.branch'),
        json_extract(snapshots.review_json, '$.repository.commit'),
        json_extract(snapshots.review_json, '$.case.id'),
        json_extract(snapshots.review_json, '$.case.revision'),
        json_extract(snapshots.review_json, '$.started_at'),
        json_extract(snapshots.review_json, '$.finished_at'),
        json_extract(snapshots.review_json, '$.previous_review_id'),
        json_array_length(snapshots.review_json, '$.case.answers'),
        json_array_length(snapshots.review_json, '$.findings'),
        (SELECT COUNT(*) FROM json_each(snapshots.review_json, '$.findings')
            WHERE json_extract(json_each.value, '$.verdict') = 'material'),
        (SELECT COUNT(*) FROM json_each(snapshots.review_json, '$.findings')
            WHERE json_extract(json_each.value, '$.verdict') = 'held'),
        (SELECT COUNT(*) FROM json_each(snapshots.review_json, '$.findings')
            WHERE json_extract(json_each.value, '$.verdict') = 'cleared'),
        json_array_length(snapshots.review_json, '$.questions'),
        json_array_length(snapshots.review_json, '$.delta.unchanged'),
        json_array_length(snapshots.review_json, '$.delta.changed'),
        json_array_length(snapshots.review_json, '$.delta.new'),
        json_array_length(snapshots.review_json, '$.delta.addressed')
    """

    def list_summaries(self, *, limit: int = 100) -> tuple[ReviewSummary, ...]:
        """The same reviews `list` returns, projected rather than decoded.

        Same rows and same order as `list`, so a caller can move between the two without
        the listing changing under it.
        """

        with self._transaction() as connection:
            rows = connection.execute(
                f"SELECT {self._SUMMARY_COLUMNS} "
                "FROM core_review_snapshots AS snapshots "
                f"WHERE {self._NEWEST_PER_REVISION} "
                "ORDER BY snapshots.sequence DESC, snapshots.rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(_summary(row) for row in rows)

    def delete(self, review_id: str) -> None:
        # Review deletion is an explicit user operation. Provenance and checkpoints are
        # otherwise append-only and are never cleaned up as a side effect of startup.
        with self._transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM core_review_snapshots WHERE review_id = ?", (review_id,)
            )
        if cursor.rowcount != 1:
            raise ReviewNotFoundError(f"Review {review_id} was not found")


def _moment(value: object) -> datetime | None:
    """One stored timestamp back as a datetime, so a summary reads like a review.

    The document holds what Pydantic wrote — `2026-01-01T00:00:00Z` — and everything that
    reads a review reads `datetime`. Parsing here rather than passing the string on keeps
    the two listings saying the same thing about the same review.
    """

    return None if value is None else datetime.fromisoformat(str(value))


def _summary(row: tuple[object, ...]) -> ReviewSummary:
    started = _moment(row[13])
    assert started is not None  # A stored review always has a start; the column is not null.
    return ReviewSummary(
        id=str(row[0]),
        sequence=int(str(row[1])),
        round=int(str(row[2])),
        status=str(row[3]),
        repository=RepositoryRef(
            id=str(row[4]),
            path=Path(str(row[5])),
            branch_id=str(row[6]),
            content_id=str(row[7]),
            remote_url=None if row[8] is None else str(row[8]),
            branch=None if row[9] is None else str(row[9]),
            commit=None if row[10] is None else str(row[10]),
        ),
        case_id=str(row[11]),
        case_revision=int(str(row[12])),
        started_at=started,
        finished_at=_moment(row[14]),
        previous_review_id=None if row[15] is None else str(row[15]),
        answer_count=int(str(row[16])),
        finding_count=int(str(row[17])),
        material_count=int(str(row[18])),
        held_count=int(str(row[19])),
        cleared_count=int(str(row[20])),
        question_count=int(str(row[21])),
        unchanged_count=int(str(row[22])),
        changed_count=int(str(row[23])),
        new_count=int(str(row[24])),
        addressed_count=int(str(row[25])),
    )
