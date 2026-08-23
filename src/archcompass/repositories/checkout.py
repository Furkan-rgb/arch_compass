"""Turning "review this repository" into a directory on disk.

Everything downstream of a review already works in terms of a folder, and that is not going
to change: the atlas is built from files, and identity is read out of the git repository the
folder sits at the top of. What was missing was a way to name a repository that is not on
this machine yet. So this service is a small one — it makes the folder, and hands back where
it is.

The reason a clone is worth making rather than asking someone to make is identity, not
convenience. A folder chosen with a picker is a git top level only if the person happened to
pick one, and anything else falls back to a hash of its path: no branch, nothing shared with
the same repository seen anywhere else. A checkout Arch Compass makes is always a top level,
so `repo_id` comes from the root commit, branches group, and the verdict cache and the
baselines line up across machines without anyone arranging it.
"""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path

from archcompass.domain.errors import PathValidationError, RepositoryCheckoutError
from archcompass.repositories.ports import GitClient
from archcompass.repositories.records import CheckoutRefresh, RepositoryCheckout

#: The transports a clone may be asked for. Anything else is refused by name rather than
#: handed to git: `ext::` runs an arbitrary command as a transport, and a bare word beginning
#: with a dash is an option wearing a URL's clothes. Neither is something a person typing the
#: address of a repository into a form has ever meant.
ALLOWED_SCHEMES = ("https://", "http://", "ssh://", "git://", "file://")

#: `git@github.com:owner/repo.git` — scp syntax, which is what every host's copy button still
#: offers for ssh and therefore what people paste. Recognised explicitly rather than by
#: "contains a colon", so that a Windows path or a typo does not become a network address.
_SCP_URL = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:[^\s]+$")

#: What a branch name may be here. Narrower than git's own rules on purpose: this string
#: reaches a command line, and the refusals below are all names that would be an option, a
#: revision expression or a glob rather than a branch.
_BRANCH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

#: Everything a directory name is allowed to keep from a repository's name.
_UNSAFE_IN_DIRECTORY = re.compile(r"[^a-z0-9._-]+")

#: How much of the URL's digest goes in the directory name. Long enough that two repositories
#: never collide, short enough that the directory is still something a person can read.
_DIGEST_LENGTH = 12


class RepositoryCheckoutService:
    """Point Arch Compass at a repository, wherever it currently is."""

    def __init__(self, *, git: GitClient, checkouts_root: Path) -> None:
        self._git = git
        self._checkouts_root = checkouts_root

    def checkout(self, url_or_path: str, *, branch: str | None = None) -> RepositoryCheckout:
        """The directory holding this repository, cloned or updated as needed.

        Two shapes of answer, decided by what was asked for. A local path that is already the
        top level of a repository is returned as it stands: it is a git root, so it has
        everything a managed checkout would have been made for, and copying it would only
        cost disk and go stale. Everything else is a remote, and gets a directory of ours.
        """

        source = url_or_path.strip()
        if not source:
            raise PathValidationError("Name a repository to review.")
        requested_branch = self._validated_branch(branch)
        local = self._local_source(source)
        if local is not None:
            return self._existing_repository(local, requested_branch)
        return self._managed_checkout(self._validated_url(source), requested_branch)

    def _existing_repository(
        self, path: Path, branch: str | None
    ) -> RepositoryCheckout:
        """A repository already on this machine, reviewed where it lies.

        Read, never written: this is somebody's working copy, and a request for a branch it
        is not on is refused rather than acted on. Checking one out here would discard their
        uncommitted work to answer a question they could answer themselves, and quietly
        reviewing a different branch from the one asked for would be worse still.
        """

        described = self._git.describe(path)
        if described is None:
            raise PathValidationError(
                f"{path} is not a git repository. Point at one, or paste the address of a "
                "repository to clone."
            )
        if described.bare or described.top_level is None:
            raise RepositoryCheckoutError(
                f"{path} is a bare repository, so there are no files in it to review. Paste "
                "its address instead and Arch Compass will clone a working copy."
            )
        if described.top_level != path:
            raise RepositoryCheckoutError(
                f"{path} is inside the repository at {described.top_level} rather than the "
                "top of it. Review it as a folder, or point at the repository root."
            )
        if branch is not None and branch != described.branch_name:
            on = described.branch_name or "no branch (a detached HEAD)"
            raise RepositoryCheckoutError(
                f"{path} is on {on}, not {branch}, and Arch Compass will not move somebody's "
                f"working copy. Check {branch} out yourself, or paste this repository's "
                "address to have a separate checkout made for it."
            )
        return RepositoryCheckout(
            root_path=str(path),
            branch_name=described.branch_name,
            created=False,
            managed=False,
        )

    def _managed_checkout(self, url: str, branch: str | None) -> RepositoryCheckout:
        """A clone of our own, made once and updated every time after.

        The directory is derived from the URL rather than allocated, which is the whole of
        the bookkeeping: nothing is written down about a checkout anywhere, and asking for
        the same repository twice finds the same folder because it computes the same name.

        The update is a hard reset onto the remote's tip, and the reason is what this
        directory is for. It is a mirror, and a mirror that had merged, stashed or refused
        would be showing something that is not on the remote — every review run against it a
        claim about code nobody can find.
        """

        destination = self._checkouts_root / directory_name(url)
        described = self._git.describe(destination)
        created = described is None or described.top_level != destination
        if created:
            self._git.clone(url, destination)
            target = branch or self._git.default_branch(destination)
            self._git.force_checkout(destination, target)
        else:
            target = self._onto_remote_tip(destination, branch)
        return RepositoryCheckout(
            root_path=str(destination),
            branch_name=target,
            created=created,
            managed=True,
        )

    def remote_branches(self, url: str) -> list[str]:
        """The branches `url` publishes, for a chooser being filled in before a clone."""

        return self._git.remote_branches(self._validated_url(url))

    def refresh(self, root_path: str) -> CheckoutRefresh:
        """Bring the folder at `root_path` up to its remote, if it is ours to bring.

        The same update a repeat checkout performs, reached from the other end: a review page
        holds a directory and not the address it was cloned from, so the address is read back
        out of the checkout rather than asked for. Which means this can only ever act on a
        clone Arch Compass made — for anything else there is no `origin` of ours to trust,
        and the answer is that the folder was reviewed in place and left alone.

        The managed-directory test comes first and is about the path, not about what is in it.
        A directory somewhere else may well be a clone with a remote and be perfectly
        fetchable, and fetching it would still be wrong: it is somebody's working copy, a hard
        reset would take their uncommitted work with it, and no button labelled "new revision"
        is worth that.
        """

        requested = root_path.strip()
        if not requested:
            raise PathValidationError("Name a folder to refresh.")
        path = Path(requested).expanduser()
        if not path.is_dir():
            raise PathValidationError(
                f"There is no folder at {requested}, so there is nothing to refresh."
            )
        if not self._is_managed(path.resolve()):
            return CheckoutRefresh(root_path=requested, managed=False)
        if self._git.remote_url(path) is None:
            raise RepositoryCheckoutError(
                f"{requested} is in Arch Compass's checkouts directory but has no remote to "
                "update from. Delete it and check the repository out again by its address."
            )
        # Read before the fetch and again after the reset, because that is what "new" means
        # here: not whether the remote had anything to send, but whether the code this review
        # would run against is different code from last time.
        before = self._git.head_commit(path)
        described = self._git.describe(path)
        target = self._onto_remote_tip(path, described.branch_name if described else None)
        return CheckoutRefresh(
            root_path=requested,
            managed=True,
            updated=self._git.head_commit(path) != before,
            branch_name=target,
        )

    def _onto_remote_tip(self, checkout: Path, branch: str | None) -> str:
        """Fetch, then make the working tree be the remote's tip of `branch`.

        The mirror rule of `_managed_checkout`, in the one place both callers reach it: a
        directory Arch Compass owns holds what the remote holds, so the update discards local
        modifications rather than merging or refusing them.
        """

        self._git.fetch(checkout)
        target = branch or self._git.default_branch(checkout)
        self._git.force_checkout(checkout, target)
        return target

    def _is_managed(self, path: Path) -> bool:
        """Whether this resolved path is one of our own checkouts.

        Compared as resolved paths rather than as strings, since `..` and a symlink both make
        a prefix test say yes about a directory that is somewhere else. The root itself is not
        a checkout, only the directories in it are.
        """

        root = self._checkouts_root.expanduser().resolve(strict=False)
        return path != root and path.is_relative_to(root)

    @staticmethod
    def _local_source(source: str) -> Path | None:
        """The directory this string names on this machine, if it names one at all.

        A path is recognised by there being something at it, not by its shape. `file://` is
        deliberately not treated as local: it is a transport git clones over, and someone who
        wrote it asked for a clone.
        """

        if source.startswith(ALLOWED_SCHEMES) or _SCP_URL.match(source):
            return None
        candidate = Path(source).expanduser()
        if not candidate.is_dir():
            return None
        return candidate.resolve()

    @staticmethod
    def _validated_url(source: str) -> str:
        if source.startswith(ALLOWED_SCHEMES) or _SCP_URL.match(source):
            return source
        raise PathValidationError(
            f"{source} is neither a folder on this machine nor a repository address Arch "
            f"Compass can clone. Addresses start with one of: {', '.join(ALLOWED_SCHEMES)} "
            "— or look like git@host:owner/repo.git."
        )

    @staticmethod
    def _validated_branch(branch: str | None) -> str | None:
        if branch is None:
            return None
        name = branch.strip()
        if not name:
            return None
        if not _BRANCH_NAME.match(name) or ".." in name:
            raise PathValidationError(f"{branch} is not a branch name.")
        return name


def directory_name(url: str) -> str:
    """What this repository's directory is called, from the URL and nothing else.

    Shared with `repositories.sources`, which needs the same answer for the same
    reason: two ways of putting a repository on disk should not disagree about what to call
    the folder, and the rule for turning an address into a safe single path component is the
    interesting part of it.

    Two parts, because each answers half of it. The slug is for the person who opens the
    folder and wants to know whose code is in it; the digest is what actually keeps two
    repositories apart, since `repo` is a name a great many of them share.

    The digest is over a lightly normalized URL, so that the three addresses of one
    repository that differ only in a trailing slash or a `.git` suffix are one checkout
    rather than three. Nothing more is normalized than that: an http and an https address may
    well be the same repository, and a service that assumed so would be guessing about a
    remote it has not spoken to.
    """

    normalized = url.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[: -len(".git")]
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
    last = normalized.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    slug = _UNSAFE_IN_DIRECTORY.sub("-", last.lower()).strip("-.") or "repository"
    return f"{slug}-{digest}"
