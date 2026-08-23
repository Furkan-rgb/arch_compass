"""Repository indexing use case."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from archcompass.analysis.atlas import AtlasVersion
from archcompass.analysis.scope import validate_excluded_paths
from archcompass.ports.atlas import AtlasSource
from archcompass.ports.persistence import (
    AtlasRepository,
    LineageRepository,
    ScopeSelectionRepository,
)
from archcompass.ports.vcs import GitClient
from archcompass.repositories.lineage import (
    DEFAULT_BRANCH_NAME,
    BranchLineage,
    RepositoryBranch,
    RepositoryLineage,
    derive_branch_id,
    resolve_branch_lineage,
    resolve_repository_lineage,
)
from archcompass.repositories.records import RepositorySummary


class RepositoryIndexService:
    def __init__(
        self,
        *,
        analyzer: AtlasSource,
        atlases: AtlasRepository,
        lineages: LineageRepository,
        scope_selections: ScopeSelectionRepository,
        git: GitClient,
    ) -> None:
        self._analyzer = analyzer
        self._atlases = atlases
        self._lineages = lineages
        self._scope_selections = scope_selections
        self._git = git

    def index(
        self,
        repository: Path,
        *,
        branch_name: str | None = None,
        excluded_paths: Sequence[str] | None = None,
    ) -> AtlasVersion:
        """Build the atlas for this repository and file it under a durable lineage.

        `branch_name` names the branch this checkout is on where the checkout cannot say so
        itself, which is the ordinary CI case: a detached HEAD knows its commit and not the
        branch it was reached from. Left out, the working tree is believed, and a tree with
        no opinion falls back to the default branch name — see `repositories.lineage`.

        `excluded_paths` names the folders this analysis is to leave out, relative to the
        root. Left out entirely — which is what every caller that has never heard of scopes
        does — the repository's remembered selection is applied instead, so a re-index does
        not silently widen a review somebody narrowed. Given, even as an empty list, it is
        validated, remembered and applied: an empty list is somebody saying "all of it",
        which is a choice and undoes the last one.

        The lineage is resolved before the atlas is stored, so the row is written already
        stamped rather than updated a moment later. There is no window in which an atlas
        exists without the repository it belongs to.
        """

        applied = (
            # Keyed the way the atlas is keyed, and resolved the same way the analyzer
            # resolves it, so a selection recorded under one spelling of a directory is
            # found from the other. `strict=False` because a root that does not exist is
            # the analyzer's error to report, in its own words, a line below.
            self._recorded_for(str(repository.expanduser().resolve(strict=False)))
            if excluded_paths is None
            else validate_excluded_paths(excluded_paths)
        )
        # The analyzer canonicalizes and validates the root, and excludes whatever subtrees
        # it was built to leave out; stating either again here would be a second copy of a
        # rule that has to hold in one place.
        atlas = self._analyzer.analyze(repository, excluded_paths=applied)
        version = atlas.version
        if excluded_paths is not None:
            # Recorded under the analyzer's own canonical root rather than under the one
            # guessed above, because that is the string the stored atlas holds and therefore
            # the string a freshness check will look this up by.
            self._scope_selections.record(version.root_path, applied)
        repository_lineage = self._lineages.get_or_create_repository(
            resolve_repository_lineage(
                root_commit_sha=version.root_commit_sha,
                canonical_root=version.root_path,
            )
        )
        branch = self._based(
            repository_lineage,
            self._lineages.get_or_create_branch(
                resolve_branch_lineage(
                    repository_lineage, version.branch_name, branch_name=branch_name
                )
            ),
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

    def _recorded_for(self, canonical_root: str) -> tuple[str, ...]:
        """The scope this repository was last indexed under, or the whole of it.

        A repository nobody has chosen a scope for and one somebody chose to review whole
        are analysed identically; the difference between them matters to whoever is reading
        the selection back, not here.
        """

        return self._scope_selections.get(canonical_root) or ()

    def _based(
        self, repository: RepositoryLineage, branch: BranchLineage
    ) -> BranchLineage:
        """Point a branch at the repository's default branch, the first time both exist.

        Lazy and in application code because a migration is pure SQL and neither half of this
        can be computed there: the base is a derived id, and the branch it names may not have
        been indexed in this workspace yet. So it is resolved at the one moment both facts are
        in hand — a branch being written, with the default branch's lineage already stored.

        The default branch is `DEFAULT_BRANCH_NAME` rather than something read out of git.
        There is no cheap and honest way to ask a checkout what its repository's default branch
        is: `origin/HEAD` is a local cache of a remote's opinion, is absent from most clones
        and from every checkout with no remote, and being wrong here would attach a team's
        inheritance to a branch nobody works on. The name is also exactly what the rest of the
        system already falls back to when git will not name a branch, so one guess is made once
        and in one place. A team on `trunk` or `develop` gets no inheritance rather than the
        wrong inheritance, which is the failure worth having until a branch's base is something
        a person can state.

        Only ever fills a base in. A branch whose base is already recorded is left alone, and a
        branch that *is* the default one is left with none — there is nothing behind it, and
        pointing it at itself would be a cycle written down.
        """

        if branch.base_branch_id is not None or branch.branch_name == DEFAULT_BRANCH_NAME:
            return branch
        base_branch_id = derive_branch_id(repository.repo_id, DEFAULT_BRANCH_NAME)
        if self._lineages.get_branch(base_branch_id) is None:
            # The default branch has never been indexed here. Nothing is written, so the next
            # index of this branch asks again — which is what makes "index main, then the
            # feature branch" and the other order reach the same place.
            return branch
        return self._lineages.set_base_branch(branch.branch_id, base_branch_id)

    def list(self, *, limit: int = 100) -> list[RepositorySummary]:
        """Each indexed repository once, with what is true of it right now beside it.

        The stored row says what was analysed and when. Three things a reader needs are not
        in it, because none of them is a fact about the atlas: where the checkout has got to
        since, how far that is, and how much of the repository the analysis was told to
        leave out. All three are read here rather than written into the row, because all
        three change without anything re-indexing.
        """

        return [
            self._against_the_checkout(summary)
            for summary in self._atlases.list_repositories(limit=limit)
        ]

    def scope(self, root_path: str) -> tuple[str, ...]:
        """The folders this repository is reviewed without, as anything reading it sees them.

        The stored `None` — nobody has chosen — and the stored empty list — somebody chose
        the whole repository — are one answer here, because a caller listing what was left
        out has nothing to say about either. The two are still kept apart where the
        difference is load-bearing, which is the next analysis of this repository.
        """

        return self._recorded_for(root_path)

    def _against_the_checkout(self, summary: RepositorySummary) -> RepositorySummary:
        root = Path(summary.root_path)
        head = self._git.head_commit(root)
        # Asked only where there is a distance that could be anything but zero. A commit that
        # is already `HEAD` is nought commits behind by definition, and a listing of seven
        # repositories should not spend seven subprocesses proving it.
        behind: int | None = None
        if head is not None and summary.git_commit_sha is not None:
            behind = (
                0
                if head == summary.git_commit_sha
                else self._git.commits_since(root, summary.git_commit_sha)
            )
        return summary.model_copy(
            update={
                "head_commit_sha": head,
                "commits_behind": behind,
                "excluded_path_count": len(self.scope(summary.root_path)),
            }
        )

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
