"""Fetching a repository as an archive: what is accepted, and what is refused.

Served from an in-process transport rather than over the network. The thing under test is
what this code does with bytes and addresses, and a test that reached github.com would be
testing github.com — slowly, and differently on a train.
"""

from __future__ import annotations

import io
import os
import shutil
import tarfile
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from archcompass.domain.errors import RepositoryCheckoutError
from archcompass.repositories.adapters.https_tarball import HttpsTarballFetcher
from archcompass.repositories.sources import SourceArchiveService
from archcompass.repositories.storage import SourceStorage

HOSTS = frozenset({"github.com", "gitlab.com", "codeberg.org"})

#: Every address that must not become a request. The metadata one is the reason the whole
#: allowlist exists: on a cloud instance it serves credentials to anything that asks.
REFUSED = [
    "file:///tmp/archcompass-sessions/somebody-else/repo",
    "git@github.com:owner/repository",
    "http://github.com/owner/repository",
    "https://github.com@169.254.169.254/owner/repository",
    "https://169.254.169.254/owner/repository",
    "https://github.com.evil.test/owner/repository",
    "https://evil.test/github.com/owner/repository",
    "https://github.com:8080/owner/repository",
    "https://github.com/owner/repository?x=1",
    "https://github.com/owner/repository#fragment",
    "https://GITHUB.COM/owner/repository",
    "https://user:token@github.com/owner/repository",
    "https://github.com/../../etc/passwd",
    "https://github.com//repository",
    "https://github.com/owner",
    "https://github.com/owner/repository/tree/main",
    "https://bitbucket.org/owner/repository",
    "ssh://git@github.com/owner/repository",
    "/etc",
    "",
    # `$` in a Python pattern also matches before a trailing newline, so an address ending
    # in one would pass a check the request then made without it.
    "https://github.com/owner/repository\n",
    " https://github.com/owner/repository",
]


def _tarball(entries: dict[str, bytes], *, top: str = "repository-abc123") -> bytes:
    """A source tarball shaped the way the hosts shape one: everything under one directory."""

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tar:
        for name, content in entries.items():
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return raw.getvalue()


def _serving(body: bytes, *, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(status, content=body))


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, bytes]]:
    """Whatever the next fetch will be answered with, and the address it was asked for."""

    state: dict[str, bytes] = {"body": _tarball({"module.py": b"x = 1\n"})}

    def stream(method: str, url: str, **kwargs: object) -> httpx.Client.stream:
        state["asked"] = url.encode("utf-8")
        client = httpx.Client(transport=_serving(state["body"]))
        return client.stream(method, url)

    monkeypatch.setattr("archcompass.repositories.adapters.https_tarball.httpx.stream", stream)
    yield state


class _Origins:
    """The origin store, in memory: the persistence is SQLite's problem, not this test's."""

    def __init__(self) -> None:
        self.rows: dict[str, object] = {}

    def record(self, origin) -> None:
        self.rows[origin.root_path] = origin

    def get(self, root_path: str):
        return self.rows.get(root_path)


def _fetcher(max_bytes: int = 1 << 20) -> HttpsTarballFetcher:
    return HttpsTarballFetcher(hosts=HOSTS, max_bytes=max_bytes, timeout=5)


@pytest.mark.parametrize("address", REFUSED)
def test_an_address_this_workspace_will_not_fetch_is_refused(
    address: str, tmp_path: Path, served: dict[str, bytes]
) -> None:
    with pytest.raises(RepositoryCheckoutError):
        _fetcher().fetch(address, branch=None, destination=tmp_path / "tree")
    assert "asked" not in served, "the address was refused after a request was already made"
    assert not (tmp_path / "tree").exists()


def test_a_repository_on_an_allowed_host_lands_as_its_files(
    tmp_path: Path, served: dict[str, bytes]
) -> None:
    served["body"] = _tarball({"a.py": b"a = 1\n", "pkg/b.py": b"b = 2\n"})
    fetched = _fetcher().fetch(
        "https://github.com/owner/repository", branch=None, destination=tmp_path / "tree"
    )
    assert fetched.root_path == tmp_path / "tree"
    assert (tmp_path / "tree" / "a.py").read_bytes() == b"a = 1\n"
    assert (tmp_path / "tree" / "pkg" / "b.py").read_bytes() == b"b = 2\n"
    # No history came with it, which is the whole point: nothing git can be told to do.
    assert not (tmp_path / "tree" / ".git").exists()


def test_the_branch_asked_for_reaches_the_address(
    tmp_path: Path, served: dict[str, bytes]
) -> None:
    _fetcher().fetch(
        "https://github.com/owner/repository", branch="release/2", destination=tmp_path / "t"
    )
    assert b"release/2" in served["asked"]


@pytest.mark.parametrize("branch", ["..", "-x", "a" * 250, "--upload-pack=sh"])
def test_a_branch_that_is_not_a_branch_name_is_refused(
    branch: str, tmp_path: Path, served: dict[str, bytes]
) -> None:
    with pytest.raises(RepositoryCheckoutError):
        _fetcher().fetch(
            "https://github.com/owner/repository", branch=branch, destination=tmp_path / "t"
        )


def test_an_archive_over_the_cap_is_refused_while_it_streams(
    tmp_path: Path, served: dict[str, bytes]
) -> None:
    served["body"] = b"\0" * 4096
    with pytest.raises(RepositoryCheckoutError, match="larger than"):
        _fetcher(max_bytes=1024).fetch(
            "https://github.com/owner/repository", branch=None, destination=tmp_path / "t"
        )
    assert not (tmp_path / "t").exists()
    assert not list(tmp_path.iterdir()), "the staging directory outlived the failure"


def test_a_compression_bomb_dies_before_it_is_written(
    tmp_path: Path, served: dict[str, bytes]
) -> None:
    """Small on the wire, enormous once unpacked — which is what the second cap is for."""

    served["body"] = _tarball({"big.py": b"\0" * (8 << 20)})
    assert len(served["body"]) < (1 << 20)
    with pytest.raises(RepositoryCheckoutError, match="unpacks to more"):
        _fetcher(max_bytes=1 << 20).fetch(
            "https://github.com/owner/repository", branch=None, destination=tmp_path / "t"
        )
    assert not (tmp_path / "t").exists()


def test_an_archive_that_escapes_its_directory_is_refused(tmp_path: Path, served) -> None:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tar:
        escaping = tarfile.TarInfo("repository-abc/../../escaped.py")
        escaping.size = 0
        tar.addfile(escaping, io.BytesIO(b""))
    served["body"] = raw.getvalue()
    with pytest.raises(RepositoryCheckoutError):
        _fetcher().fetch(
            "https://github.com/owner/repository", branch=None, destination=tmp_path / "t"
        )
    assert not (tmp_path.parent / "escaped.py").exists()


def test_an_archive_carrying_a_symlink_is_refused(tmp_path: Path, served) -> None:
    """A link to somewhere outside the tree is how an archive reads a file it was not given."""

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tar:
        link = tarfile.TarInfo("repository-abc/passwd")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    served["body"] = raw.getvalue()
    with pytest.raises(RepositoryCheckoutError):
        _fetcher().fetch(
            "https://github.com/owner/repository", branch=None, destination=tmp_path / "t"
        )


def test_something_that_is_not_a_source_tarball_is_refused(tmp_path: Path, served) -> None:
    served["body"] = b"not an archive at all"
    with pytest.raises(RepositoryCheckoutError, match="could not be read"):
        _fetcher().fetch(
            "https://github.com/owner/repository", branch=None, destination=tmp_path / "t"
        )


def test_fetching_again_replaces_the_tree_and_keeps_the_old_one_on_failure(
    tmp_path: Path, served: dict[str, bytes]
) -> None:
    service = _service(tmp_path)
    served["body"] = _tarball({"a.py": b"first\n"})
    first = service.fetch("https://github.com/owner/repository")
    assert first.created is True
    assert (Path(first.root_path) / "a.py").read_bytes() == b"first\n"

    served["body"] = _tarball({"a.py": b"second\n"})
    again = service.fetch("https://github.com/owner/repository")
    assert again.created is False
    assert again.root_path == first.root_path
    assert (Path(again.root_path) / "a.py").read_bytes() == b"second\n"

    # A fetch that fails leaves what was already reviewable exactly where it was.
    served["body"] = b"not an archive at all"
    with pytest.raises(RepositoryCheckoutError):
        service.fetch("https://github.com/owner/repository")
    assert (Path(first.root_path) / "a.py").read_bytes() == b"second\n"


def test_a_tree_this_service_wrote_is_told_from_one_it_did_not(tmp_path: Path) -> None:
    service = _service(tmp_path)
    assert service.holds(tmp_path / "sources" / "repository-abc") is True
    # The root itself is where they live, not one of them.
    assert service.holds(tmp_path / "sources") is False
    assert service.holds(tmp_path / "elsewhere") is False
    # `..` is resolved before the comparison, so a path that spells its way out is out.
    assert service.holds(tmp_path / "sources" / ".." / "elsewhere") is False


def test_a_host_with_no_archive_address_cannot_be_allowed() -> None:
    """The allowlist narrows what the build knows how to ask for; it cannot widen it."""

    with pytest.raises(ValueError, match=r"evil\.test"):
        HttpsTarballFetcher(hosts=frozenset({"evil.test"}), max_bytes=1, timeout=1)


def _service(tmp_path: Path, **kwargs) -> SourceArchiveService:
    return SourceArchiveService(
        fetcher=_fetcher(),
        sources_root=tmp_path / "sources",
        hosts=HOSTS,
        origins=_Origins(),
        **kwargs,
    )


def test_a_visitor_holds_one_repository_at_a_time(
    tmp_path: Path, served: dict[str, bytes]
) -> None:
    """The per-fetch cap bounds each tree; without this, nothing bounds their sum."""

    service = _service(tmp_path)
    first = Path(service.fetch("https://github.com/owner/first").root_path)
    assert first.exists()

    second = Path(service.fetch("https://github.com/owner/second").root_path)

    assert second.exists()
    assert not first.exists(), "the previous repository was kept as well as the new one"
    assert [tree.name for tree in (tmp_path / "sources").iterdir()] == [second.name]


def test_the_instance_deletes_the_oldest_trees_to_make_room(tmp_path: Path) -> None:
    """A container's /tmp is memory: running out kills everyone, not just the fetch."""

    sessions = tmp_path / "sessions"
    trees = []
    for index, token in enumerate(["oldest", "middle", "newest"]):
        tree = sessions / token / ".archcompass" / "sources" / f"repository-{token}"
        tree.mkdir(parents=True)
        (tree / "big.py").write_bytes(b"\0" * 400)
        os.utime(tree, (1_700_000_000 + index, 1_700_000_000 + index))
        trees.append(tree)

    # Three trees of 400 bytes against a ceiling of 1200, reserving 400 for what is coming:
    # exactly one has to go, and it is the one nobody has touched for longest.
    SourceStorage(root=sessions, max_total_bytes=1200).make_room(
        reserve=400, keep=sessions / "mine" / ".archcompass" / "sources" / "repository-mine"
    )

    oldest, middle, newest = trees
    assert not oldest.exists()
    assert middle.exists()
    assert newest.exists()


def test_the_tree_being_replaced_is_never_swept(tmp_path: Path) -> None:
    """Deleting it here would be doing the caller's job before the replacement exists."""

    sessions = tmp_path / "sessions"
    mine = sessions / "mine" / ".archcompass" / "sources" / "repository-mine"
    mine.mkdir(parents=True)
    (mine / "a.py").write_bytes(b"\0" * 4000)

    SourceStorage(root=sessions, max_total_bytes=100).make_room(reserve=100, keep=mine)

    assert mine.exists()


def test_nothing_is_swept_while_there_is_room(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    tree = sessions / "someone" / ".archcompass" / "sources" / "repository-a"
    tree.mkdir(parents=True)
    (tree / "a.py").write_bytes(b"\0" * 10)

    SourceStorage(root=sessions, max_total_bytes=1 << 20).make_room(
        reserve=1000, keep=tmp_path / "elsewhere"
    )

    assert tree.exists()


def test_a_sessions_root_that_does_not_exist_yet_is_not_an_error(tmp_path: Path) -> None:
    """The first fetch on a cold instance happens before anybody has a workspace."""

    SourceStorage(root=tmp_path / "never-created", max_total_bytes=1).make_room(
        reserve=1 << 30, keep=tmp_path / "nothing"
    )


def _restorable(tmp_path: Path) -> SourceArchiveService:
    return SourceArchiveService(
        fetcher=_fetcher(),
        sources_root=tmp_path / "sources",
        hosts=HOSTS,
        origins=_Origins(),
    )


def test_a_repository_that_was_swept_is_fetched_again_rather_than_lost(
    tmp_path: Path, served: dict[str, bytes]
) -> None:
    """The whole reason the address is recorded: absence costs seconds, not a dead end."""

    service = _restorable(tmp_path)
    served["body"] = _tarball({"a.py": b"first\n"}, top="repository-abc123")
    root = Path(service.fetch("https://github.com/owner/repository").root_path)
    assert (root / "a.py").exists()

    # What the instance does to stay inside its memory.
    shutil.rmtree(root)
    assert not root.exists()

    assert service.restore(root) is True
    assert (root / "a.py").read_bytes() == b"first\n"


def test_restoring_asks_for_the_revision_that_was_served_not_the_branch_tip(
    tmp_path: Path, served: dict[str, bytes]
) -> None:
    """The atlas holds line numbers. Code that moved under them would cite the wrong lines."""

    service = _restorable(tmp_path)
    served["body"] = _tarball({"a.py": b"first\n"}, top="repository-abc123")
    root = Path(service.fetch("https://github.com/owner/repository").root_path)
    shutil.rmtree(root)

    service.restore(root)

    assert b"abc123" in served["asked"], "the re-fetch did not pin the original revision"


def test_a_repository_whose_archive_never_named_a_revision_is_not_restored(
    tmp_path: Path, served: dict[str, bytes]
) -> None:
    """Refused rather than restored wrongly: the same address may serve different code now."""

    service = _restorable(tmp_path)
    # A top-level directory that is not `<repository>-<revision>`, so nothing names a commit.
    served["body"] = _tarball({"a.py": b"first\n"}, top="something-else-entirely")
    root = Path(service.fetch("https://github.com/owner/repository").root_path)
    shutil.rmtree(root)

    assert service.restore(root) is False


def test_nothing_this_service_wrote_is_restored(tmp_path: Path) -> None:
    service = _restorable(tmp_path)

    assert service.restore(tmp_path / "somebody-elses-folder") is False


def test_a_repository_still_on_disk_is_left_alone(
    tmp_path: Path, served: dict[str, bytes]
) -> None:
    """Restoring is for absence. A tree that is there must not be fetched over."""

    service = _restorable(tmp_path)
    root = Path(service.fetch("https://github.com/owner/repository").root_path)
    served.pop("asked", None)

    assert service.restore(root) is False
    assert "asked" not in served, "a present repository was fetched again"


def test_a_refused_address_leaves_every_tree_where_it_was(tmp_path: Path) -> None:
    """Nothing is destroyed on the way to refusing an address.

    Everything between the request and the fetcher is destructive: the visitor's other
    tree is dropped so one visitor holds one repository, and `make_room` evicts other
    visitors' trees to stay inside the instance ceiling. All of it used to run before the
    address was looked at, so `POST /api/repositories/checkout` with `file:///etc/passwd`
    returned a refusal *and* deleted a working directory — the caller's, and somebody
    else's. Reproduced before this test existed; this is what stops it coming back.

    The existing failure test above covers a fetch that fails with a *valid* address,
    which takes the superseded-rename path and passes either way.
    """

    sources = tmp_path / "session-a" / ".archcompass" / "sources"
    sources.mkdir(parents=True)
    mine = sources / "existing-repository-abc123"
    mine.mkdir()
    (mine / "keep.py").write_text("# already fetched\n", encoding="utf-8")
    theirs = tmp_path / "session-b" / ".archcompass" / "sources" / "another-tree"
    theirs.mkdir(parents=True)
    (theirs / "keep.py").write_text("# another visitor\n", encoding="utf-8")

    service = SourceArchiveService(
        fetcher=HttpsTarballFetcher(
            hosts=frozenset({"github.com"}), max_bytes=1 << 20, timeout=5.0
        ),
        sources_root=sources,
        hosts=frozenset({"github.com"}),
        origins=_Origins(),
        # One byte, so `make_room` would evict everything it is allowed to touch.
        storage=SourceStorage(root=tmp_path, max_total_bytes=1),
    )

    with pytest.raises(RepositoryCheckoutError):
        service.fetch("file:///etc/passwd")

    assert (mine / "keep.py").exists(), "the caller's own tree was deleted by a refusal"
    assert (theirs / "keep.py").exists(), "another visitor's tree was evicted by a refusal"
