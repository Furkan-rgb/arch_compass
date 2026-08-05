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

from archcompass.adapters.models.deterministic import DETERMINISTIC_MODEL
from archcompass.bootstrap import CHECKOUT_DIRECTORY, Runtime, build_runtime, pinned_model
from archcompass.domain.errors import PathValidationError, RepositoryCheckoutError
from archcompass.domain.lineage import derive_repo_id

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


def test_a_branch_the_remote_does_not_have_is_refused_by_name(
    tmp_path: Path, workspace_runtime: Runtime
) -> None:
    remote = _committed_repository(tmp_path / "remote")

    with pytest.raises(RepositoryCheckoutError, match="no branch called nowhere"):
        workspace_runtime.checkout_service.checkout(_url(remote), branch="nowhere")


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
