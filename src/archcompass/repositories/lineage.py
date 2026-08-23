"""Validated repository and branch lineage boundary records.

The identity a checkout already has — `repository_identity`, the hash of the canonical path
— answers "where is this on this machine", and that is the only question it can answer. Two
clones of the same repository are two strangers under it, and moving one directory makes a
repository into a new repository. Everything built on top of a run wants the opposite: a
verdict cached on Monday should still be about the same repository when CI checks out the
same code somewhere else on Tuesday.

So there are two identities here, and they are not competing. The path-derived one stays
exactly what it is, a checkout location. `repo_id` is the repository itself, and `branch_id`
is one line of work in it — the level at which humans hold an opinion ("on main, this
boundary is accepted"), which is why standing decisions, the case and the line of revisions
attach here rather than to any single run.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from archcompass.domain.repository import DEFAULT_BRANCH_NAME, derive_branch_id
from archcompass.records import BoundaryDTO, stable_id, utc_now

#: The branch a run is attributed to when git will not name one. A detached HEAD is the
#: ordinary shape of a CI checkout, and a non-git directory has no branches at all; neither
#: is a reason to leave a run unattached, because then the first CI run of a repository would
#: share nothing with the workspace runs of the same repository. `main` is a guess, and it is
#: a guess the caller can always override by naming the branch explicitly — which is what CI
#: does, since the branch is in the environment even when it is not in the working tree.


class RepositoryLineage(BoundaryDTO):
    """One repository, wherever it happens to be checked out.

    `canonical_root` is where it was first seen and is kept as a courtesy to a reader, not as
    part of the identity: the same repository cloned somewhere else keeps the `repo_id` it
    already had, and the row keeps naming the first path it was met at.
    """

    repo_id: str = Field(min_length=1)
    #: The first commit of the history, when this folder is one. Absent for a folder that is
    #: not the top level of a git repository — one nested inside another repository as much as
    #: one outside git altogether — where the path is all there is to go on.
    root_commit_sha: str | None = None
    canonical_root: str = Field(min_length=1)
    first_seen_at: datetime = Field(default_factory=utc_now)


class BranchLineage(BoundaryDTO):
    """One named line of work under a repository.

    A renamed branch is a new lineage and the old one goes stale. Following renames would
    mean trusting reflog archaeology to decide which decisions a team still holds, and a
    stale lineage that can be pruned is the cheaper wrong answer.
    """

    branch_id: str = Field(min_length=1)
    repo_id: str = Field(min_length=1)
    branch_name: str = Field(min_length=1)
    #: The branch this one came from, whose standings and case it reads through to where it
    #: has none of its own. `None` is an ordinary and honest value — the default branch of a
    #: repository has nothing behind it, and so does a branch first seen before the default
    #: one was ever indexed here — and it means the branch answers from its own records
    #: alone. Filled by the application rather than derived, because which branch a line of
    #: work came from is not a function of its name (see `workflow/cases.py` for how the
    #: chain is walked, and `RepositoryIndexService` for where it is set).
    base_branch_id: str | None = None
    first_seen_at: datetime = Field(default_factory=utc_now)


class RepositoryBranch(BoundaryDTO):
    """A branch lineage together with the repository it belongs to."""

    repository: RepositoryLineage
    branch: BranchLineage


def derive_repo_id(root_commit_sha: str | None, canonical_root: str) -> str:
    """The durable identity of a repository, from its history where it has one.

    The root commit is the one fact about a repository that survives cloning, moving,
    renaming and re-remoting it: every clone of a history shares its first commit, and
    nothing an ordinary workflow does rewrites it. The remote URL would have been the obvious
    alternative and is worse — remotes get renamed, a repository can have several, and a
    checkout can have none.

    The sha is only ever passed for a folder that *is* the top level of its repository. The
    folder put up for review is the project, and that is the whole of the scope: a folder
    nested inside some larger repository is its own project, not a corner of that
    repository's, and it borrows neither the enclosing history's identity nor its branch.
    Without that rule the sha alone answers for everything under one checkout — every project
    of a monorepo, and every bundled example in this one — so their reviews group together
    and one project's standing decisions govern another's boundaries.

    A nested folder therefore lands in the same place as a folder outside git altogether: the
    canonical path, which is not durable and does not pretend to be, because it is the only
    thing such a folder has. The price is that moving such a folder loses what was attached
    to it, and it is accepted rather than worked around — reading identity out of the
    enclosing repository is exactly the confusion above, and no cheaper signal distinguishes
    "a project that happens to live in a repository" from "a subdirectory of a project". The
    fallback is spelled with an extra `path` part so the two derivations can never collide,
    even for the pathological input where a path happens to read like a sha.

    A fork shares its root commit with what it was forked from, and is therefore the same
    repository under this scheme. That is deliberate for now: a fork of a repository is
    usually the same codebase under review, and separating the two would need a signal this
    layer does not have.
    """

    if root_commit_sha:
        return stable_id("repoid", root_commit_sha)
    return stable_id("repoid", "path", canonical_root)


def resolve_repository_lineage(
    *, root_commit_sha: str | None, canonical_root: str
) -> RepositoryLineage:
    """The lineage a checkout belongs to, derived from what git could say about it."""

    return RepositoryLineage(
        repo_id=derive_repo_id(root_commit_sha, canonical_root),
        root_commit_sha=root_commit_sha,
        canonical_root=canonical_root,
    )


def resolve_branch_lineage(
    repository: RepositoryLineage,
    detected_branch_name: str | None,
    *,
    branch_name: str | None = None,
) -> BranchLineage:
    """Which branch lineage a run attaches to.

    Three sources, in falling order of authority: a branch the caller states, the branch the
    working tree is actually on, and `DEFAULT_BRANCH_NAME`. The stated one comes first
    because the case it exists for is CI, where the checkout is detached and the branch is
    known to the environment rather than to the repository — a run that could only read the
    working tree would file every CI run under the same default and lose the distinction
    between branches exactly where it matters most.
    """

    name = branch_name or detected_branch_name or DEFAULT_BRANCH_NAME
    return BranchLineage(
        branch_id=derive_branch_id(repository.repo_id, name),
        repo_id=repository.repo_id,
        branch_name=name,
    )
