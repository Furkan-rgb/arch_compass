"""Case snapshots, stored one row per revision and never rewritten."""

from __future__ import annotations

from archcompass.domain import ArchitectureCase
from archcompass.domain.errors import CaseNotFoundError, CaseRevisionConflictError
from archcompass.persistence.sqlite.codecs import DataclassRecordCodec
from archcompass.persistence.sqlite.database import Transaction


class SQLiteCoreCaseRepository:
    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction
        self._codec = DataclassRecordCodec(ArchitectureCase)
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_case_snapshots (
                    case_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    case_json TEXT NOT NULL,
                    PRIMARY KEY(case_id, revision)
                )
                """
            )

    def record(self, case: ArchitectureCase) -> ArchitectureCase:
        """Write one revision. Writing a different one over it is an error, not a no-op.

        This used to insert with `DO NOTHING` and then read the row back, which is only
        harmless while a revision number can be taken once. It cannot: a review started
        from an older revision opens the number after that one, and where that number was
        already on disk the run's answers were dropped and the caller was handed somebody
        else's revision with no error anywhere.

        Recording the same revision twice is still fine, because a resumed graph replays
        the node that wrote it. Same bytes, same revision, nothing to say.
        """

        document = self._codec.encode(case)
        with self._transaction() as connection:
            stored = connection.execute(
                "SELECT case_json FROM core_case_snapshots "
                "WHERE case_id = ? AND revision = ?",
                (case.id, case.revision),
            ).fetchone()
            if stored is None:
                connection.execute(
                    "INSERT INTO core_case_snapshots(case_id, revision, case_json) "
                    "VALUES (?, ?, ?)",
                    (case.id, case.revision, document),
                )
                return case
        if str(stored[0]) != document:
            raise CaseRevisionConflictError(
                f"Architecture case {case.id} already records a different revision "
                f"{case.revision}"
            )
        return self._codec.decode(str(stored[0]), description=f"Case {case.id}")

    def next_revision(self, case_id: str) -> int:
        """The first revision number this case has not used.

        Not `latest + 1` off a case somebody is holding: a review opened from an older
        revision is holding a number that has moved on, and this is what stops it writing
        over the revision that took it.
        """

        with self._transaction() as connection:
            row = connection.execute(
                "SELECT MAX(revision) FROM core_case_snapshots WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        if row is None or row[0] is None:
            raise CaseNotFoundError(f"Architecture case {case_id} was not found")
        return int(row[0]) + 1

    def get(self, case_id: str, revision: int | None = None) -> ArchitectureCase:
        query = "SELECT case_json FROM core_case_snapshots WHERE case_id = ?"
        parameters: tuple[object, ...] = (case_id,)
        if revision is None:
            query += " ORDER BY revision DESC LIMIT 1"
        else:
            query += " AND revision = ?"
            parameters = (case_id, revision)
        with self._transaction() as connection:
            row = connection.execute(query, parameters).fetchone()
        if row is None:
            raise CaseNotFoundError(f"Architecture case {case_id} was not found")
        return self._codec.decode(str(row[0]), description=f"Case {case_id}")

    def history(self, case_id: str) -> tuple[ArchitectureCase, ...]:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT case_json FROM core_case_snapshots WHERE case_id = ? "
                "ORDER BY revision",
                (case_id,),
            ).fetchall()
        if not rows:
            raise CaseNotFoundError(f"Architecture case {case_id} was not found")
        return tuple(
            self._codec.decode(str(row[0]), description=f"Case {case_id}")
            for row in rows
        )

    def list(self, *, limit: int = 100) -> tuple[ArchitectureCase, ...]:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT snapshots.case_json FROM core_case_snapshots AS snapshots "
                "JOIN (SELECT case_id, MAX(revision) AS revision "
                "FROM core_case_snapshots GROUP BY case_id) AS latest "
                "ON snapshots.case_id = latest.case_id "
                "AND snapshots.revision = latest.revision "
                "ORDER BY snapshots.case_id LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Stored case") for row in rows
        )
