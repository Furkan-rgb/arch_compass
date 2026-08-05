"""Bounded source reading that cannot escape the analysed repository."""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.errors import PathValidationError


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
        lines = resolved.read_text(encoding="utf-8").splitlines()
        first = max(1, start_line)
        last = min(len(lines), end_line, first + max_lines - 1)
        if not numbered:
            return "\n".join(lines[first - 1 : last])
        return "\n".join(f"{number:>5} | {lines[number - 1]}" for number in range(first, last + 1))

