"""Baseline persistence: what one branch has already seen, one row per boundary.

Writes are last-writer-wins, which is the opposite of the verdict cache next door and for a
reason. A cached verdict is an answer that was reached once and must not move; a baseline
entry is a claim about the present, and re-baselining a branch is someone stating it again
with whatever the boundary looks like now. So `put_all` replaces.

Reads answer one question — "what does this branch already know about?" — and answer it for
a whole branch at once, keyed by fingerprint. A run comparing forty boundaries makes one
query, not forty.
"""

from __future__ import annotations

from collections.abc import Iterable

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.stored_records import decode_stored_json
from archcompass.domain.baseline import BaselineEntry

_REMEDY = (
    "A baseline entry records that a branch has seen a boundary, so deleting the row is "
    "safe: the boundary surfaces as new on the next run and can be baselined again."
)


class SQLiteBaselineRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def put_all(self, entries: Iterable[BaselineEntry]) -> int:
        """Record every entry, replacing whatever the branch claimed about those boundaries.

        Returns how many rows were written, which is the count of entries and deliberately
        not a count of *new* ones. Baselining is idempotent by design, and "42 boundaries
        baselined" is the true report of doing it twice — a caller told "0 added" the second
        time would reasonably wonder whether anything is recorded at all.
        """

        rows = [
            (
                entry.branch_id,
                entry.boundary_fingerprint,
                int(entry.material),
                entry.verdict_label,
                entry.added_at.isoformat(),
                entry.added_from_review,
                entry.model_dump_json(),
            )
            for entry in entries
        ]
        if not rows:
            return 0
        with self._database.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO branch_baselines(
                    branch_id, boundary_fingerprint, material, verdict_label,
                    added_at, added_from_review, entry_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.commit()
        return len(rows)

    def for_branch(self, branch_id: str) -> dict[str, BaselineEntry]:
        """Everything this branch has seen, keyed by boundary fingerprint.

        A dictionary rather than a list because every caller is about to do lookups by
        fingerprint, and the primary key already guarantees one entry per boundary.
        """

        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT boundary_fingerprint, entry_json FROM branch_baselines
                WHERE branch_id = ? ORDER BY added_at, boundary_fingerprint
                """,
                (branch_id,),
            ).fetchall()
        return {
            str(row["boundary_fingerprint"]): decode_stored_json(
                BaselineEntry,
                str(row["entry_json"]),
                description=(
                    f"Baseline entry {row['boundary_fingerprint']} on branch {branch_id}"
                ),
                remedy=_REMEDY,
            )
            for row in rows
        }

    def remove(self, branch_id: str, boundary_fingerprint: str) -> bool:
        """Forget one boundary, and say whether there was anything to forget.

        The boolean is the whole interface to "did that exist": a caller that has to turn a
        missing entry into a 404 would otherwise read before deleting and race with itself.
        """

        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM branch_baselines
                WHERE branch_id = ? AND boundary_fingerprint = ?
                """,
                (branch_id, boundary_fingerprint),
            )
            connection.commit()
            return cursor.rowcount > 0

    def count_for_branch(self, branch_id: str) -> int:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM branch_baselines WHERE branch_id = ?",
                (branch_id,),
            ).fetchone()
        return int(row["total"]) if row is not None else 0
