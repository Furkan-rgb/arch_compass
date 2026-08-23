"""Reading a review's starting context out of the workspace database.

The `ContextLoader` capability, and the one place the graph's first node touches SQL: the
latest indexed atlas for a branch names the repository the review runs against, and the
case and the branch's review history are read beside it in the same call.
"""

from __future__ import annotations

from pathlib import Path

from archcompass.domain import RepositoryRef
from archcompass.persistence.sqlite.database import Transaction
from archcompass.ports.capabilities import LoadedReviewContext
from archcompass.ports.persistence import CaseSnapshots, ReviewSnapshots


class SQLiteContextLoader:
    def __init__(
        self,
        transaction: Transaction,
        core_cases: CaseSnapshots,
        reviews: ReviewSnapshots,
    ) -> None:
        self._transaction = transaction
        self._core_cases = core_cases
        self._reviews = reviews

    def load(
        self,
        repository_id: str,
        branch_id: str,
        case_id: str,
        case_revision: int | None,
    ) -> LoadedReviewContext:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT root_path, git_commit_sha, branch_name, content_fingerprint "
                "FROM atlas_versions WHERE repo_id = ? AND branch_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (repository_id, branch_id),
            ).fetchone()
        if row is None:
            raise ValueError(
                f"Repository {repository_id} branch {branch_id} has no indexed atlas"
            )
        repository = RepositoryRef(
            id=repository_id,
            path=Path(str(row["root_path"])).resolve(),
            branch_id=branch_id,
            content_id=str(row["content_fingerprint"]),
            branch=None if row["branch_name"] is None else str(row["branch_name"]),
            commit=None if row["git_commit_sha"] is None else str(row["git_commit_sha"]),
        )
        case = self._core_cases.get(case_id, case_revision)
        previous = self._reviews.latest_for_branch(branch_id)
        return LoadedReviewContext(
            repository, case, previous, self._reviews.history_for_branch(branch_id)
        )
