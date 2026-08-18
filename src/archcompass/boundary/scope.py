"""Validated analysis-scope boundary records.
asked it to skip this time.

Two different kinds of omission live here on purpose. `IGNORED_DIRECTORIES` is a property of
the analyser — a `.git` directory or a `__pycache__` is never source, whoever is asking — and
it is folded into the analysis configuration hash, so changing it makes every stored atlas
stale. An exclusion, by contrast, is a property of one request: it says which subtrees of
*this* repository the caller does not want reviewed, and two callers may reasonably disagree
about the same repository without either of them being wrong.

That is why an exclusion is validated here and applied nowhere near the hash. It changes
which files an analysis reads, which changes the content fingerprint by itself, because the
files it left out never entered the digest. Nothing further has to record it for a stored
atlas to be recognised as the atlas of a different question.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import Field

from archcompass.boundary.base import DomainModel
from archcompass.domain.errors import ScopeValidationError

#: Directories no analysis ever descends into, whatever it was asked for. Not source, not
#: reviewable, and in several cases (a `.git`, a `.pytest_cache`) changing on their own
#: between two runs over identical code — which would make the content fingerprint move for
#: reasons nobody wrote.
#:
#: Lives in the domain rather than beside the parser because two things need the same answer:
#: the analysis, and the folder listing a caller reads before choosing what to exclude. A
#: listing built from a second copy of this set would show folders and counts that the
#: analysis then disagreed with, and the disagreement would look like a bug in the counts.
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
}


#: What counts as configuration rather than code, by suffix. Beside `IGNORED_DIRECTORIES`
#: for the reason that set is here: the analyser is no longer the only thing that has to know
#: which files of a repository are worth reading. A stage investigating how a symbol is used
#: searches the same files the atlas was built from, and a second copy of this set would let
#: it report a match in a file the analysis had never opened — or miss one it had.
#:
#: Folded into the analysis configuration hash by the analyser, which is what makes changing
#: it a decision rather than an edit: every stored atlas goes stale.
CONFIG_SUFFIXES = {".yaml", ".yml", ".toml", ".json", ".ini", ".cfg", ".env"}


def validate_excluded_paths(paths: Iterable[str]) -> tuple[str, ...]:
    """The subtrees to leave out, as relative POSIX directory paths, or a refusal.

    Refuses rather than repairs anything that could name a directory outside the repository:
    an absolute path, a `..` part, a backslash that a Windows path would carry. The analysis
    applies these by comparing path parts, so a value that escaped validation would not
    quietly exclude the wrong tree — it would silently exclude nothing at all, and a caller
    who asked for a smaller review would get the whole repository with no way to notice.

    Repairs only what has one possible meaning: a trailing slash, and the order and
    duplication of the list. `["src/", "tests", "src"]` and `["tests", "src"]` are the same
    request, and they have to reach the fingerprint as the same request, or re-indexing with
    the selection typed in a different order would look like the code had changed.

    Entries nested under another entry are dropped for the same reason. Excluding `a` already
    excludes `a/b`, so keeping both would leave two spellings of one scope — and the recorded
    selection is read back and compared, not just applied.
    """

    cleaned: list[str] = []
    for raw in paths:
        candidate = raw.strip()
        if not candidate:
            raise ScopeValidationError(
                "A folder to leave out cannot be blank; remove it from the list instead."
            )
        if "\\" in candidate:
            raise ScopeValidationError(
                f"Folders to leave out are written with forward slashes: {raw!r}."
            )
        if candidate.startswith("/"):
            raise ScopeValidationError(
                f"A folder to leave out is named relative to the repository, not from the "
                f"root of the filesystem: {raw!r}."
            )
        # Trailing slashes only. A leading one is refused above, and an interior double
        # slash is an empty part, which is refused below rather than collapsed: it is a
        # typo, and the two readings of it ("a/b" or something else) are not both harmless.
        trimmed = candidate.rstrip("/")
        if not trimmed:
            raise ScopeValidationError(
                "A folder to leave out cannot be the repository itself; there would be "
                "nothing left to review."
            )
        parts = trimmed.split("/")
        if any(part == "" for part in parts):
            raise ScopeValidationError(
                f"A folder to leave out has an empty part in it: {raw!r}."
            )
        if any(part in {".", ".."} for part in parts):
            # `..` could name somebody else's directory. `.` could not, and is refused with
            # it because it excludes nothing while looking like it excludes something.
            raise ScopeValidationError(
                f"A folder to leave out is named by its path inside the repository, without "
                f"'.' or '..': {raw!r}."
            )
        cleaned.append("/".join(parts))

    # Sorted, so a directory always comes before anything under it and one pass over the
    # list is enough to drop the nested entries.
    kept: list[tuple[str, ...]] = []
    for candidate in sorted(set(cleaned)):
        parts = tuple(candidate.split("/"))
        if any(parts[: len(entry)] == entry for entry in kept):
            continue
        kept.append(parts)
    return tuple("/".join(parts) for parts in kept)


def excludes(relative_parts: tuple[str, ...], excluded_paths: tuple[str, ...]) -> bool:
    """Whether a file at these path parts lies under one of the excluded directories.

    Compared part by part rather than by string prefix, because `src/apps` is not inside
    `src/app` and a prefix test says it is.
    """

    for excluded in excluded_paths:
        parts = tuple(excluded.split("/"))
        if relative_parts[: len(parts)] == parts:
            return True
    return False


class RepositoryFolder(DomainModel):
    """One directory of a repository, with how much Python is under it.

    Counted recursively, so a folder's number is what excluding it would cost — which is the
    question the reader is actually asking. A child's Python is therefore counted in its
    parent's total as well as in its own, and the totals on the tree are the repository's
    rather than the sum of this list.
    """

    #: POSIX and relative to the repository root: `tests`, `src/vendor`.
    path: str = Field(min_length=1)
    python_files: int = Field(ge=0)
    python_bytes: int = Field(ge=0)
    #: Whether this looks like a folder most reviews do not need. Advisory and nothing more:
    #: it is a guess from a directory's name, and a repository whose product lives in
    #: `examples/` would be gutted by a guess applied on its behalf. Nothing acts on this
    #: except a caller who reads it and decides.
    suggested: bool = False


class RepositoryFolderTree(DomainModel):
    """What is in a repository, shallowly, so a caller can choose what to leave out.

    Two levels deep and directories only. Deeper than that is a file browser, and the choice
    this informs is made about subtrees — `tests`, `docs`, `src/vendor` — rather than about
    files.
    """

    root_path: str = Field(min_length=1)
    folders: tuple[RepositoryFolder, ...] = ()
    total_python_files: int = Field(default=0, ge=0)
    total_python_bytes: int = Field(default=0, ge=0)
