"""The reviewed repository, read at the revision the atlas was built from.

The judge may look at source while it decides, and what it looks at has to be the snapshot
the candidate's line numbers and qualified names belong to. Two ways to serve that, and the
order between them is the whole of this module.

Git first. A review records the commit it judged, so `git show <revision>:./<path>` answers
about that commit however far the checkout has moved on since — immutable, repeatable, and
needing no freshness check at all because nothing about it can go stale.

The working tree second, and only under guard. A repository reviewed from a local path is
not a copy: `RepositoryCheckoutService` hands back the developer's own tree, so there may be
no commit to ask for and the files may change while a judgement is still reading them. Every
fallback read therefore asks `AtlasFreshnessChecker` immediately before touching disk rather
than once when this was constructed, and refuses when the answer has changed. A judgement
that mixed a newer tree with an older atlas would be reasoning about line numbers that name
different code, and no part of the record would show it.
"""

from __future__ import annotations

import fnmatch
import subprocess
from itertools import product
from pathlib import Path

from archcompass.analysis.atlas import Atlas
from archcompass.analysis.ports import AtlasFreshnessChecker
from archcompass.domain.errors import PathValidationError
from archcompass.reasoning.ports import SourceMatch

#: Long enough for git to answer about a large repository, short enough that a judgement
#: waiting on one cannot stall a review behind it.
_GIT_TIMEOUT_SECONDS = 20.0

#: Directories no judgement has business reading, skipped when walking the working tree.
#: Git never offers them, so this only ever applies on the fallback path.
_UNWALKED = frozenset({".git", ".archcompass", "node_modules", "__pycache__", ".venv"})


#: How many `**/` segments are expanded exhaustively. Two covers `src/**/tests/**/*.py`, and
#: the cap is only there so a pattern nobody meant to write cannot cost 2^n comparisons per
#: path; past it the pattern is tried whole and with every `**/` removed, which is the two
#: readings that matter.
_MAX_EXPANDED_WILDCARDS = 3


def _glob_forms(pattern: str) -> tuple[str, ...]:
    """One glob as every `fnmatch` pattern that means the same thing.

    `fnmatch` has no `**`. It has `*`, which already crosses `/`, so `**` mostly behaves —
    except in the one place it matters most: `**/` cannot match *zero* directories. So
    `tests/**/*.py` found `tests/unit/test_x.py` and missed `tests/test_x.py`, and a
    repository whose tests all sit directly in `tests/` answered a perfectly valid pattern
    with nothing. Measured on a real repository: four of fifty-six lookups.

    That is not a nicety. The glob description the model is handed is the vendor's, and it
    says `**` matches "any directories" — so the pattern was right and the matcher was
    narrow, which is the same shape of defect as promising absolute paths and returning
    relative ones.

    A bare name is still read as "anywhere". `*.py` means every Python file to whoever typed
    it, and matching only the root is not what anybody means.
    """

    seed = pattern if "/" in pattern else f"**/{pattern}"
    forms = {pattern, seed}
    for form in (pattern, seed):
        pieces = form.split("**/")
        if len(pieces) - 1 > _MAX_EXPANDED_WILDCARDS:
            forms.add(form.replace("**/", ""))
            continue
        for keep in product((True, False), repeat=len(pieces) - 1):
            forms.add(
                pieces[0]
                + "".join(
                    ("**/" if kept else "") + piece
                    for kept, piece in zip(keep, pieces[1:], strict=True)
                )
            )
    return tuple(sorted(form for form in forms if form))


class AtlasReviewedSource:
    """`ReviewedSource` over one atlas, its repository root and the revision it was made at."""

    def __init__(
        self,
        *,
        root: Path,
        revision: str | None,
        atlas: Atlas,
        freshness: AtlasFreshnessChecker | None = None,
    ) -> None:
        self._root = root
        self._revision = (revision or "").strip() or None
        self._atlas = atlas
        self._freshness = freshness

    # ---- the two ways to be served ---------------------------------------------

    def _git(self, *arguments: str) -> tuple[int, str]:
        try:
            done = subprocess.run(
                ["git", "-C", str(self._root), *arguments],
                capture_output=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return 1, ""
        return done.returncode, done.stdout.decode("utf-8", errors="replace")

    def _tree(self) -> Path:
        """The working tree, once it has been confirmed to still be what was analysed.

        Called by every fallback operation rather than once at construction. The whole
        reason this class exists is that the interval between those two moments is exactly
        when a developer's tree changes under a running review.
        """

        if self._freshness is not None:
            self._freshness.ensure_fresh(self._atlas)
        return self._root

    @staticmethod
    def _relative(path: str) -> str:
        cleaned = path.strip().lstrip("/")
        if ".." in Path(cleaned).parts:
            raise PathValidationError(
                "Paths are relative to the root of the repository under review."
            )
        return cleaned

    # ---- the four operations ---------------------------------------------------

    def list_directory(self, path: str) -> tuple[str, ...]:
        relative = self._relative(path)
        if self._revision:
            where = f"{relative}/" if relative else "."
            code, out = self._git("ls-tree", "--name-only", self._revision, "--", where)
            if code == 0:
                return tuple(out.splitlines())
        base = self._tree() / relative
        if not base.is_dir():
            return ()
        return tuple(
            sorted(
                str(item.relative_to(self._root))
                for item in base.iterdir()
                if item.name not in _UNWALKED
            )
        )

    def read_file(self, path: str, *, offset: int, limit: int) -> str:
        relative = self._relative(path)
        text: str | None = None
        if self._revision:
            code, out = self._git("show", f"{self._revision}:./{relative}")
            if code == 0:
                text = out
        if text is None:
            candidate = self._tree() / relative
            if not candidate.is_file():
                return ""
            text = candidate.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        return "\n".join(lines[max(offset, 0) : max(offset, 0) + max(limit, 0)])

    def _every_path(self) -> tuple[str, ...]:
        if self._revision:
            code, out = self._git("ls-tree", "-r", "--name-only", self._revision)
            if code == 0:
                return tuple(out.splitlines())
        root = self._tree()
        return tuple(
            sorted(
                str(item.relative_to(root))
                for item in root.rglob("*")
                if item.is_file() and not _UNWALKED & set(item.parts)
            )
        )

    def find_paths(self, pattern: str, *, within: str | None, limit: int) -> tuple[str, ...]:
        prefix = self._relative(within or "")
        matched = [
            item
            for item in self._every_path()
            if (not prefix or item == prefix or item.startswith(f"{prefix}/"))
            and any(fnmatch.fnmatch(item, form) for form in _glob_forms(pattern))
        ]
        return tuple(matched[:limit])

    def search_lines(
        self,
        pattern: str,
        *,
        within: str | None,
        name_pattern: str | None,
        limit: int,
    ) -> tuple[SourceMatch, ...]:
        prefix = self._relative(within or "")
        if self._revision:
            arguments = ["grep", "-n", "-I", "--no-color", "-e", pattern, self._revision, "--"]
            arguments.extend(_pathspecs(prefix, name_pattern))
            code, out = self._git(*arguments)
            if code in (0, 1):
                return _matches(out, strip=f"{self._revision}:", limit=limit)
        self._tree()
        arguments = ["grep", "-n", "-I", "--no-color", "--untracked", "-e", pattern, "--"]
        arguments.extend(_pathspecs(prefix, name_pattern))
        code, out = self._git(*arguments)
        if code not in (0, 1):
            return ()
        return _matches(out, strip="", limit=limit)


def _pathspecs(prefix: str, name_pattern: str | None) -> list[str]:
    """What git should search, as pathspecs rather than as one concatenated string.

    Built separately because concatenating them produced `:(glob)/*.py`, which git accepts
    and matches nothing — a search that silently answers "no results" about the wrong thing.
    """

    if not name_pattern:
        return [prefix or "."]
    leading = f"{prefix}/" if prefix else ""
    return [f":(glob){leading}**/{name_pattern}", f":(glob){leading}{name_pattern}"]


def _matches(out: str, *, strip: str, limit: int) -> tuple[SourceMatch, ...]:
    found: list[SourceMatch] = []
    for line in out.splitlines():
        body = line.removeprefix(strip) if strip else line
        path, _, rest = body.partition(":")
        number, _, text = rest.partition(":")
        if not number.isdigit():
            continue
        found.append(SourceMatch(path=path, line=int(number), text=text))
        if len(found) == limit:
            break
    return tuple(found)
