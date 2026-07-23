"""Filesystem report output constrained to a validated workspace."""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.errors import PathValidationError


class SafeWorkspaceReportWriter:
    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace.expanduser().resolve(strict=True)

    def write(
        self,
        *,
        report_id: str,
        structured_json: str,
        markdown: str,
    ) -> None:
        if not report_id or "/" in report_id or "\\" in report_id or report_id in {".", ".."}:
            raise PathValidationError("Report ID is not a safe file name")
        report_directory = self._safe_path(Path("reports"))
        report_directory.mkdir(parents=False, exist_ok=True)
        self._reject_symlink(report_directory)
        json_path = self._safe_path(Path("reports") / f"{report_id}.json")
        markdown_path = self._safe_path(Path("reports") / f"{report_id}.md")
        json_path.write_text(structured_json.rstrip() + "\n", encoding="utf-8")
        markdown_path.write_text(markdown, encoding="utf-8")

    def _safe_path(self, relative: Path) -> Path:
        if relative.is_absolute() or ".." in relative.parts:
            raise PathValidationError(f"Workspace path escapes its root: {relative}")
        candidate = self._workspace / relative
        current = self._workspace
        for part in relative.parts:
            current = current / part
            if current.exists() or current.is_symlink():
                self._reject_symlink(current)
        try:
            candidate.resolve(strict=False).relative_to(self._workspace)
        except ValueError as error:
            raise PathValidationError(
                f"Workspace path escapes its root: {relative}"
            ) from error
        return candidate

    @staticmethod
    def _reject_symlink(path: Path) -> None:
        if path.is_symlink():
            raise PathValidationError(f"Workspace output path is a symlink: {path}")
