"""What is in a repository, shallowly, so that a scope can be chosen with the facts in hand.

Read before an analysis rather than derived from one, which is the point: a caller choosing
what to leave out has not indexed anything yet, and indexing the whole repository to find out
what to skip would spend exactly what skipping it was meant to save.

Counted the way the analysis counts, and that is load-bearing rather than tidy. The listing
answers "what would leaving this out save", so it has to leave out what the analysis leaves
out — the ignored directories, symlinks — or the numbers would describe a repository nobody
is going to analyse.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from archcompass.analysis.scope import (
    IGNORED_DIRECTORIES,
    RepositoryFolder,
    RepositoryFolderTree,
)
from archcompass.domain.errors import PathValidationError

#: Directory names that usually hold something other than the code under review. Advisory,
#: and never applied on anybody's behalf: `examples/` is the product in a library of
#: examples, and `tests/` is the subject of a review about how a project tests itself.
#: Guessing from a name is good enough to offer and nowhere near good enough to act on.
SUGGESTED_EXCLUSIONS = {
    "tests",
    "test",
    "testing",
    "docs",
    "doc",
    "examples",
    "example",
    "benchmarks",
    "benchmark",
    "samples",
    "sample",
    "demos",
    "demo",
}

#: How deep the listing goes. One level is too shallow for the repository whose vendored
#: copy of somebody else's library sits at `src/vendor`; three is a file browser, and the
#: choice being made is about subtrees rather than about files.
_MAX_DEPTH = 2


def folder_tree(root: Path) -> RepositoryFolderTree:
    """Every directory near the top of this repository that has Python under it.

    Counts are recursive, so a folder's number is what excluding it would save — the whole
    question — and a child's Python is therefore counted in its parent's as well. The totals
    are the repository's own, not the sum of the listing, for the same reason.

    Folders with no Python anywhere under them are left out. There is nothing to save by
    excluding one, and a repository's top level is mostly such folders.
    """

    canonical = root.expanduser().resolve(strict=False)
    if not canonical.is_dir():
        raise PathValidationError(f"Repository path is not a directory: {root}")
    files: defaultdict[str, int] = defaultdict(int)
    counted_bytes: defaultdict[str, int] = defaultdict(int)
    total_files = 0
    total_bytes = 0
    for path in canonical.rglob("*"):
        relative_parts = path.relative_to(canonical).parts
        if any(part in IGNORED_DIRECTORIES for part in relative_parts):
            continue
        # Asked in the same order and of the same things as `_discover_files`: a symlink is
        # never followed, so a link into a tree of Python is not counted as Python here and
        # would not be analysed either.
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix != ".py":
            continue
        size = path.stat().st_size
        total_files += 1
        total_bytes += size
        directories = relative_parts[:-1]
        for depth in range(1, min(len(directories), _MAX_DEPTH) + 1):
            folder = "/".join(directories[:depth])
            files[folder] += 1
            counted_bytes[folder] += size
    return RepositoryFolderTree(
        root_path=str(canonical),
        folders=tuple(
            RepositoryFolder(
                path=folder,
                python_files=files[folder],
                python_bytes=counted_bytes[folder],
                suggested=folder.rsplit("/", maxsplit=1)[-1] in SUGGESTED_EXCLUSIONS,
            )
            for folder in sorted(files)
        ),
        total_python_files=total_files,
        total_python_bytes=total_bytes,
    )
