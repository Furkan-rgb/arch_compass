"""Turning "review this repository" into a directory, without version control.

The sibling of `application.checkouts`, and deliberately much smaller. That service exists
for identity: a clone is a git top level, so `repo_id` comes from the root commit and the
same repository reviewed on two machines groups together. This one gives that up on purpose.

It is for a deployment where the identity was never going to survive anyway — an ephemeral
per-visitor workspace that is gone when the container is — and where what a clone drags in
with it is the problem rather than the price. What is left without git is a directory of
files, which is all the atlas was ever built from, and `domain.lineage` already treats a
repository outside version control as an ordinary thing to be asked about rather than a
degraded one.
"""

from __future__ import annotations

import os
import shutil
from contextlib import suppress
from pathlib import Path

from archcompass.application.checkouts import directory_name
from archcompass.application.source_storage import SourceStorage
from archcompass.domain.checkout import RepositoryCheckout
from archcompass.domain.errors import PathValidationError
from archcompass.ports.source_archive import SourceArchiveFetcher


class SourceArchiveService:
    """Point Arch Compass at a repository by fetching its files, not its history."""

    def __init__(
        self,
        *,
        fetcher: SourceArchiveFetcher,
        sources_root: Path,
        hosts: frozenset[str],
        storage: SourceStorage | None = None,
        reserve_bytes: int = 0,
    ) -> None:
        self._fetcher = fetcher
        self._sources_root = sources_root
        #: The instance-wide ceiling, shared with every other session. `None` where nothing
        #: is shared — a workspace on one person's machine has a disk, not an allowance.
        self._storage = storage
        self._reserve_bytes = reserve_bytes
        #: The hosts this workspace will fetch from, so the page that offers the field can
        #: name them rather than let a reader discover the list one refusal at a time.
        self.hosts = hosts

    def fetch(self, url: str, *, branch: str | None = None) -> RepositoryCheckout:
        """The directory holding this repository's files, fetched fresh.

        Fetched again rather than reused when the directory is already there. A checkout can
        be brought up to date in place because it knows where it came from; an extracted
        tree knows nothing, so "again" can only mean "replace". That is also what the reader
        asked for — pasting an address a second time is how you say you want what is there
        now — and it costs one archive, which is the thing this path is cheap at.

        The old tree is moved aside before the new one is fetched, so a fetch that fails
        leaves the previous tree where it was rather than deleting a working directory on
        the way to not replacing it.
        """

        destination = self._sources_root / directory_name(url)
        self._sources_root.mkdir(parents=True, exist_ok=True)
        # One repository at a time per visitor. Reviewing a second does not mean wanting the
        # first kept: the atlas of the old one is already stored, and what is being dropped
        # is a copy of code that can be fetched again in seconds. Without this a visitor
        # holds as many trees as the daily cap allows fetches, and the per-fetch ceiling
        # bounds each of them rather than the sum — which is the number that has to fit.
        for existing in self._sources_root.iterdir():
            if existing.is_dir() and existing != destination:
                shutil.rmtree(existing, ignore_errors=True)
        if self._storage is not None:
            self._storage.make_room(reserve=self._reserve_bytes, keep=destination)
        superseded = destination.with_name(f"{destination.name}.superseded")
        shutil.rmtree(superseded, ignore_errors=True)
        existed = destination.exists()
        if existed:
            destination.rename(superseded)
        try:
            fetched = self._fetcher.fetch(url, branch=branch, destination=destination)
        except BaseException:
            if existed:
                shutil.rmtree(destination, ignore_errors=True)
                superseded.rename(destination)
            raise
        shutil.rmtree(superseded, ignore_errors=True)
        return RepositoryCheckout(
            root_path=str(fetched.root_path),
            branch_name=branch,
            created=not existed,
            managed=True,
        )

    def holds(self, path: Path) -> bool:
        """Whether this path is one of the trees this service wrote, marking it as in use.

        Compared after resolving both sides, because `..` and a symlink each make a prefix
        test say yes about a directory somewhere else entirely. The root itself is not one of
        them: it is the folder they live in.

        Asking counts as using. This is the question every index and every review asks before
        touching a fetched tree, so it is the moment at which "recently used" is actually
        known — and `SourceStorage` sweeps by modification time, which extraction sets once
        and nothing else would ever move. Without this, a tree being reviewed right now looks
        older every minute the review runs, and is exactly what the next visitor's fetch
        deletes to make room.
        """

        root = self._sources_root.expanduser().resolve(strict=False)
        candidate = path.expanduser().resolve(strict=False)
        if candidate == root or not candidate.is_relative_to(root):
            return False
        with suppress(OSError):
            os.utime(candidate)
        return True

    def validated_address(self, url: str) -> str:
        """The address, or a refusal — asked before anything is written to disk."""

        asked = url.strip()
        if not asked:
            raise PathValidationError("A repository address is required.")
        return asked
