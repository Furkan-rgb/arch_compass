"""How much of one instance every visitor's fetched code may occupy, together.

A per-fetch cap bounds one repository and nothing else. Two things defeat it: one visitor
may fetch several repositories, and — because a session's directory is never deleted, only
its cached runtime handle is — every visitor who ever fetched anything is still holding
their tree. The product of those two is what actually has to fit.

It has to fit in memory, not on a disk. A container's writable filesystem is usually
`tmpfs`, so a fetched repository is spending the same allowance the server itself runs in,
and running out does not mean a failed fetch — it means the process is killed and every
visitor on the instance loses their session at once. That asymmetry is the whole reason this
exists: the cost of being slightly too eager to delete is that somebody pastes an address
again, and the cost of being too slow is everybody's work.

Least-recently-used, by the directory's own modification time. A tree nobody has touched
since before the trees around it is the best available guess at the visitor who has gone,
and it is the guess a browser cache makes for the same reason.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from threading import Lock


class SourceStorage:
    """The ceiling on fetched repositories across every session on this instance."""

    def __init__(self, *, root: Path, max_total_bytes: int) -> None:
        #: Where every session's workspace lives. One level above any one visitor, because
        #: the thing being bounded is the instance rather than the visitor.
        self._root = root.expanduser().resolve(strict=False)
        self._max_total_bytes = max_total_bytes
        # Held across the whole sweep. Two fetches arriving together would otherwise each
        # measure a total that the other is about to change, and both conclude there is room.
        self._lock = Lock()

    def make_room(self, *, reserve: int, keep: Path) -> None:
        """Delete other visitors' trees until `reserve` more bytes would still fit.

        `reserve` is the per-fetch cap rather than the size of what is coming, because the
        size of what is coming is not known until it has arrived — and a check made after it
        arrives is a check made after the memory was spent.

        `keep` is never deleted: it is the tree this fetch is replacing, and removing it here
        would be doing the caller's job at the wrong moment, before the replacement exists.
        """

        kept = keep.expanduser().resolve(strict=False)
        with self._lock:
            trees = sorted(self._trees(), key=lambda tree: tree.stat().st_mtime)
            total = sum(_size(tree) for tree in trees)
            for tree in trees:
                if total + reserve <= self._max_total_bytes:
                    return
                if tree.resolve(strict=False) == kept:
                    continue
                total -= _size(tree)
                shutil.rmtree(tree, ignore_errors=True)

    def _trees(self) -> list[Path]:
        """Every fetched repository on this instance, whoever fetched it.

        Found by walking the shape the workspaces have rather than by keeping a register:
        a register is a second source of truth that a restart, a crash or a hand-deleted
        directory would leave lying about what is on the filesystem.
        """

        if not self._root.is_dir():
            return []
        return [
            tree
            for session in self._root.iterdir()
            if (sources := session / ".archcompass" / "sources").is_dir()
            for tree in sources.iterdir()
            if tree.is_dir()
        ]


def _size(tree: Path) -> int:
    """What this tree costs, counting files and never following a link out of it."""

    return sum(
        item.stat().st_size
        for item in tree.rglob("*")
        if item.is_file() and not item.is_symlink()
    )
