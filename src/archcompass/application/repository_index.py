"""Repository indexing use case."""

from __future__ import annotations

from pathlib import Path

from archcompass.application.safety import (
    validate_workspace_repository_separation,
)
from archcompass.domain.atlas import AtlasVersion
from archcompass.domain.workspace import RepositorySummary
from archcompass.ports.atlas import RepositoryAnalyzer
from archcompass.ports.repositories import AtlasRepository


class RepositoryIndexService:
    def __init__(
        self,
        *,
        workspace: Path,
        analyzer: RepositoryAnalyzer,
        atlases: AtlasRepository,
    ) -> None:
        self._workspace = workspace
        self._analyzer = analyzer
        self._atlases = atlases

    def index(self, repository: Path) -> AtlasVersion:
        _, canonical_repository = validate_workspace_repository_separation(
            self._workspace,
            repository,
        )
        atlas = self._analyzer.analyze(canonical_repository)
        self._atlases.save(atlas)
        return atlas.version

    def list(self, *, limit: int = 100) -> list[RepositorySummary]:
        return self._atlases.list_versions(limit=limit)
