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
    ) -> str:
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
        return "\n".join(f"{number:>5} | {lines[number - 1]}" for number in range(first, last + 1))

