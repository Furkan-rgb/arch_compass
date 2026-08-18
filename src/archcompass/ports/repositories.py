"""Persistence protocols."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from archcompass.boundary.atlas import Atlas
from archcompass.boundary.checkout import SourceOrigin
from archcompass.boundary.lineage import BranchLineage, RepositoryLineage
from archcompass.boundary.workspace import (
    RepositorySummary,
)


class LineageRepository(Protocol):
    """Storage for the identities a repository and its branches keep across checkouts.

    Both ids are derived from facts rather than allocated, so writing is get-or-create: the
    same repository indexed twice computes the same `repo_id` both times, and the row that
    already exists is the answer rather than a conflict.

    `set_base_branch` is the exception and is deliberately not an update: it fills in a base
    that is not yet known and leaves a known one alone, because which branch a line of work
    reads its standings through is not something a re-index should be able to move.
    """

    def get_or_create_repository(self, lineage: RepositoryLineage) -> RepositoryLineage: ...

    def get_or_create_branch(self, lineage: BranchLineage) -> BranchLineage: ...

    def set_base_branch(self, branch_id: str, base_branch_id: str) -> BranchLineage: ...

    def repository(self, repo_id: str) -> RepositoryLineage | None: ...

    def get_branch(self, branch_id: str) -> BranchLineage | None: ...

    def list_repositories(self, *, limit: int = 100) -> list[RepositoryLineage]: ...

    def list_branches(self, repo_id: str | None = None) -> list[BranchLineage]: ...


class AtlasRepository(Protocol):
    def save(self, atlas: Atlas) -> None: ...

    def get(self, version_id: str) -> Atlas: ...

    def latest_for_path(self, root: Path) -> Atlas | None: ...

    def list_versions(self, *, limit: int = 100) -> list[RepositorySummary]: ...


class ScopeSelectionRepository(Protocol):
    """Which folders a repository is reviewed without, kept beyond the request that said so.

    Persisted rather than passed, because the caller that has to apply a scope is usually not
    the caller that chose it: a freshness check recomputes the repository's fingerprint from a
    stored atlas, and a fingerprint taken over a different set of files would mark that atlas
    stale forever.

    Keyed by canonical root path, which is what a stored atlas holds.
    """

    def record(self, root_path: str, excluded_paths: Sequence[str]) -> None:
        """Remember this scope for this repository, replacing whatever was chosen before.

        An empty sequence is a scope: it says "review everything", and it is recorded so a
        later index that names no scope keeps reviewing everything rather than falling back
        to a choice that was deliberately undone.
        """
        ...

    def get(self, root_path: str) -> tuple[str, ...] | None:
        """The folders this repository is reviewed without, or `None` if nobody has chosen.

        `None` and `()` are different answers and both are ordinary. Nobody choosing is the
        common case — every repository indexed from the CLI — and choosing everything is
        what somebody who opened the folder list and cleared it meant.
        """
        ...


class SourceOriginRepository(Protocol):
    """Where a fetched directory came from, for a workspace that may not keep the directory."""

    def record(self, origin: SourceOrigin) -> None: ...

    def get(self, root_path: str) -> SourceOrigin | None:
        """The address behind this directory, or `None` for one nobody fetched.

        `None` is an ordinary answer rather than a miss: a bundled example was never
        fetched, and neither was a folder somebody picked on their own machine.
        """
        ...
