"""The working copy a review is going to be run against."""

from __future__ import annotations

from pydantic import Field

from archcompass.domain.base import DomainModel


class RepositoryCheckout(DomainModel):
    """Where the code named by a URL or a path now sits, and what it is checked out at.

    The answer to "point Arch Compass at this repository", and the input to everything that
    follows: `root_path` is what indexing, reviewing and every lineage-derived identity are
    given. A managed checkout is a git top level, which is the whole point of making one —
    identity comes from the root commit rather than from a path hash, so the same repository
    reviewed on two machines groups together.
    """

    root_path: str = Field(min_length=1)
    #: The branch checked out, or `None` when git will not name one — a local checkout on a
    #: detached HEAD. Never `None` for a managed checkout, which is always put on a branch.
    branch_name: str | None = None
    #: True when this call produced the directory, false when it found and updated one. Only
    #: ever about the directory: a reused checkout that fast-forwarded onto twenty new commits
    #: is still not `created`.
    created: bool = False
    #: Whether Arch Compass owns this directory. False for a local repository reviewed where
    #: it lies, which is somebody's working copy and is never written to.
    managed: bool = False
