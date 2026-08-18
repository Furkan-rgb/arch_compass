"""Validated working-copy boundary records."""

from __future__ import annotations

from pydantic import Field

from archcompass.boundary.base import DomainModel


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


class SourceOrigin(DomainModel):
    """The address a directory was fetched from, and the revision that answered.

    Kept because an extracted archive cannot be asked. A clone records its remote and can
    say where it came from years later; a directory of files says nothing, so the one short
    string that makes its absence recoverable has to be written down beside it.
    """

    root_path: str = Field(min_length=1)
    url: str = Field(min_length=1)
    #: What the host said it served. `None` where the archive did not name it — such a
    #: repository can be reviewed and cannot be restored, because restoring it might bring
    #: back different code under line numbers the atlas already recorded.
    revision: str | None = None


class CheckoutRefresh(DomainModel):
    """What asking a folder to catch up with its remote did, if anything.

    The answer to "review this again, with whatever has landed since" for a folder that is
    all the caller has — a review page knows the directory it ran against and not the address
    that directory was cloned from. Two of the three fields are about what did *not* happen:
    `managed` is false for somebody's own working copy, which is read and never written, and
    `updated` is false for a mirror that was already on the remote's tip. Both are ordinary
    outcomes, and a caller that treats either as a failure is wrong about them.
    """

    root_path: str = Field(min_length=1)
    #: Whether this directory is one of Arch Compass's own checkouts. False means nothing was
    #: touched: the folder is reviewed where it lies, and moving it is its owner's business.
    managed: bool = False
    #: Whether the tip moved. False for a checkout that was already current — the fetch still
    #: happened, it just had nothing to bring back.
    updated: bool = False
    #: The branch the checkout is now on, or `None` when nothing was refreshed.
    branch_name: str | None = None
