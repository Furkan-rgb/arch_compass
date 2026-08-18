"""Repository-evidence freshness checks."""

from __future__ import annotations

from pathlib import Path

from archcompass.boundary.atlas import Atlas
from archcompass.domain.errors import PathValidationError, StaleAtlasError
from archcompass.ports.atlas import RepositoryIdentityReader
from archcompass.ports.repositories import ScopeSelectionRepository


class AtlasFreshnessService:
    def __init__(
        self,
        identities: RepositoryIdentityReader,
        scope_selections: ScopeSelectionRepository,
    ) -> None:
        self._identities = identities
        self._scope_selections = scope_selections

    def ensure_fresh(self, atlas: Atlas) -> None:
        root = Path(atlas.version.root_path)
        # Under the same scope the atlas was built with, or the comparison is between the
        # digest of one set of files and the digest of another, and a repository reviewed
        # without its tests would be reported stale every time it was opened.
        excluded_paths = self._scope_selections.get(atlas.version.root_path) or ()
        try:
            current = self._identities.current_identity(root, excluded_paths=excluded_paths)
        except PathValidationError as error:
            raise self._stale(atlas, str(error)) from error
        mismatches: list[str] = []
        if current.content_fingerprint != atlas.version.content_fingerprint:
            mismatches.append("content fingerprint")
        if current.git_commit_sha != atlas.version.git_commit_sha:
            mismatches.append("Git commit")
        if (
            current.parser_version is not None
            and current.parser_version != atlas.version.parser_version
        ):
            mismatches.append("parser version")
        if (
            current.analysis_config_hash is not None
            and current.analysis_config_hash != atlas.version.analysis_config_hash
        ):
            mismatches.append("analysis configuration")
        if mismatches:
            raise self._stale(atlas, " and ".join(mismatches) + " changed")

    @staticmethod
    def _stale(atlas: Atlas, reason: str) -> StaleAtlasError:
        return StaleAtlasError(
            f"Atlas {atlas.version.version_id} is stale ({reason}); "
            f"rerun `archcompass repo index {atlas.version.root_path}`."
        )
