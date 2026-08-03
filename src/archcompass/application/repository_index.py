"""Repository indexing use case."""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.atlas import AtlasVersion
from archcompass.domain.workspace import RepositorySummary
from archcompass.ports.atlas import RepositoryAnalyzer
from archcompass.ports.repositories import AtlasRepository


class RepositoryIndexService:
    def __init__(
        self,
        *,
        analyzer: RepositoryAnalyzer,
        atlases: AtlasRepository,
    ) -> None:
        self._analyzer = analyzer
        self._atlases = atlases

    def index(self, repository: Path) -> AtlasVersion:
        # The analyzer canonicalizes and validates the root, and excludes whatever subtrees
        # it was built to leave out; stating either again here would be a second copy of a
        # rule that has to hold in one place.
        atlas = self._analyzer.analyze(repository)
        self._atlases.save(atlas)
        return atlas.version

    def list(self, *, limit: int = 100) -> list[RepositorySummary]:
        return self._atlases.list_versions(limit=limit)
