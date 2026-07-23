"""Validated deterministic query layer over a repository atlas."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

from archcompass.adapters.repository.graph import shortest_path
from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasQuery,
    AtlasQueryResult,
    CyclesQuery,
    EdgeType,
    HotspotsQuery,
    MetricProfile,
    NeighbourhoodQuery,
    NodeDetailsQuery,
    RelationQuery,
    RepositorySummaryQuery,
    SearchNodesQuery,
    ShortestPathQuery,
    SourceExcerpt,
    SourceLocation,
    SubsystemSummaryQuery,
)
from archcompass.domain.errors import AtlasQueryValidationError
from archcompass.ports.services import SourceReader


class DeterministicAtlasQueryService:
    def __init__(self, source_reader: SourceReader) -> None:
        self._source_reader = source_reader

    def execute(self, atlas: Atlas, query: AtlasQuery) -> AtlasQueryResult:
        nodes = {node.atlas_id: node for node in atlas.nodes}
        edges_by_source: defaultdict[str, list[AtlasEdge]] = defaultdict(list)
        edges_by_target: defaultdict[str, list[AtlasEdge]] = defaultdict(list)
        for edge in atlas.edges:
            edges_by_source[edge.source_id].append(edge)
            edges_by_target[edge.target_id].append(edge)
        kind = query.kind
        if isinstance(query, RepositorySummaryQuery):
            selected = sorted(
                atlas.nodes,
                key=lambda node: (node.node_type, node.qualified_name),
            )[: query.limit]
            summary = (
                f"{len(atlas.nodes)} nodes, {len(atlas.edges)} edges, "
                f"{len(atlas.signals)} objective signals"
            )
            return AtlasQueryResult(
                query=query, node_ids=[node.atlas_id for node in selected], summary=summary
            )
        if isinstance(query, SubsystemSummaryQuery):
            self._require_node(query.node_id, nodes)
            children = self._descendants(query.node_id, edges_by_source)[: query.limit]
            return AtlasQueryResult(
                query=query,
                node_ids=children,
                summary=f"{len(children)} descendants selected",
            )
        if isinstance(query, NodeDetailsQuery):
            node = self._require_node(query.node_id, nodes)
            profile = next(
                (item for item in atlas.metrics if item.node_id == query.node_id), None
            )
            return AtlasQueryResult(
                query=query,
                node_ids=[node.atlas_id],
                summary=(
                    f"{node.node_type} {node.qualified_name} at {node.path}; "
                    f"metrics={profile.model_dump_json() if profile else 'unavailable'}"
                ),
            )
        if isinstance(query, RelationQuery):
            self._require_node(query.node_id, nodes)
            wanted, reverse = self._relation_filter(kind)
            candidates = (
                edges_by_target[query.node_id]
                if reverse
                else edges_by_source[query.node_id]
            )
            node_ids = sorted(
                {
                    edge.source_id if reverse else edge.target_id
                    for edge in candidates
                    if edge.edge_type in wanted
                }
            )[: query.limit]
            return AtlasQueryResult(
                query=query, node_ids=node_ids, summary=f"{len(node_ids)} related nodes"
            )
        if isinstance(query, NeighbourhoodQuery):
            self._require_node(query.node_id, nodes)
            reverse = kind == "reverse_neighbourhood"
            adjacency = self._dependency_adjacency(atlas, reverse=reverse)
            node_ids = self._bounded_neighbourhood(
                adjacency, query.node_id, query.depth, query.limit
            )
            return AtlasQueryResult(
                query=query,
                node_ids=node_ids,
                summary=f"{len(node_ids)} nodes within dependency depth {query.depth}",
            )
        if isinstance(query, ShortestPathQuery):
            self._require_node(query.source_id, nodes)
            self._require_node(query.target_id, nodes)
            path = shortest_path(
                self._dependency_adjacency(atlas), query.source_id, query.target_id
            )
            return AtlasQueryResult(
                query=query,
                node_ids=path,
                summary="No dependency path found" if not path else f"Path length {len(path) - 1}",
            )
        if isinstance(query, CyclesQuery):
            profiles = [profile for profile in atlas.metrics if profile.dependency.cycle_size > 1]
            selected = sorted(
                profiles,
                key=lambda item: (
                    -item.dependency.cycle_size,
                    item.node_id,
                ),
            )[: query.limit]
            return AtlasQueryResult(
                query=query,
                node_ids=[item.node_id for item in selected],
                summary=f"{len(selected)} nodes participate in cycles",
            )
        if isinstance(query, HotspotsQuery):
            metric_name = query.metric.replace("-", "_")
            ranked: list[tuple[float, str]] = []
            for profile in atlas.metrics:
                value = self._metric_value(profile, metric_name)
                if value is not None:
                    ranked.append((float(value), profile.node_id))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            return AtlasQueryResult(
                query=query,
                node_ids=[node_id for _, node_id in ranked[: query.limit]],
                summary=f"Ranked by {metric_name}",
            )
        if isinstance(query, SearchNodesQuery):
            terms = [term.casefold() for term in query.terms]
            matching = [
                node
                for node in atlas.nodes
                if all(
                    term in f"{node.symbol_name} {node.qualified_name} {node.path}".casefold()
                    for term in terms
                )
            ]
            matching.sort(key=lambda node: (node.qualified_name, node.atlas_id))
            return AtlasQueryResult(
                query=query,
                node_ids=[node.atlas_id for node in matching[: query.limit]],
                summary=f"{len(matching)} name/path matches before limiting",
            )
        node = self._require_node(query.node_id, nodes)
        if node.start_line is None or node.end_line is None:
            raise AtlasQueryValidationError(f"Node {node.atlas_id} has no source span")
        start = max(1, node.start_line - query.context_lines)
        end = min(node.end_line + query.context_lines, start + query.max_lines - 1)
        text = self._source_reader.excerpt(
            root=self._root(atlas),
            relative_path=node.path,
            start_line=start,
            end_line=end,
            max_lines=query.max_lines,
        )
        excerpt = SourceExcerpt(
            node_id=node.atlas_id,
            location=SourceLocation(path=node.path, start_line=start, end_line=end),
            text=text,
        )
        return AtlasQueryResult(
            query=query,
            node_ids=[node.atlas_id],
            summary=f"Source excerpt for {node.qualified_name}",
            excerpts=[excerpt],
        )

    @staticmethod
    def _require_node(node_id: str, nodes: dict[str, AtlasNode]) -> AtlasNode:
        node = nodes.get(node_id)
        if node is None:
            raise AtlasQueryValidationError(f"Unknown atlas node ID: {node_id}")
        return node

    @staticmethod
    def _relation_filter(kind: str) -> tuple[set[EdgeType], bool]:
        mapping = {
            "direct_dependencies": ({EdgeType.IMPORTS, EdgeType.CALLS}, False),
            "direct_dependants": ({EdgeType.IMPORTS, EdgeType.CALLS}, True),
            "known_callers": ({EdgeType.CALLS}, True),
            "implementations": ({EdgeType.IMPLEMENTS}, True),
            "related_tests": ({EdgeType.TESTS}, True),
        }
        return mapping[kind]

    @staticmethod
    def _descendants(
        node_id: str, edges: dict[str, list[AtlasEdge]]
    ) -> list[str]:
        result: list[str] = []
        queue: deque[str] = deque([node_id])
        seen = {node_id}
        while queue:
            current = queue.popleft()
            children = sorted(
                edge.target_id
                for edge in edges[current]
                if edge.edge_type == EdgeType.CONTAINS
            )
            for child in children:
                if child in seen:
                    continue
                seen.add(child)
                result.append(child)
                queue.append(child)
        return result

    @staticmethod
    def _dependency_adjacency(
        atlas: Atlas, *, reverse: bool = False
    ) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = {
            node.atlas_id: set() for node in atlas.nodes
        }
        for edge in atlas.edges:
            if edge.edge_type not in {EdgeType.IMPORTS, EdgeType.CALLS}:
                continue
            source, target = (
                (edge.target_id, edge.source_id)
                if reverse
                else (edge.source_id, edge.target_id)
            )
            graph[source].add(target)
        return graph

    @staticmethod
    def _bounded_neighbourhood(
        graph: dict[str, set[str]], start: str, depth: int, limit: int
    ) -> list[str]:
        result: list[str] = []
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        seen = {start}
        while queue and len(result) < limit:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for target in sorted(graph.get(current, set())):
                if target in seen:
                    continue
                seen.add(target)
                result.append(target)
                queue.append((target, current_depth + 1))
                if len(result) == limit:
                    break
        return result

    @staticmethod
    def _metric_value(profile: MetricProfile, name: str) -> int | float | None:
        for group_name in ("local", "dependency", "change_amplification", "cognitive_scope"):
            group = getattr(profile, group_name)
            value = getattr(group, name, None)
            if isinstance(value, (int, float)):
                return value
        return None

    @staticmethod
    def _root(atlas: Atlas) -> Path:
        return Path(atlas.version.root_path)
