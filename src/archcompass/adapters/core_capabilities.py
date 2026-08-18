"""Adapters from established storage/parsers into the clean-break capabilities."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from archcompass.application.capabilities import LoadedReviewContext
from archcompass.application.policies import PolicyService
from archcompass.domain import (
    ArchitectureCase,
    Policy,
    PolicyScope,
    PolicyStrength,
    RepositoryRef,
    Review,
)


class CoreReviewHistory(Protocol):
    def latest_for_branch(self, branch_id: str) -> Review | None: ...

    def history_for_branch(self, branch_id: str) -> tuple[Review, ...]: ...


class CoreCaseSnapshots(Protocol):
    def get(self, case_id: str, revision: int | None = None) -> ArchitectureCase: ...

    def record(self, case: ArchitectureCase) -> ArchitectureCase: ...


class SQLiteContextLoader:
    def __init__(
        self,
        connect: Callable[[], sqlite3.Connection],
        core_cases: CoreCaseSnapshots,
        reviews: CoreReviewHistory,
    ) -> None:
        self._connect = connect
        self._core_cases = core_cases
        self._reviews = reviews

    def load(
        self,
        repository_id: str,
        branch_id: str,
        case_id: str,
        case_revision: int | None,
    ) -> LoadedReviewContext:
        with self._connect() as connection:
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


class DataclassPolicyCorpus:
    def __init__(self, policies: PolicyService) -> None:
        self._policies = policies

    def policies_for(self, repository: RepositoryRef) -> tuple[Policy, ...]:
        return tuple(
            Policy(
                id=item.id,
                title=item.title,
                body=item.body,
                scope=PolicyScope(item.scope.value),
                strength=PolicyStrength(item.strength.value),
                content_hash=item.content_hash,
                tags=tuple(item.tags),
                applies_to=item.applies_to,
                source=item.source_path,
            )
            for item in sorted(
                self._policies.catalog(repository_root=repository.path),
                key=lambda policy: policy.id,
            )
        )
