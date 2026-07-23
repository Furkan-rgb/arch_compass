"""Fresh, persisted atlas query use cases."""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.atlas import (
    AtlasQuery,
    AtlasQueryResult,
    HotspotsQuery,
    NodeDetailsQuery,
    RepositorySummaryQuery,
)
from archcompass.domain.errors import AtlasNotFoundError
from archcompass.ports.atlas import AtlasFreshnessChecker, AtlasQueryService
from archcompass.ports.repositories import AtlasRepository


class AtlasService:
    def __init__(
        self,
        *,
        atlases: AtlasRepository,
        queries: AtlasQueryService,
        freshness: AtlasFreshnessChecker,
    ) -> None:
        self._atlases = atlases
        self._queries = queries
        self._freshness = freshness

    def summary(self, repository: Path) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            RepositorySummaryQuery(kind="repository_summary", limit=30),
        )

    def inspect(self, repository: Path, node_id: str) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            NodeDetailsQuery(kind="node_details", node_id=node_id),
        )

    def hotspots(self, repository: Path, metric: str) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            HotspotsQuery(kind="hotspots", metric=metric, limit=20),
        )

    def _execute_latest(
        self,
        repository: Path,
        query: AtlasQuery,
    ) -> AtlasQueryResult:
        atlas = self._atlases.latest_for_path(repository)
        if atlas is None:
            raise AtlasNotFoundError(f"No indexed atlas exists for {repository}")
        self._freshness.ensure_fresh(atlas)
        return self._queries.execute(atlas, query)
