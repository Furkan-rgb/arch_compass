"""Lineage persistence: a row per repository, and one per branch worked on in it.

Both writes are get-or-create, because both ids are derived rather than allocated. Two runs
of the same repository compute the same `repo_id` independently, so the second write is not
a conflict to report — it is the same fact arriving twice, and the row that already exists is
the one that keeps its `first_seen_at`.
"""

from __future__ import annotations

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.stored_records import decode_stored_json
from archcompass.boundary.lineage import BranchLineage, RepositoryLineage
from archcompass.domain.errors import PersistenceError

_REPOSITORY_REMEDY = (
    "A lineage is derived from the repository itself, so re-indexing the repository "
    "writes it again."
)


class SQLiteLineageRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get_or_create_repository(self, lineage: RepositoryLineage) -> RepositoryLineage:
        """Record this repository, and return whichever row now stands for it.

        The stored row wins over the one passed in. They agree about everything that is
        derived — the id is a function of the rest — and differ only in `first_seen_at` and
        in the path this particular checkout is at, where the older answer is the true one.
        """

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO repository_lineages(
                    repo_id, root_commit_sha, canonical_root, first_seen_at, lineage_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    lineage.repo_id,
                    lineage.root_commit_sha,
                    lineage.canonical_root,
                    lineage.first_seen_at.isoformat(),
                    lineage.model_dump_json(),
                ),
            )
            connection.commit()
        stored = self.repository(lineage.repo_id)
        if stored is None:  # pragma: no cover - the insert above has just committed
            raise PersistenceError(
                f"Repository lineage {lineage.repo_id} vanished immediately after it was written"
            )
        return stored

    def get_or_create_branch(self, lineage: BranchLineage) -> BranchLineage:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO branch_lineages(
                    branch_id, repo_id, branch_name, base_branch_id, first_seen_at,
                    lineage_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    lineage.branch_id,
                    lineage.repo_id,
                    lineage.branch_name,
                    lineage.base_branch_id,
                    lineage.first_seen_at.isoformat(),
                    lineage.model_dump_json(),
                ),
            )
            connection.commit()
        stored = self.get_branch(lineage.branch_id)
        if stored is None:  # pragma: no cover - the insert above has just committed
            raise PersistenceError(
                f"Branch lineage {lineage.branch_id} vanished immediately after it was written"
            )
        return stored

    def set_base_branch(self, branch_id: str, base_branch_id: str) -> BranchLineage:
        """Record which branch this one reads through to, on a row that does not say yet.

        The one write in this module that is not get-or-create, and it is narrow on purpose:
        it only ever fills a base in, never changes or clears one. A base that has been set is
        a claim the workspace has already read standings through, and quietly re-pointing it
        would move which decisions govern a branch without anybody having decided anything.
        Widening that to a general update is a change with a conversation attached, not a
        parameter.

        Both the column and the stored document are written, because the document is what
        `get_branch` decodes and the column is what a reader querying the table sees. Two
        copies of one fact is the shape every table here uses, and they are only safe while
        nothing can write one without the other.
        """

        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE branch_lineages
                SET base_branch_id = ?,
                    lineage_json = json_set(lineage_json, '$.base_branch_id', ?)
                WHERE branch_id = ? AND base_branch_id IS NULL
                """,
                (base_branch_id, base_branch_id, branch_id),
            )
            connection.commit()
        stored = self.get_branch(branch_id)
        if stored is None:
            raise PersistenceError(
                f"Branch lineage {branch_id} is not stored, so it has no base to set"
            )
        return stored

    def repository(self, repo_id: str) -> RepositoryLineage | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT lineage_json FROM repository_lineages WHERE repo_id = ?",
                (repo_id,),
            ).fetchone()
        if row is None:
            return None
        return decode_stored_json(
            RepositoryLineage,
            str(row["lineage_json"]),
            description=f"Repository lineage {repo_id}",
            remedy=_REPOSITORY_REMEDY,
        )

    def get_branch(self, branch_id: str) -> BranchLineage | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT lineage_json FROM branch_lineages WHERE branch_id = ?",
                (branch_id,),
            ).fetchone()
        if row is None:
            return None
        return decode_stored_json(
            BranchLineage,
            str(row["lineage_json"]),
            description=f"Branch lineage {branch_id}",
            remedy=_REPOSITORY_REMEDY,
        )

    def list_repositories(self, *, limit: int = 100) -> list[RepositoryLineage]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT repo_id, lineage_json FROM repository_lineages
                ORDER BY first_seen_at, repo_id LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            decode_stored_json(
                RepositoryLineage,
                str(row["lineage_json"]),
                description=f"Repository lineage {row['repo_id']}",
                remedy=_REPOSITORY_REMEDY,
            )
            for row in rows
        ]

    def list_branches(self, repo_id: str | None = None) -> list[BranchLineage]:
        """Every branch of one repository, or of all of them when none is named."""

        query = "SELECT branch_id, lineage_json FROM branch_lineages"
        parameters: tuple[object, ...] = ()
        if repo_id is not None:
            query += " WHERE repo_id = ?"
            parameters = (repo_id,)
        query += " ORDER BY repo_id, branch_name"
        with self._database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            decode_stored_json(
                BranchLineage,
                str(row["lineage_json"]),
                description=f"Branch lineage {row['branch_id']}",
                remedy=_REPOSITORY_REMEDY,
            )
            for row in rows
        ]
