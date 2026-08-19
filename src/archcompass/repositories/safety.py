"""Path checks shared by repository and workspace use cases."""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.errors import PathValidationError


def validate_repository_directory(repository: Path) -> Path:
    """The analysed repository, canonical, refused here rather than mid-run.

    A workspace inside the analysed repository used to be refused alongside these checks.
    It no longer is: the workspace is excluded from the snapshot instead, so its files
    neither enter the atlas nor move the content fingerprint when a review writes to it.
    """

    try:
        canonical_repository = repository.expanduser().resolve(strict=True)
    except OSError as error:
        raise PathValidationError(f"Repository does not exist: {repository}") from error
    if not canonical_repository.is_dir():
        raise PathValidationError(f"Repository path is not a directory: {repository}")
    return canonical_repository


def safe_workspace_output_path(workspace: Path, relative_path: str | Path) -> Path:
    canonical_workspace = workspace.expanduser().resolve()
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise PathValidationError(
            f"Workspace output path must be relative and traversal-free: {relative_path}"
        )
    candidate = canonical_workspace.joinpath(relative)
    cursor = canonical_workspace
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PathValidationError(f"Workspace output path contains a symlink: {cursor}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(canonical_workspace)
    except ValueError as error:
        raise PathValidationError(
            f"Workspace output path escapes {canonical_workspace}: {relative_path}"
        ) from error
    return resolved
