"""A repository named by address becomes a folder, and that folder is a git root.

Against real git and real repositories in `tmp_path`, with a local directory standing in for
a remote — `file://` is a transport git clones over like any other, so nothing here touches
the network and everything here exercises the commands that would. A stubbed git would only
prove the stub, and the claim being made is about what git actually does.

The point of all of it is the last assertion of the first test: the checkout is a top level,
so `repo_id` comes from the root commit rather than from a hash of wherever it landed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from archcompass.bootstrap import CHECKOUT_DIRECTORY, Runtime, build_runtime, pinned_model
from archcompass.domain.errors import PathValidationError, RepositoryCheckoutError
from archcompass.reasoning.adapters.providers import DETERMINISTIC_MODEL
from archcompass.repositories.lineage import derive_repo_id

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
        timeout=30,
    )
    return result.stdout.strip()


def _committed_repository(root: Path, *, branch: str = "main") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    # Named after the directory so that two repositories built in the same second are two
    # histories rather than, git being content-addressed, one.
    (root / "store.py").write_text(f"# {root.name}\n{MODULE}", encoding="utf-8")
    _git(root, "init", "-b", branch)
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "first")
    return root


def _commit(repository: Path, name: str, message: str) -> str:
    (repository / name).write_text(f"# {name}\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", message)
    return _git(repository, "rev-parse", "HEAD")


def _url(repository: Path) -> str:
    return f"file://{repository}"


@pytest.fixture
def workspace_runtime(tmp_path: Path) -> Runtime:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return build_runtime(workspace, pin=pinned_model("fake", DETERMINISTIC_MODEL))


def test_a_cloned_repository_lands_beside_the_database_and_is_a_git_root(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    remote = _committed_repository(tmp_path / "remote")

    checkout = workspace_runtime.checkout_service.checkout(_url(remote))

    assert checkout.created is True
    assert checkout.managed is True
    assert checkout.branch_name == "main"
    root = Path(checkout.root_path)
    assert root.parent == workspace_runtime.workspace / CHECKOUT_DIRECTORY
    assert (root / "store.py").exists()
    # The whole reason for cloning rather than asking someone to: identity from history.
    version = workspace_runtime.repository_service.index(root)
    assert version.root_commit_sha == _git(remote, "rev-list", "--max-parents=0", "HEAD")
    assert version.repo_id == derive_repo_id(version.root_commit_sha, version.root_path)
    assert version.branch_name == "main"


def test_the_same_address_reuses_its_directory_and_picks_up_new_commits(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    remote = _committed_repository(tmp_path / "remote")
    first = workspace_runtime.checkout_service.checkout(_url(remote))
    head = _commit(remote, "later.py", "second")

    second = workspace_runtime.checkout_service.checkout(_url(remote))

    assert second.root_path == first.root_path
    assert second.created is False
    assert _git(Path(second.root_path), "rev-parse", "HEAD") == head
    assert (Path(second.root_path) / "later.py").exists()


def test_a_managed_checkout_is_reset_onto_the_remote_rather_than_merged(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    """The mirror rule: what is in the folder is what is on the remote, or nothing is true."""

    remote = _committed_repository(tmp_path / "remote")
    first = workspace_runtime.checkout_service.checkout(_url(remote))
    root = Path(first.root_path)
    (root / "store.py").write_text("# edited by hand\n", encoding="utf-8")
    head = _commit(remote, "later.py", "second")

    workspace_runtime.checkout_service.checkout(_url(remote))

    assert _git(root, "rev-parse", "HEAD") == head
    assert "edited by hand" not in (root / "store.py").read_text(encoding="utf-8")


def test_a_named_branch_is_the_one_checked_out(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    remote = _committed_repository(tmp_path / "remote")
    _git(remote, "checkout", "-b", "feature")
    head = _commit(remote, "feature.py", "on the feature branch")
    _git(remote, "checkout", "main")

    checkout = workspace_runtime.checkout_service.checkout(_url(remote), branch="feature")

    assert checkout.branch_name == "feature"
    root = Path(checkout.root_path)
    assert _git(root, "rev-parse", "HEAD") == head
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD") == "feature"
    version = workspace_runtime.repository_service.index(root)
    assert version.branch_name == "feature"


def test_two_addresses_are_two_directories(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    first = _committed_repository(tmp_path / "first")
    second = _committed_repository(tmp_path / "second")

    one = workspace_runtime.checkout_service.checkout(_url(first))
    other = workspace_runtime.checkout_service.checkout(_url(second))

    assert one.root_path != other.root_path


def test_a_remote_lists_its_branches_without_being_cloned(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    # What fills the branch chooser on the start page. Asked of the remote rather than of a
    # checkout, because the reader is choosing a branch before there is anywhere to put one.
    remote = _committed_repository(tmp_path / "remote")
    _git(remote, "checkout", "-b", "release/2026-01")
    _commit(remote, "release.py", "on the release branch")
    _git(remote, "checkout", "main")

    branches = workspace_runtime.checkout_service.remote_branches(_url(remote))

    assert branches == ["main", "release/2026-01"]
    # A slash in a branch name survives: the ref is split on its tab, not on its slashes.
    assert not (tmp_path / "checkouts").exists() or not any(
        (tmp_path / "checkouts").iterdir()
    )


def test_a_remote_that_cannot_be_reached_offers_no_branches_rather_than_failing(
    workspace_runtime: Runtime,
) -> None:
    # An address git cannot reach — or a private one it has no credentials for — says nothing
    # about whether the branch the reader has in mind exists. So this is an empty list and the
    # form falls back to a name being typed; raising here would turn "I cannot offer you the
    # list" into "you may not clone this".
    assert workspace_runtime.checkout_service.remote_branches("https://example.invalid/x.git") == []


def test_a_branch_the_remote_does_not_have_is_refused_by_name(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    remote = _committed_repository(tmp_path / "remote")

    with pytest.raises(RepositoryCheckoutError, match="no branch called nowhere"):
        workspace_runtime.checkout_service.checkout(_url(remote), branch="nowhere")


def test_refreshing_a_managed_checkout_picks_up_a_new_remote_commit(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    """The button on the review page holds a folder, not the address it was cloned from."""

    remote = _committed_repository(tmp_path / "remote")
    checkout = workspace_runtime.checkout_service.checkout(_url(remote))
    head = _commit(remote, "later.py", "second")

    refreshed = workspace_runtime.checkout_service.refresh(checkout.root_path)

    assert refreshed.managed is True
    assert refreshed.updated is True
    assert refreshed.branch_name == "main"
    assert refreshed.root_path == checkout.root_path
    assert _git(Path(checkout.root_path), "rev-parse", "HEAD") == head
    assert (Path(checkout.root_path) / "later.py").exists()


def test_refreshing_a_checkout_that_is_already_current_says_nothing_moved(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    remote = _committed_repository(tmp_path / "remote")
    checkout = workspace_runtime.checkout_service.checkout(_url(remote))

    refreshed = workspace_runtime.checkout_service.refresh(checkout.root_path)

    assert refreshed.managed is True
    assert refreshed.updated is False
    assert refreshed.branch_name == "main"
    assert _git(Path(checkout.root_path), "rev-parse", "HEAD") == _git(
        remote, "rev-parse", "HEAD"
    )


def test_refreshing_a_checkout_stays_on_the_branch_it_was_put_on(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    """A named branch is not forgotten by a refresh, which never sees the original request."""

    remote = _committed_repository(tmp_path / "remote")
    _git(remote, "checkout", "-b", "feature")
    _commit(remote, "feature.py", "on the feature branch")
    _git(remote, "checkout", "main")
    checkout = workspace_runtime.checkout_service.checkout(_url(remote), branch="feature")
    _git(remote, "checkout", "feature")
    head = _commit(remote, "more.py", "more on the feature branch")

    refreshed = workspace_runtime.checkout_service.refresh(checkout.root_path)

    assert refreshed.branch_name == "feature"
    assert refreshed.updated is True
    assert _git(Path(checkout.root_path), "rev-parse", "HEAD") == head


def test_refreshing_somebody_elses_working_copy_touches_nothing(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    """Refusing by not acting: a folder outside our checkouts is read and left as it was."""

    repository = _committed_repository(tmp_path / "local", branch="work")
    (repository / "store.py").write_text("# uncommitted work\n", encoding="utf-8")
    before = (repository / "store.py").stat().st_mtime_ns
    head = _git(repository, "rev-parse", "HEAD")

    refreshed = workspace_runtime.checkout_service.refresh(str(repository))

    assert refreshed.managed is False
    assert refreshed.updated is False
    assert refreshed.branch_name is None
    assert refreshed.root_path == str(repository)
    assert (repository / "store.py").read_text(encoding="utf-8") == "# uncommitted work\n"
    assert (repository / "store.py").stat().st_mtime_ns == before
    assert _git(repository, "rev-parse", "HEAD") == head
    assert _git(repository, "rev-parse", "--abbrev-ref", "HEAD") == "work"


def test_refreshing_a_folder_that_is_not_there_says_so(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    with pytest.raises(PathValidationError, match="nothing to refresh"):
        workspace_runtime.checkout_service.refresh(str(tmp_path / "gone"))


def test_a_managed_directory_with_no_remote_is_refused_by_name(
    workspace_runtime: Runtime,
) -> None:
    """Ours by its address, and not a clone: the one case that is a fault rather than a no."""

    stray = workspace_runtime.workspace / CHECKOUT_DIRECTORY / "stray-000000000000"
    _committed_repository(stray)

    with pytest.raises(RepositoryCheckoutError, match="no remote to update from"):
        workspace_runtime.checkout_service.refresh(str(stray))


def test_a_local_repository_root_is_reviewed_where_it_lies(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    repository = _committed_repository(tmp_path / "local", branch="work")

    checkout = workspace_runtime.checkout_service.checkout(str(repository))

    assert checkout.root_path == str(repository)
    assert checkout.branch_name == "work"
    assert checkout.created is False
    assert checkout.managed is False
    assert not (workspace_runtime.workspace / CHECKOUT_DIRECTORY).exists()


def test_a_local_working_copy_is_never_moved_to_another_branch(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    repository = _committed_repository(tmp_path / "local", branch="work")

    with pytest.raises(RepositoryCheckoutError, match="will not move somebody's"):
        workspace_runtime.checkout_service.checkout(str(repository), branch="other")

    assert _git(repository, "rev-parse", "--abbrev-ref", "HEAD") == "work"


def test_a_folder_that_is_not_a_repository_says_so(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "store.py").write_text(MODULE, encoding="utf-8")

    with pytest.raises(PathValidationError, match="is not a git repository"):
        workspace_runtime.checkout_service.checkout(str(plain))


def test_a_bare_repository_on_disk_is_refused_with_what_to_do_instead(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    remote = _committed_repository(tmp_path / "remote")
    bare = tmp_path / "bare.git"
    subprocess.run(
        ["git", "clone", "--bare", "--", str(remote), str(bare)],
        check=True,
        capture_output=True,
        timeout=60,
    )

    with pytest.raises(RepositoryCheckoutError, match="bare repository"):
        workspace_runtime.checkout_service.checkout(str(bare))


def test_something_that_is_neither_a_folder_nor_an_address_is_refused(
    workspace_runtime: Runtime,
) -> None:
    with pytest.raises(PathValidationError, match="neither a folder"):
        workspace_runtime.checkout_service.checkout("ext::sh -c whoami")
