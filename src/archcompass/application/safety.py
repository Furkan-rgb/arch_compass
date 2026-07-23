"""Path checks shared by repository and workspace use cases."""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.errors import PathValidationError


def validate_workspace_repository_separation(
    workspace: Path, repository: Path
) -> tuple[Path, Path]:
    canonical_workspace = workspace.expanduser().resolve()
    try:
        canonical_repository = repository.expanduser().resolve(strict=True)
    except OSError as error:
        raise PathValidationError(f"Repository does not exist: {repository}") from error
    if not canonical_repository.is_dir():
        raise PathValidationError(f"Repository path is not a directory: {repository}")
    try:
        canonical_workspace.relative_to(canonical_repository)
    except ValueError:
        return canonical_workspace, canonical_repository
    raise PathValidationError(
        "The ArchCompass workspace must not equal or be contained by the "
        f"analysed repository: {canonical_workspace}"
    )


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
