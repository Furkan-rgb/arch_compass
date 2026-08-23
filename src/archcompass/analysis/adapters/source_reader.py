"""Bounded source reading that cannot escape the analysed repository."""

from __future__ import annotations

import subprocess
from pathlib import Path

from archcompass.domain.errors import PathValidationError

#: A read of one blob out of git, which is local and small. Long enough for a cold cache on
#: a large repository, short enough that a review never waits on it.
_GIT_TIMEOUT_SECONDS = 5


class SafeSourceReader:
    def excerpt(
        self,
        root: Path,
        relative_path: str,
        start_line: int,
        end_line: int,
        *,
        max_lines: int,
        numbered: bool = True,
    ) -> str:
        """Lines `start_line` to `end_line` of a file inside this repository, and no other.

        `numbered` decides only how the result is presented. An excerpt a person reads carries
        its line numbers, because a finding cites `path:line` and a panel without them makes
        the reader count. A caller hashing the code wants what the code says and nothing else:
        the gutter moves whenever anything above the span is inserted or removed, so a
        fingerprint over the numbered form would call a boundary changed because an unrelated
        import was added at the top of its file.

        One method rather than two, because the part worth getting right — refusing symlinks,
        refusing paths that resolve outside the root, bounding how much is read — is the same
        for both and must not exist twice.
        """

        canonical_root = root.resolve(strict=True)
        candidate = canonical_root / relative_path
        if candidate.is_symlink():
            raise PathValidationError(f"Refusing to read symlink: {relative_path}")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(canonical_root)
        except (OSError, ValueError) as error:
            raise PathValidationError(
                f"Source path escapes or is absent from repository: {relative_path}"
            ) from error
        if not resolved.is_file():
            raise PathValidationError(f"Source path is not a file: {relative_path}")
        return _span(
            resolved.read_text(encoding="utf-8").splitlines(),
            start_line,
            end_line,
            max_lines=max_lines,
            numbered=numbered,
        )

    def at_revision(
        self,
        root: Path,
        relative_path: str,
        start_line: int,
        end_line: int,
        *,
        revision: str,
        max_lines: int,
        numbered: bool = True,
    ) -> str | None:
        """The file as git recorded it at `revision`, or `None` if git cannot say.

        `:./path` rather than `:path`, because git reads the second from the root of the
        repository and the first from the directory it was invoked in — and a review may be
        of a subdirectory of a larger checkout.

        Nothing here is a failure worth raising. No git, no repository, a revision that was
        garbage-collected, a file that did not exist yet: each of them means this question
        has no answer, and the caller has a working tree to fall back to.
        """

        if not revision or relative_path.startswith("/") or ".." in Path(relative_path).parts:
            return None
        try:
            found = subprocess.run(
                ["git", "-C", str(root), "show", f"{revision}:./{relative_path}"],
                capture_output=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if found.returncode != 0:
            return None
        text = found.stdout.decode("utf-8", errors="replace")
        return _span(
            text.splitlines(), start_line, end_line, max_lines=max_lines, numbered=numbered
        )


def _span(
    lines: list[str], start_line: int, end_line: int, *, max_lines: int, numbered: bool
) -> str:
    """The requested window of a file's lines, however the lines were obtained."""

    first = max(1, start_line)
    last = min(len(lines), end_line, first + max_lines - 1)
    if not numbered:
        return "\n".join(lines[first - 1 : last])
    return "\n".join(f"{number:>5} | {lines[number - 1]}" for number in range(first, last + 1))

