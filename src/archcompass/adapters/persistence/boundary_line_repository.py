"""The ledger of what happened to boundaries' lines: one append-only table, no updates.

Every write is an insert and nothing here issues an UPDATE or a DELETE, for the reason
migration 029 states: this is an account of something that happened, and an account that can
be rewritten is not evidence of anything. A closure that turns out to have been premature is
answered by appending the resurrection, never by removing the closure.

Reading is where the work is, and there is exactly one question: what is the latest thing
that happened to this line. `recorded_at` is an ISO string with millisecond resolution, so
`rowid` breaks the tie — a closure and a resurrection written in the same tick still have an
order, and the same order every time it is asked.
"""

from __future__ import annotations

from collections.abc import Iterable

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.stored_records import decode_stored_json
from archcompass.domain.delta import BoundaryLineEvent

_REMEDY = (
    "A line event is what one revision observed, and only another revision can produce it. "
    "Run the review again to have the comparison made afresh."
)

#: How many fingerprints go into one `IN (...)` clause. SQLite's default parameter ceiling is
#: 999 and a revision on a large repository can carry more boundaries than that, so the read
#: is chunked rather than left to fail on the repository that finally exceeds it.
_MAX_PARAMETERS = 800


class SQLiteBoundaryLineRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def append_all(self, events: Iterable[BoundaryLineEvent]) -> int:
        """Record everything one revision observed about the lines, in one transaction.

        All of it or none of it: a revision that recorded its closures and then failed before
        its successions would leave a line reported as addressed when the run had in fact
        matched a successor for it, which is precisely the silent loss this table exists to
        prevent.
        """

        rows = [
            (
                event.event_id,
                event.branch_id,
                event.boundary_fingerprint,
                event.event.value,
                event.review_id,
                event.successor_fingerprint,
                event.recorded_at.isoformat(),
                event.model_dump_json(),
            )
            for event in events
        ]
        if not rows:
            return 0
        with self._database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO boundary_lines(
                    event_id, branch_id, boundary_fingerprint, event, review_id,
                    successor_fingerprint, recorded_at, event_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.commit()
        return len(rows)

    def latest_for(
        self, branch_id: str, fingerprints: Iterable[str]
    ) -> dict[str, BoundaryLineEvent]:
        """The most recent event per fingerprint, for the ones that have any.

        Asked once per revision about every boundary it detected, which is why it takes a set
        rather than a fingerprint: the question is "has any of these been here before and
        closed", and asking it forty times would be forty round trips to answer one.

        A fingerprint with no history is absent rather than mapped to `None`. Absence is the
        ordinary state — most boundaries have never moved and never gone — and a key present
        with nothing behind it would be a claim that something was looked up and found empty.
        """

        wanted = sorted(set(fingerprints))
        if not wanted:
            return {}
        latest: dict[str, BoundaryLineEvent] = {}
        with self._database.connect() as connection:
            for start in range(0, len(wanted), _MAX_PARAMETERS):
                chunk = wanted[start : start + _MAX_PARAMETERS]
                placeholders = ", ".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""
                    SELECT boundary_fingerprint, event_json FROM boundary_lines AS outer_event
                    WHERE branch_id = ?
                      AND boundary_fingerprint IN ({placeholders})
                      AND rowid = (
                          SELECT inner_event.rowid FROM boundary_lines AS inner_event
                          WHERE inner_event.branch_id = outer_event.branch_id
                            AND inner_event.boundary_fingerprint
                                = outer_event.boundary_fingerprint
                          ORDER BY inner_event.recorded_at DESC, inner_event.rowid DESC
                          LIMIT 1
                      )
                    """,
                    (branch_id, *chunk),
                ).fetchall()
                for row in rows:
                    latest[str(row["boundary_fingerprint"])] = self._event(
                        str(row["event_json"])
                    )
        return latest

    def history(self, branch_id: str, boundary_fingerprint: str) -> list[BoundaryLineEvent]:
        """Everything that ever happened to this line, oldest first.

        Oldest first because it reads as a story: succeeded here, addressed there, back now.
        """

        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT event_json FROM boundary_lines
                WHERE branch_id = ? AND boundary_fingerprint = ?
                ORDER BY recorded_at, rowid
                """,
                (branch_id, boundary_fingerprint),
            ).fetchall()
        return [self._event(str(row["event_json"])) for row in rows]

    @staticmethod
    def _event(document: str) -> BoundaryLineEvent:
        return decode_stored_json(
            BoundaryLineEvent,
            document,
            description="A stored boundary line event",
            remedy=_REMEDY,
        )
