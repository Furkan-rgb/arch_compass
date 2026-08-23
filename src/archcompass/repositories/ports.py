"""What getting a repository onto disk asks the outside world for.

Two ways in, rather than one with a mode. `GitClient` makes a remote's *history* appear and
keeps it current; `SourceArchiveFetcher` makes a remote's *files* appear, once, and has no
notion of a remote afterwards. Folding them together would mean a `GitClient` whose `fetch`,
`remote_url`, `head_commit`, `default_branch` and `force_checkout` all answered "not
applicable".

The reason to want the second is that the first drags git in with it: hooks, submodules,
`.gitattributes` filters, credential helpers, the `file://` and `ssh://` transports, and a
redirect policy of git's own. A public deployment reviewing a stranger's repository wants
none of that, and none of it can be present in a directory that was written by extracting a
tarball.

Both are narrow on purpose. The decisions — where a managed checkout lives, when a directory
is reused rather than cloned again, what a local path is allowed to be — are the
application's, and stay in `service.py`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class LocalRepository:
    """What git says about a directory that turned out to be a repository.

    Returned only when there is one; a path outside version control is `None` from
    `describe`, because "this is not a repository" is an ordinary answer rather than a
    failure. A bare repository answers `top_level=None`: it has a history and no working
    tree, and there is nothing in it to read files out of.
    """

    top_level: Path | None
    bare: bool
    #: The branch the working tree is on, or `None` for a detached HEAD or a bare repository
    #: — the same absence `repositories.lineage` already knows how to attribute a run despite.
    branch_name: str | None


class GitClient(Protocol):
    """The git operations a managed checkout needs, and no more."""

    def describe(self, path: Path) -> LocalRepository | None: ...

    def clone(self, url: str, destination: Path) -> None:
        """Put the whole history at `destination`, leaving nothing behind on failure.

        Whole rather than shallow: the repository's identity is derived from its first
        commit, which a truncated history does not contain.
        """
        ...

    def fetch(self, checkout: Path) -> None: ...

    def remote_url(self, checkout: Path) -> str | None:
        """The address `origin` points at, or `None` when there is no such remote.

        `None` rather than an error, because "this directory has no remote" is an ordinary
        answer: a repository initialised on this machine and never pushed has none, and the
        caller deciding whether a directory can be brought up to date needs to be told that
        rather than to catch it.
        """
        ...

    def head_commit(self, checkout: Path) -> str | None:
        """The commit the working tree is on, or `None` when there is not one yet."""
        ...

    def commits_since(self, checkout: Path, commit: str) -> int | None:
        """How many commits `HEAD` has that `commit` did not, or `None` where it cannot say.

        The question behind "is this atlas still about the code on disk". A timestamp cannot
        answer it — an index built an hour ago against an untouched checkout is current, and
        one built ten minutes ago with twelve commits landed since is not.

        `None` for a directory outside git and for a commit this checkout has never heard
        of, which is an ordinary outcome rather than a failure: a rewritten history or a
        re-clone leaves an atlas naming a commit that is genuinely gone, and the honest
        answer is that the distance is unknown rather than zero.
        """
        ...

    def remote_branches(self, url: str) -> list[str]:
        """Every branch `url` publishes, without cloning it.

        Asked of the remote rather than of a checkout, because the caller that wants this is
        choosing a branch *before* there is anywhere to check one out to. An unreachable or
        private remote answers with an empty list rather than an error: not being able to
        offer a list is an ordinary outcome — git may have no credentials for this address —
        and the caller's job is then to let a branch be named instead of refusing to proceed.
        """
        ...

    def default_branch(self, checkout: Path) -> str:
        """What the remote says its own default is, as a plain branch name."""
        ...

    def force_checkout(self, checkout: Path, branch: str) -> None:
        """Make the working tree be the remote's tip of `branch`, discarding what differs."""
        ...


@dataclass(frozen=True)
class FetchedSource:
    """Where a fetched repository landed, and what it was fetched from.

    `revision` is whatever the host called the thing it served — a commit sha when the host
    says one, otherwise the ref that was asked for. It is recorded rather than trusted: no
    freshness decision rests on it, because the content fingerprint the analyser computes
    from the files themselves is what every downstream comparison actually uses.
    """

    root_path: Path
    url: str
    revision: str | None


class SourceArchiveFetcher(Protocol):
    """Fetching a repository's files, for a deployment that will not run git."""

    def fetch(self, url: str, *, branch: str | None, destination: Path) -> FetchedSource:
        """Put the repository's files at `destination`, or leave nothing behind.

        `destination` is a directory that does not exist yet. An implementation that fails
        part way is required to remove it: a half-extracted tree that a later call mistakes
        for a complete one is a much worse failure than fetching twice.
        """
        ...
