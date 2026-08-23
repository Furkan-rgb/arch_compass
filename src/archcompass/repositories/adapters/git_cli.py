"""Git, driven by the command line installed on this machine.

Shelled out to rather than bound as a library: cloning and fetching is exactly what the git
binary is for, it is already present wherever a developer works, and a library would be a
second implementation of authentication, transports and credential helpers for no gain. The
cost is that every call has to be honest about its arguments, which is what `_run` is for —
an argument list and never a shell string, so a URL is data at every layer and there is no
quoting rule to get wrong.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from archcompass.domain.errors import RepositoryCheckoutError
from archcompass.repositories.ports import LocalRepository

#: How long a command that only reads this disk may take. Generous for a question answered
#: from `.git`, and short enough that a wedged binary is a failure rather than a hang.
LOCAL_TIMEOUT_SECONDS = 30

#: How long a command that talks to a remote may take. A first clone of a real repository is
#: minutes of work on a slow link, and giving up on it early would be the common case failing.
NETWORK_TIMEOUT_SECONDS = 600


class GitCommandLineClient:
    """The `GitClient` port over the `git` executable."""

    def __init__(
        self,
        *,
        local_timeout: int = LOCAL_TIMEOUT_SECONDS,
        network_timeout: int = NETWORK_TIMEOUT_SECONDS,
    ) -> None:
        self._local_timeout = local_timeout
        self._network_timeout = network_timeout

    def describe(self, path: Path) -> LocalRepository | None:
        """What git says about `path`, or `None` when it says it is not a repository.

        Asked as three separate questions because they fail separately, and because the first
        one is the only one whose failure means "not a repository": a repository with no
        commits yet has a git directory and no branch, and a bare one has no working tree to
        report a top level for.
        """

        if self._ask(path, "rev-parse", "--git-dir") is None:
            return None
        bare = self._ask(path, "rev-parse", "--is-bare-repository") == "true"
        top_level = None if bare else self._ask(path, "rev-parse", "--show-toplevel")
        branch = self._ask(path, "symbolic-ref", "--short", "-q", "HEAD")
        return LocalRepository(
            top_level=self._resolved(top_level),
            bare=bare,
            branch_name=branch or None,
        )

    def clone(self, url: str, destination: Path) -> None:
        """Clone `url` into a directory that does not exist yet, or leave nothing behind.

        `--filter=blob:none` fetches the commits and trees and defers file contents until
        something reads them, which is most of the transfer saved on a large history with
        none of the cost of `--depth`: the history stays complete, so the root commit the
        repository's identity is derived from is still there to be asked for.

        A failed clone is removed rather than kept. Git's own cleanup is reliable for the
        common failures and not for all of them — an interrupted process leaves a half-written
        directory — and a partial checkout that a later call mistakes for a usable one is a
        much worse failure than cloning twice.
        """

        destination.parent.mkdir(parents=True, exist_ok=True)
        completed = self._execute(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-single-branch",
                "--",
                url,
                str(destination),
            ],
            timeout=self._network_timeout,
        )
        if completed is None:
            shutil.rmtree(destination, ignore_errors=True)
            raise RepositoryCheckoutError(
                f"{url} could not be cloned. Check that the address is right and that this "
                "machine can reach it — Arch Compass clones with whatever credentials git "
                "already has, so a private repository needs an ssh agent or a credential "
                "helper git can use."
            )

    def fetch(self, checkout: Path) -> None:
        """Bring every remote branch up to date, and forget the ones that are gone."""

        if self._run(
            checkout, "fetch", "--prune", "origin", timeout=self._network_timeout
        ) is None:
            raise RepositoryCheckoutError(
                f"The checkout at {checkout} could not be updated from its remote. It may "
                "have moved, or this machine may not be able to reach it right now."
            )

    def remote_url(self, checkout: Path) -> str | None:
        """Where this checkout came from, according to the checkout itself.

        Asked of `origin` by name rather than of whatever remotes happen to be configured: a
        clone Arch Compass made has exactly one, and a directory with some other arrangement
        is not one of ours to update.
        """

        return self._ask(checkout, "remote", "get-url", "origin") or None

    def head_commit(self, checkout: Path) -> str | None:
        """The commit `HEAD` resolves to, or `None` before the first one exists."""

        return self._ask(checkout, "rev-parse", "--verify", "--quiet", "HEAD") or None

    def commits_since(self, checkout: Path, commit: str) -> int | None:
        """How far `HEAD` has moved past `commit`, counted in commits.

        `rev-list --count` and not a comparison of two shas, because "different" is not the
        answer anybody wants: a reader deciding whether to re-index wants to know whether
        that is one commit's worth of drift or two hundred.

        `None` wherever git will not answer, which covers the two cases that are not
        failures — a directory outside version control, and a commit that is no longer in
        this history — as well as a machine with no git on it at all. Every one of them
        means the same thing to a caller: the distance cannot be stated, so do not state it.
        """

        counted = self._ask(checkout, "rev-list", "--count", f"{commit}..HEAD")
        if counted is None:
            return None
        try:
            return int(counted)
        except ValueError:  # pragma: no cover - `--count` answers with a number or fails
            return None

    def remote_branches(self, url: str) -> list[str]:
        """Every branch `url` publishes, read straight off the remote.

        `ls-remote` and not a clone: this answers a question asked while someone is still
        deciding what to fetch, and cloning a repository to find out what is in it would cost
        the whole transfer for a list of names.

        An empty list for every failure, including a remote that asked for credentials git
        does not have. The caller is filling in a chooser, and a chooser that cannot be filled
        has to fall back to a name being typed — an exception here would turn "I could not
        offer you the list" into "you may not clone this", which is a different and wrong
        answer.
        """

        completed = self._execute(
            ["git", "ls-remote", "--heads", "--", url], timeout=self._network_timeout
        )
        if completed is None:
            return []
        branches: list[str] = []
        for line in completed.stdout.splitlines():
            # `<sha>\trefs/heads/<name>`. Split once from the right of the tab so a branch
            # name containing a slash — `feature/thing` — survives intact.
            _, _, ref = line.partition("\t")
            if ref.startswith("refs/heads/"):
                branches.append(ref[len("refs/heads/") :])
        return sorted(set(branches))

    def default_branch(self, checkout: Path) -> str:
        """The branch the remote hands out to a caller who does not name one.

        Read from `origin/HEAD`, which a clone writes and a fetch does not maintain. When it
        is missing — an older clone, or a remote that had no HEAD at the time — it is asked
        for again explicitly rather than guessed at, because guessing `main` at a repository
        whose default is `master` produces an empty-looking review rather than an error.
        """

        head = self._ask(checkout, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
        if head is None:
            self._run(
                checkout,
                "remote",
                "set-head",
                "origin",
                "--auto",
                timeout=self._network_timeout,
            )
            head = self._ask(
                checkout, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD"
            )
        if not head:
            raise RepositoryCheckoutError(
                "This repository does not say which branch is its default, so one has to be "
                "named."
            )
        # `origin/main`, and the caller wants `main`: everything up to the first slash is the
        # remote's name, which is `origin` because that is the only remote a clone makes.
        return head.split("/", 1)[1] if "/" in head else head

    def force_checkout(self, checkout: Path, branch: str) -> None:
        """Put the working tree on the remote's tip of `branch`, whatever was there before.

        A managed checkout is a mirror of the remote and not somebody's working copy, so the
        update is a hard one: the branch is pointed at `origin/<branch>` and the tree is made
        to match, discarding local modifications rather than merging or refusing. Anything
        else and a checkout could drift from the branch it claims to be, which would make
        every review run against it a claim about code that is nowhere.

        Untracked files are left alone. Nothing but git writes here, and deleting whatever an
        analysis left behind is not this method's business.
        """

        remote_branch = f"refs/remotes/origin/{branch}"
        if self._ask(checkout, "rev-parse", "--verify", "--quiet", remote_branch) is None:
            raise RepositoryCheckoutError(
                f"This repository has no branch called {branch}."
            )
        # On the network budget, not the local one: `clone` filtered the blobs out, so this
        # is the command that actually fetches the file contents of the tree it checks out.
        # A question answered from `.git` it is not, and on the short budget every repository
        # bigger than a toy fails here after thirty seconds.
        if self._run(
            checkout,
            "checkout",
            "--force",
            "-B",
            branch,
            remote_branch,
            timeout=self._network_timeout,
        ) is None:
            raise RepositoryCheckoutError(
                f"The checkout at {checkout} could not be moved to {branch}."
            )

    def _ask(self, repository: Path, *arguments: str) -> str | None:
        """One command that only touches this disk, on the short budget."""

        return self._run(repository, *arguments, timeout=self._local_timeout)

    def _run(self, repository: Path, *arguments: str, timeout: int) -> str | None:
        """One git command against one repository, or `None` when it did not succeed.

        `-C` rather than a working directory, so the path is an argument like any other and
        the process this one runs in never changes directory under a concurrent caller.
        """

        completed = self._execute(
            ["git", "-C", str(repository), *arguments], timeout=timeout
        )
        return None if completed is None else completed.stdout.strip()

    @staticmethod
    def _execute(
        command: list[str], *, timeout: int
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                # A repository that wants a password gets none. Nothing here is attached to a
                # terminal — the caller is a web request or a CLI command already in flight —
                # so a prompt cannot be answered and would only sit there until the timeout
                # turns it into a failure minutes later. Refused immediately, the same call
                # fails in the time the network takes, and the message about credentials
                # `clone` already raises is the one the reader gets.
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except (OSError, subprocess.SubprocessError):
            return None

    @staticmethod
    def _resolved(path: str | None) -> Path | None:
        if not path:
            return None
        try:
            return Path(path).resolve(strict=True)
        except OSError:  # pragma: no cover - git named a path that vanished mid-call
            return None
