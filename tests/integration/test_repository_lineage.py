"""A repository keeps its identity when the directory holding it does not.

Against real git repositories in `tmp_path`, because the whole claim is about what git says
and a stubbed answer would only prove the stub. Each test builds its own workspace beside
its own repository: a workspace inside the analysed repository is excluded from the snapshot,
which would leave nothing to analyse.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.reasoning.adapters.providers import DETERMINISTIC_MODEL
from archcompass.repositories.lineage import DEFAULT_BRANCH_NAME, derive_repo_id

MODULE = """\
class Store:
    \"\"\"A thing to have an atlas about.\"\"\"

    def put(self, key: str) -> None:
        self._key = key
"""


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


def _commit_everything(root: Path, *, branch: str) -> None:
    _git(root, "init", "-b", branch)
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "first")


def _committed_repository(root: Path, *, branch: str = "work") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    # Named after the directory, so two repositories built in the same second are two
    # histories. Identical content committed at the same timestamp by the same author is the
    # same commit — git is content-addressed too — and the collision would look exactly like
    # the bug these tests are about.
    (root / "store.py").write_text(f"# {root.name}\n{MODULE}", encoding="utf-8")
    _commit_everything(root, branch=branch)
    return root


def _monorepo(root: Path, *projects: str, branch: str = "work") -> Path:
    """One history holding several projects, which is how a monorepo arrives."""

    for project in projects:
        directory = root / project
        directory.mkdir(parents=True)
        (directory / "store.py").write_text(f"# {project}\n{MODULE}", encoding="utf-8")
    _commit_everything(root, branch=branch)
    return root


def _runtime(workspace: Path) -> Runtime:
    workspace.mkdir(parents=True, exist_ok=True)
    return build_runtime(workspace, pin=pinned_model("fake", DETERMINISTIC_MODEL))


@pytest.fixture
def workspace_runtime(tmp_path: Path) -> Runtime:
    return _runtime(tmp_path / "workspace")


def test_indexing_a_git_repository_records_its_lineage(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    repository = _committed_repository(tmp_path / "repository")

    version = workspace_runtime.repository_service.index(repository)

    root_commit = _git(repository, "rev-list", "--max-parents=0", "HEAD")
    assert version.root_commit_sha == root_commit
    assert version.branch_name == "work"
    assert version.repo_id == derive_repo_id(root_commit, version.root_path)
    stored = workspace_runtime.lineage_repository.repository(version.repo_id or "")
    assert stored is not None
    assert stored.root_commit_sha == root_commit
    branch = workspace_runtime.lineage_repository.get_branch(version.branch_id or "")
    assert branch is not None
    assert branch.branch_name == "work"
    assert branch.repo_id == version.repo_id


def test_a_stored_atlas_is_read_back_with_the_lineage_it_was_stamped_with(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    repository = _committed_repository(tmp_path / "repository")

    version = workspace_runtime.repository_service.index(repository)

    reloaded = workspace_runtime.atlas_repository.get(version.version_id)
    assert reloaded.version.repo_id == version.repo_id
    assert reloaded.version.branch_id == version.branch_id
    listed = workspace_runtime.repository_service.list()
    assert [(item.repo_id, item.branch_name) for item in listed] == [
        (version.repo_id, "work")
    ]


def test_the_same_history_in_a_new_directory_is_the_same_repository(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    """The failure this whole phase exists for: moving a checkout used to lose everything."""

    repository = _committed_repository(tmp_path / "before")
    first = workspace_runtime.repository_service.index(repository)

    moved = tmp_path / "after"
    repository.rename(moved)
    second = workspace_runtime.repository_service.index(moved)

    assert second.repo_id == first.repo_id
    assert second.branch_id == first.branch_id
    assert second.repository_identity != first.repository_identity
    # One repository, met twice, keeps the path it was first seen at.
    stored = workspace_runtime.lineage_repository.repository(first.repo_id or "")
    assert stored is not None
    assert stored.canonical_root == first.root_path


def test_two_repositories_are_two_lineages(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    one = workspace_runtime.repository_service.index(_committed_repository(tmp_path / "one"))
    two = workspace_runtime.repository_service.index(_committed_repository(tmp_path / "two"))

    assert one.repo_id != two.repo_id
    assert {item.repo_id for item in workspace_runtime.lineage_repository.list_repositories()} == {
        one.repo_id,
        two.repo_id,
    }


def test_a_project_inside_a_repository_is_not_the_repository(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    """The folder put up for review is the project, whatever it happens to be sitting in.

    Keyed on the enclosing root commit, every project of a monorepo — and every example
    bundled under this checkout — was one repository: one grouping in the listing, one
    baseline over all of them.
    """

    monorepo = _monorepo(tmp_path / "monorepo", "packages/billing", "packages/search")

    enclosing = workspace_runtime.repository_service.index(monorepo)
    billing = workspace_runtime.repository_service.index(monorepo / "packages" / "billing")
    search = workspace_runtime.repository_service.index(monorepo / "packages" / "search")

    # Neither the enclosing history nor its branch reaches a project inside it.
    assert billing.root_commit_sha is None
    assert billing.branch_name is None
    assert billing.repo_id == derive_repo_id(None, billing.root_path)
    assert len({enclosing.repo_id, billing.repo_id, search.repo_id}) == 3
    assert enclosing.root_commit_sha == _git(monorepo, "rev-list", "--max-parents=0", "HEAD")
    branch = workspace_runtime.lineage_repository.get_branch(billing.branch_id or "")
    assert branch is not None
    assert branch.branch_name == DEFAULT_BRANCH_NAME
    assert branch.branch_id != enclosing.branch_id


def test_a_project_inside_a_repository_still_reads_its_own_commit(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    """Identity stops at the folder; freshness does not, and never did.

    `git_commit_sha` answers "have these files moved since the atlas was built", which is a
    question about the folder rather than about whose repository it is in — so a nested
    project still gets the last commit that touched it.
    """

    monorepo = _monorepo(tmp_path / "monorepo", "packages/billing")

    version = workspace_runtime.repository_service.index(monorepo / "packages" / "billing")

    assert version.git_commit_sha == _git(
        monorepo, "log", "-1", "--format=%H", "--", "packages/billing"
    )


def test_a_directory_outside_git_falls_back_to_its_path(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "store.py").write_text(MODULE, encoding="utf-8")

    version = workspace_runtime.repository_service.index(repository)

    assert version.root_commit_sha is None
    assert version.branch_name is None
    assert version.repo_id == derive_repo_id(None, version.root_path)
    branch = workspace_runtime.lineage_repository.get_branch(version.branch_id or "")
    assert branch is not None
    assert branch.branch_name == DEFAULT_BRANCH_NAME
    # The lineage's default name is a sentinel, not a fact about the folder: the listing
    # shows no branch for a project that has no repository.
    listed = workspace_runtime.repository_service.list()
    assert [(item.repo_id, item.branch_name) for item in listed] == [
        (version.repo_id, None)
    ]


def test_a_detached_checkout_is_attributed_to_the_default_branch(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    """What CI looks like: the commit is known and the branch it came from is not."""

    repository = _committed_repository(tmp_path / "repository")
    attached = workspace_runtime.repository_service.index(repository)
    _git(repository, "checkout", "--detach", "HEAD")

    detached = workspace_runtime.repository_service.index(repository)

    assert detached.branch_name is None
    assert detached.repo_id == attached.repo_id
    branch = workspace_runtime.lineage_repository.get_branch(detached.branch_id or "")
    assert branch is not None
    assert branch.branch_name == DEFAULT_BRANCH_NAME


def test_a_stated_branch_is_used_where_the_checkout_cannot_say(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    repository = _committed_repository(tmp_path / "repository")
    _git(repository, "checkout", "--detach", "HEAD")

    version = workspace_runtime.repository_service.index(repository, branch_name="release")

    branch = workspace_runtime.lineage_repository.get_branch(version.branch_id or "")
    assert branch is not None
    assert branch.branch_name == "release"


def test_a_branch_lineage_is_created_once_and_then_reused(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    repository = _committed_repository(tmp_path / "repository")

    first = workspace_runtime.repository_service.index(repository)
    (repository / "store.py").write_text(MODULE + "\n\nVALUE = 1\n", encoding="utf-8")
    second = workspace_runtime.repository_service.index(repository)

    assert second.branch_id == first.branch_id
    assert len(workspace_runtime.lineage_repository.list_branches()) == 1
    original = workspace_runtime.lineage_repository.get_branch(first.branch_id or "")
    assert original is not None
    # Get-or-create: the second run finds the row rather than replacing it.
    assert original.first_seen_at <= second.created_at


def test_every_branch_is_listed_with_the_repository_it_belongs_to(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    repository = _committed_repository(tmp_path / "repository")
    workspace_runtime.repository_service.index(repository)
    _git(repository, "checkout", "-b", "release")
    workspace_runtime.repository_service.index(repository)

    listed = workspace_runtime.repository_service.branches()

    assert sorted(item.branch.branch_name for item in listed) == ["release", "work"]
    assert {item.repository.repo_id for item in listed} == {
        item.branch.repo_id for item in listed
    }


def test_a_review_is_recorded_against_the_branch_it_ran_on(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    repository = _committed_repository(tmp_path / "repository")
    version = workspace_runtime.repository_service.index(repository)
    case = workspace_runtime.case_service.create()

    review = workspace_runtime.review_workflow_service.start(
        repository_id=version.repo_id,
        branch_id=version.branch_id,
        case_id=case.id,
    )

    assert review.status.value in {"completed", "awaiting_answers"}
    assert review.repository.id == version.repo_id
    assert review.repository.branch_id == version.branch_id
    stored = workspace_runtime.review_workflow_service.get(review.id)
    assert stored.repository.id == version.repo_id
    listed = workspace_runtime.review_workflow_service.list()
    assert [(item.repository.id, item.repository.branch_id) for item in listed] == [
        (version.repo_id, version.branch_id)
    ]


def test_the_listing_says_how_far_the_checkout_has_moved_past_the_atlas(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    """Freshness answered as a distance in commits, which is the question a reviewer has.

    Wall-clock age was standing in for it and gets it wrong both ways round: an index built
    an hour ago against a checkout nobody has touched is current, and one built ten minutes
    ago with twelve commits landed since is not. Nothing on the wire could tell those apart.
    """

    repository = _committed_repository(tmp_path / "repository")
    indexed = workspace_runtime.repository_service.index(repository)

    current = workspace_runtime.repository_service.list()[0]
    assert current.head_commit_sha == indexed.git_commit_sha
    # Nought is an answer — the atlas was built at the commit that is checked out — and it
    # is the one a reader gets for the ordinary case of having just indexed something.
    assert current.commits_behind == 0

    (repository / "store.py").write_text(f"{MODULE}\n# later\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "second")
    _git(repository, "commit", "--allow-empty", "-m", "third")

    behind = workspace_runtime.repository_service.list()[0]
    assert behind.commits_behind == 2
    assert behind.head_commit_sha == _git(repository, "rev-parse", "HEAD")
    # The atlas is untouched by any of this: it still names the commit it was built at, and
    # that is the whole point of saying how far the checkout has gone past it.
    assert behind.git_commit_sha == indexed.git_commit_sha


def test_a_folder_outside_git_is_neither_behind_nor_current(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    """`None` rather than nought, because "no commits behind" is a claim this cannot make."""

    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "store.py").write_text(MODULE, encoding="utf-8")
    workspace_runtime.repository_service.index(repository)

    listed = workspace_runtime.repository_service.list()[0]

    assert listed.head_commit_sha is None
    assert listed.commits_behind is None
