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
