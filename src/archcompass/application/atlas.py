"""Repository-evidence freshness checks."""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.atlas import Atlas
from archcompass.domain.errors import PathValidationError, StaleAtlasError
from archcompass.ports.atlas import RepositoryIdentityReader


class AtlasFreshnessService:
    def __init__(self, identities: RepositoryIdentityReader) -> None:
        self._identities = identities

    def ensure_fresh(self, atlas: Atlas) -> None:
        root = Path(atlas.version.root_path)
        try:
            current = self._identities.current_identity(root)
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

    def assert_fresh(self, atlas: Atlas) -> None:
        """Compatibility spelling for callers that model freshness as an assertion."""
        self.ensure_fresh(atlas)

    @staticmethod
    def _stale(atlas: Atlas, reason: str) -> StaleAtlasError:
        return StaleAtlasError(
            f"Atlas {atlas.version.version_id} is stale ({reason}); "
            f"rerun `archcompass repo index {atlas.version.root_path}`."
        )
