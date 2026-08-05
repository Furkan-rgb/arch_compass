"""The derivations that decide which repository and branch a run belongs to.

Pure functions, tested as such: everything later in this plan — the verdict cache, the
baseline, the standing decisions — is keyed on what these return, so a change of answer here
is a silent change of subject everywhere.
"""

from __future__ import annotations

from archcompass.domain.base import stable_id
from archcompass.domain.lineage import (
    DEFAULT_BRANCH_NAME,
    derive_branch_id,
    derive_repo_id,
    resolve_branch_lineage,
    resolve_repository_lineage,
)

SHA = "0" * 39 + "1"
OTHER_SHA = "0" * 39 + "2"


def test_the_root_commit_decides_the_identity_wherever_the_checkout_is() -> None:
    """The whole point: the same history in two directories is one repository."""

    assert derive_repo_id(SHA, "/home/one/project") == derive_repo_id(SHA, "/elsewhere/copy")


def test_a_directory_outside_git_falls_back_to_its_path() -> None:
    first = derive_repo_id(None, "/home/one/project")
    second = derive_repo_id(None, "/elsewhere/copy")

    assert first != second
    assert first == derive_repo_id(None, "/home/one/project")


def test_a_folder_that_is_not_its_own_repository_is_identified_by_where_it_is() -> None:
    """The reviewed folder is the project, and a folder inside a repository is not it.

    The analyzer withholds the sha for a root that is not the git top level, so two projects
    of one monorepo arrive here as two paths rather than as one history — which is the whole
    difference between two projects and one. Stated at this level because the price is paid
    here: such a folder is identified by where it is, and moving it loses that.
    """

    enclosing = derive_repo_id(SHA, "/monorepo")
    billing = derive_repo_id(None, "/monorepo/packages/billing")
    search = derive_repo_id(None, "/monorepo/packages/search")

    assert len({enclosing, billing, search}) == 3


def test_the_fallback_cannot_collide_with_a_real_history() -> None:
    """A path is hashed under an extra part, so no path can impersonate a root commit."""

    assert derive_repo_id(None, SHA) != derive_repo_id(SHA, "/anywhere")


def test_a_lineage_id_is_never_a_checkout_id() -> None:
    """The path-derived identity stays exactly what it was, and shares no prefix with these.

    Both are hashes of a path in the fallback case, and telling a location from an identity
    by looking at it is something a reader will have to do for as long as both exist.
    """

    root = "/home/one/project"

    assert derive_repo_id(None, root) != stable_id("repo", root)
    assert derive_repo_id(None, root).startswith("repoid_")
    assert stable_id("repo", root).startswith("repo_")


def test_a_branch_belongs_to_one_repository() -> None:
    first = derive_repo_id(SHA, "/one")
    second = derive_repo_id(OTHER_SHA, "/two")

    assert derive_branch_id(first, "main") != derive_branch_id(second, "main")
    assert derive_branch_id(first, "main") != derive_branch_id(first, "release")
    assert derive_branch_id(first, "main") == derive_branch_id(first, "main")


def test_a_repository_lineage_carries_what_it_was_derived_from() -> None:
    lineage = resolve_repository_lineage(root_commit_sha=SHA, canonical_root="/one")

    assert lineage.repo_id == derive_repo_id(SHA, "/one")
    assert lineage.root_commit_sha == SHA
    assert lineage.canonical_root == "/one"


def test_a_detached_checkout_is_attributed_to_the_default_branch() -> None:
    repository = resolve_repository_lineage(root_commit_sha=SHA, canonical_root="/one")

    branch = resolve_branch_lineage(repository, None)

    assert branch.branch_name == DEFAULT_BRANCH_NAME
    assert branch.branch_id == derive_branch_id(repository.repo_id, DEFAULT_BRANCH_NAME)


def test_a_stated_branch_outranks_the_working_tree() -> None:
    """The CI case: the checkout is detached and the branch is known to the environment."""

    repository = resolve_repository_lineage(root_commit_sha=SHA, canonical_root="/one")

    assert resolve_branch_lineage(repository, None, branch_name="feature").branch_name == (
        "feature"
    )
    assert resolve_branch_lineage(repository, "main", branch_name="feature").branch_name == (
        "feature"
    )
    assert resolve_branch_lineage(repository, "main").branch_name == "main"
