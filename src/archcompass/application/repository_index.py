"""Repository indexing use case."""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.atlas import AtlasVersion
from archcompass.domain.lineage import (
    RepositoryBranch,
    resolve_branch_lineage,
    resolve_repository_lineage,
)
from archcompass.domain.workspace import RepositorySummary
from archcompass.ports.atlas import RepositoryAnalyzer
from archcompass.ports.repositories import AtlasRepository, LineageRepository


class RepositoryIndexService:
    def __init__(
        self,
        *,
        analyzer: RepositoryAnalyzer,
        atlases: AtlasRepository,
        lineages: LineageRepository,
    ) -> None:
        self._analyzer = analyzer
        self._atlases = atlases
        self._lineages = lineages

    def index(self, repository: Path, *, branch_name: str | None = None) -> AtlasVersion:
        """Build the atlas for this repository and file it under a durable lineage.

        `branch_name` names the branch this checkout is on where the checkout cannot say so
        itself, which is the ordinary CI case: a detached HEAD knows its commit and not the
        branch it was reached from. Left out, the working tree is believed, and a tree with
        no opinion falls back to the default branch name — see `domain.lineage`.

        The lineage is resolved before the atlas is stored, so the row is written already
        stamped rather than updated a moment later. There is no window in which an atlas
        exists without the repository it belongs to.
        """

        # The analyzer canonicalizes and validates the root, and excludes whatever subtrees
        # it was built to leave out; stating either again here would be a second copy of a
        # rule that has to hold in one place.
        atlas = self._analyzer.analyze(repository)
        version = atlas.version
        repository_lineage = self._lineages.get_or_create_repository(
            resolve_repository_lineage(
                root_commit_sha=version.root_commit_sha,
                canonical_root=version.root_path,
            )
        )
        branch = self._lineages.get_or_create_branch(
            resolve_branch_lineage(
                repository_lineage, version.branch_name, branch_name=branch_name
            )
        )
        stamped = atlas.model_copy(
            update={
                "version": version.model_copy(
                    update={
                        "repo_id": repository_lineage.repo_id,
                        "branch_id": branch.branch_id,
                    }
                )
            }
        )
        self._atlases.save(stamped)
        return stamped.version

    def list(self, *, limit: int = 100) -> list[RepositorySummary]:
        return self._atlases.list_versions(limit=limit)

    def branches(self) -> list[RepositoryBranch]:
        """Every branch lineage this workspace has seen, with the repository it is in.

        Paired rather than listed alone: a `branch_id` is a hash of a `repo_id`, so a branch
        on its own is a name with no way to tell which of two repositories called `main` it
        belongs to.
        """

        repositories = {
            repository.repo_id: repository
            for repository in self._lineages.list_repositories()
        }
        listed: list[RepositoryBranch] = []
        for branch in self._lineages.list_branches():
            repository = repositories.get(branch.repo_id) or self._lineages.repository(
                branch.repo_id
            )
            # A branch whose repository is missing cannot happen — the foreign key says so —
            # and it is skipped rather than asserted about, because a listing is not the place
            # to fail over a row nobody can see.
            if repository is None:  # pragma: no cover - guarded by the schema
                continue
            repositories[branch.repo_id] = repository
            listed.append(RepositoryBranch(repository=repository, branch=branch))
        return listed
