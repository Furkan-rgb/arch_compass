"""Fresh, persisted atlas query use cases."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from archcompass.analysis.atlas import (
    AtlasQuery,
    AtlasQueryResult,
    CyclesQuery,
    HotspotsQuery,
    NeighbourhoodQuery,
    NodeDetailsQuery,
    RelationQuery,
    RepositorySummaryQuery,
    ReviewContextQuery,
    SearchNodesQuery,
    ShortestPathQuery,
    SignalsQuery,
    SubsystemSummaryQuery,
)
from archcompass.domain.errors import AtlasNotFoundError
from archcompass.ports.atlas import AtlasFreshnessChecker, AtlasQueryService
from archcompass.ports.persistence import AtlasRepository


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

    def repository_identity(self, repository: Path) -> tuple[str, str]:
        """Return the stable repository/branch identity for an indexed path."""

        atlas = self._atlases.latest_for_path(repository.expanduser().resolve())
        if atlas is None or atlas.version.repo_id is None or atlas.version.branch_id is None:
            raise AtlasNotFoundError(
                "Index this repository before reviewing it so its repository and branch "
                "identities are known."
            )
        self._freshness.ensure_fresh(atlas)
        return atlas.version.repo_id, atlas.version.branch_id

    def inspect(self, repository: Path, node_id: str) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            NodeDetailsQuery(kind="node_details", node_id=node_id),
        )

    def review_context(
        self,
        repository: Path,
        node_ids: list[str],
        *,
        qualified_names: list[str] | None = None,
        limit: int = 25,
    ) -> AtlasQueryResult:
        """Everything a map of these nodes needs, in one round trip.

        `inspect` answers about one node and returns that node, which leaves a caller drawing
        a map with edges whose other end it was never told about. This is the same request
        made about a whole set, with the neighbours included.
        """

        return self._execute_latest(
            repository,
            ReviewContextQuery(
                kind="review_context",
                node_ids=node_ids,
                qualified_names=qualified_names or [],
                limit=limit,
            ),
        )

    def hotspots(self, repository: Path, metric: str) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            HotspotsQuery(kind="hotspots", metric=metric, limit=20),
        )

    def children(
        self, repository: Path, node_id: str, *, limit: int = 50
    ) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            SubsystemSummaryQuery(
                kind="subsystem_summary", node_id=node_id, limit=limit
            ),
        )

    def relationships(
        self,
        repository: Path,
        node_id: str,
        *,
        kind: Literal[
            "direct_dependencies",
            "direct_dependants",
            "known_callers",
            "implementations",
            "related_tests",
        ],
        limit: int = 50,
    ) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            RelationQuery(kind=kind, node_id=node_id, limit=limit),
        )

    def neighbourhood(
        self,
        repository: Path,
        node_id: str,
        *,
        direction: Literal["forward_neighbourhood", "reverse_neighbourhood"],
        depth: int = 1,
        limit: int = 50,
    ) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            NeighbourhoodQuery(
                kind=direction,
                node_id=node_id,
                depth=depth,
                limit=limit,
            ),
        )

    def search(
        self, repository: Path, terms: list[str], *, limit: int = 30
    ) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            SearchNodesQuery(kind="search_nodes", terms=terms, limit=limit),
        )

    def shortest_path(
        self, repository: Path, source_id: str, target_id: str
    ) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            ShortestPathQuery(
                kind="shortest_dependency_path",
                source_id=source_id,
                target_id=target_id,
            ),
        )

    def cycles(self, repository: Path, *, limit: int = 50) -> AtlasQueryResult:
        return self._execute_latest(
            repository, CyclesQuery(kind="cyclic_components", limit=limit)
        )

    def signals(
        self,
        repository: Path,
        *,
        codes: list[str] | None = None,
        limit: int = 50,
    ) -> AtlasQueryResult:
        return self._execute_latest(
            repository,
            SignalsQuery(kind="signals", codes=codes or [], limit=limit),
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
