"""Standing-decision and discussion persistence: two append-only tables, no updates.

Both writes are inserts and nothing here issues an UPDATE or a DELETE. A decision that
changed by overwrite would destroy the record that it changed, which is the record a reader
came for; a comment that could be edited would make the thread a draft rather than a history.

Reading is where the work is. "What does this branch currently think" is the latest decision
per fingerprint — latest `decided_at`, tie-broken by `rowid` so two writes inside one clock
tick still have an order, and the same order every time it is asked.
"""

from __future__ import annotations

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.stored_records import decode_stored_json
from archcompass.domain.triage import DecisionComment, StandingDecision

_DECISION_REMEDY = (
    "A decision is what somebody judged, and nothing can produce it again. Record the "
    "disposition for that boundary once more."
)

_COMMENT_REMEDY = (
    "A comment is what somebody wrote, and nothing can produce it again. Post it again if "
    "it still matters."
)

#: The current decision per boundary on one branch. `rowid` breaks the tie because
#: `decided_at` is an ISO string with millisecond resolution and two decisions on the same
#: boundary in the same tick are exactly the case where getting it wrong would show the
#: reader a disposition their colleague had already replaced.
_CURRENT_PER_BOUNDARY = """
    SELECT decision_json FROM standing_decisions AS outer_decision
    WHERE branch_id = ?
      AND rowid = (
          SELECT inner_decision.rowid FROM standing_decisions AS inner_decision
          WHERE inner_decision.branch_id = outer_decision.branch_id
            AND inner_decision.boundary_fingerprint = outer_decision.boundary_fingerprint
          ORDER BY inner_decision.decided_at DESC, inner_decision.rowid DESC
          LIMIT 1
      )
    ORDER BY boundary_fingerprint
"""


class SQLiteStandingDecisionRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def append_decision(self, decision: StandingDecision) -> StandingDecision:
        """Record one disposition. Never replaces the one before it."""

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO standing_decisions(
                    decision_id, branch_id, boundary_fingerprint, state, author, reason,
                    decided_at, review_id, boundary_reference, material, verdict_label,
                    decision_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.branch_id,
                    decision.boundary_fingerprint,
                    decision.state.value,
                    decision.author,
                    decision.reason,
                    decision.decided_at.isoformat(),
                    decision.review_id,
                    decision.boundary_reference,
                    int(decision.material),
                    decision.verdict_label,
                    decision.model_dump_json(),
                ),
            )
            connection.commit()
        return decision

    def current_for_branch(self, branch_id: str) -> list[StandingDecision]:
        """What this branch currently thinks, one decision per boundary it has an opinion on.

        Boundaries nobody has decided about are simply absent — the unreviewed state is
        absence, so there is nothing here to filter out.
        """

        with self._database.connect() as connection:
            rows = connection.execute(_CURRENT_PER_BOUNDARY, (branch_id,)).fetchall()
        return [self._decision(str(row["decision_json"])) for row in rows]

    def current_for(self, branch_id: str, boundary_fingerprint: str) -> StandingDecision | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT decision_json FROM standing_decisions
                WHERE branch_id = ? AND boundary_fingerprint = ?
                ORDER BY decided_at DESC, rowid DESC
                LIMIT 1
                """,
                (branch_id, boundary_fingerprint),
            ).fetchone()
        if row is None:
            return None
        return self._decision(str(row["decision_json"]))

    def history(self, branch_id: str, boundary_fingerprint: str) -> list[StandingDecision]:
        """Every disposition ever recorded for this boundary, oldest first.

        Oldest first because it reads as a story: what was thought, and what changed it.
        """

        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT decision_json FROM standing_decisions
                WHERE branch_id = ? AND boundary_fingerprint = ?
                ORDER BY decided_at, rowid
                """,
                (branch_id, boundary_fingerprint),
            ).fetchall()
        return [self._decision(str(row["decision_json"])) for row in rows]

    def append_comment(self, comment: DecisionComment) -> DecisionComment:
        """Append one remark, numbering it inside the write that stores it.

        The ordinal the caller supplied is ignored and recomputed here. Reading the thread
        length in one statement and inserting in another lets two concurrent remarks agree on
        the same position, and the `UNIQUE` on `(branch, boundary, ordinal)` would then refuse
        the second — the reader losing a comment they had already written. Both statements run
        inside one transaction against a connection that serialises writes, so the number the
        insert uses is the number that was true when it committed.
        """

        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(ordinal), 0) AS highest FROM decision_comments
                WHERE branch_id = ? AND boundary_fingerprint = ?
                """,
                (comment.branch_id, comment.boundary_fingerprint),
            ).fetchone()
            numbered = comment.model_copy(update={"ordinal": int(row["highest"]) + 1})
            connection.execute(
                """
                INSERT INTO decision_comments(
                    comment_id, branch_id, boundary_fingerprint, ordinal, author,
                    created_at, comment_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    numbered.comment_id,
                    numbered.branch_id,
                    numbered.boundary_fingerprint,
                    numbered.ordinal,
                    numbered.author,
                    numbered.created_at.isoformat(),
                    numbered.model_dump_json(),
                ),
            )
            connection.commit()
        return numbered

    def comments_for(self, branch_id: str, boundary_fingerprint: str) -> list[DecisionComment]:
        """The thread, in the order it was written."""

        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT comment_json FROM decision_comments
                WHERE branch_id = ? AND boundary_fingerprint = ?
                ORDER BY ordinal
                """,
                (branch_id, boundary_fingerprint),
            ).fetchall()
        return [
            decode_stored_json(
                DecisionComment,
                str(row["comment_json"]),
                description="A stored decision comment",
                remedy=_COMMENT_REMEDY,
            )
            for row in rows
        ]

    def comment_counts_for_branch(self, branch_id: str) -> dict[str, int]:
        """How many remarks each discussed boundary carries, keyed by fingerprint.

        Counted in SQL rather than by loading threads, because the caller is drawing a badge
        per row: a listing of forty boundaries would otherwise decode every comment on the
        branch to render forty numbers. Boundaries nobody has discussed are absent rather
        than zero — the caller reads a missing key as no thread, which it is.
        """

        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT boundary_fingerprint, COUNT(*) AS total FROM decision_comments
                WHERE branch_id = ?
                GROUP BY boundary_fingerprint
                """,
                (branch_id,),
            ).fetchall()
        return {str(row["boundary_fingerprint"]): int(row["total"]) for row in rows}

    def _decision(self, document: str) -> StandingDecision:
        return decode_stored_json(
            StandingDecision,
            document,
            description="A stored standing decision",
            remedy=_DECISION_REMEDY,
        )
