"""Validated deterministic query layer over a repository atlas."""

from __future__ import annotations

from collections import defaultdict, deque
from itertools import pairwise
from pathlib import Path

from archcompass.analysis.adapters.graph import shortest_path
from archcompass.analysis.atlas import (
    DEPENDS_ON_EDGES,
    IMPLEMENTS_EDGES,
    Atlas,
    AtlasEdge,
    AtlasMetricValue,
    AtlasNode,
    AtlasNodeSummary,
    AtlasQuery,
    AtlasQueryResult,
    CyclesQuery,
    EdgeType,
    HotspotsQuery,
    MetricProfile,
    NeighbourhoodQuery,
    NodeDetailsQuery,
    NodeType,
    RelationQuery,
    RepositorySummaryQuery,
    ReviewContextQuery,
    SearchNodesQuery,
    ShortestPathQuery,
    SignalsQuery,
    SourceExcerpt,
    SourceLocation,
    SubsystemSummaryQuery,
)
from archcompass.analysis.metrics import (
    canonical_metric_name,
    metric_observation,
    profile_observations,
)
from archcompass.analysis.ports import AtlasFreshnessChecker, SourceReader
from archcompass.domain.errors import AtlasQueryValidationError

#: The relations `RelationQuery` accepts, in the order its enum states them. Named here so
#: that an empty answer can point at a sibling relation without importing the tool layer that
#: describes them to a model.
_RELATION_KINDS = (
    "direct_dependencies",
    "direct_dependants",
    "known_callers",
    "implementations",
    "related_tests",
)


class DeterministicAtlasQueryService:
    def __init__(
        self,
        source_reader: SourceReader,
        freshness_checker: AtlasFreshnessChecker | None = None,
    ) -> None:
        self._source_reader = source_reader
        self._freshness_checker = freshness_checker

    def execute(self, atlas: Atlas, query: AtlasQuery) -> AtlasQueryResult:
        nodes = {node.atlas_id: node for node in atlas.nodes}
        edges_by_source: defaultdict[str, list[AtlasEdge]] = defaultdict(list)
        edges_by_target: defaultdict[str, list[AtlasEdge]] = defaultdict(list)
        for edge in atlas.edges:
            edges_by_source[edge.source_id].append(edge)
            edges_by_target[edge.target_id].append(edge)
        kind = query.kind
        if isinstance(query, RepositorySummaryQuery):
            summary_priority = {
                NodeType.REPOSITORY: 0,
                NodeType.PACKAGE: 1,
                NodeType.MODULE: 2,
                NodeType.TEST_MODULE: 3,
                NodeType.CONFIGURATION: 4,
                NodeType.INTERFACE: 5,
                NodeType.CLASS: 6,
                NodeType.FUNCTION: 7,
                NodeType.METHOD: 8,
                NodeType.TEST_FUNCTION: 9,
            }
            selected = sorted(
                atlas.nodes,
                key=lambda node: (
                    summary_priority[node.node_type],
                    node.qualified_name,
                ),
            )[: query.limit]
            summary = (
                f"{len(atlas.nodes)} nodes, {len(atlas.edges)} edges, "
                f"{len(atlas.signals)} objective signals"
            )
            return AtlasQueryResult(
                query=query,
                node_ids=[node.atlas_id for node in selected],
                summary=summary,
                node_summaries=self._summaries(selected),
                relationships=self._relationships_within(
                    atlas, {node.atlas_id for node in selected}
                )[: query.limit],
                signals=atlas.signals[: query.limit],
            )
        if isinstance(query, SubsystemSummaryQuery):
            self._require_node(query.node_id, nodes)
            children = self._descendants(query.node_id, edges_by_source)[: query.limit]
            return AtlasQueryResult(
                query=query,
                node_ids=children,
                summary=f"{len(children)} descendants selected",
                node_summaries=self._summaries(
                    [nodes[node_id] for node_id in children if node_id in nodes]
                ),
                relationships=[
                    edge
                    for edge in atlas.edges
                    if edge.edge_type == EdgeType.CONTAINS and edge.target_id in set(children)
                ],
            )
        if isinstance(query, NodeDetailsQuery):
            node = self._require_node(query.node_id, nodes)
            profile = next((item for item in atlas.metrics if item.node_id == query.node_id), None)
            return AtlasQueryResult(
                query=query,
                node_ids=[node.atlas_id],
                # A sentence, not a serialised profile. This used to append
                # `profile.model_dump_json()` — every measurement as raw JSON, including the
                # atlas ids of the node and each of its dependants. Three things wrong with
                # that at once: it was the last place an internal handle reached a model that
                # has no tool taking one, it duplicated `metric_values` below in a shape
                # nothing renders, and on one lookup it was most of a thousand tokens of a
                # budget that has a size ceiling.
                summary=(
                    f"{node.node_type} {node.qualified_name} at {node.path}"
                    + ("" if profile else "; no measurements were recorded for it")
                ),
                node_summaries=self._summaries([node]),
                metric_values=self._profile_values(profile) if profile else [],
                relationships=sorted(
                    [
                        edge
                        for edge in atlas.edges
                        if query.node_id in {edge.source_id, edge.target_id}
                    ],
                    key=lambda edge: edge.edge_id,
                ),
                test_ids=self._test_ids(atlas, {query.node_id}, nodes),
                signals=[signal for signal in atlas.signals if signal.node_id == query.node_id],
            )
        if isinstance(query, ReviewContextQuery):
            # Tolerant lookup, unlike every other branch: the ids come from a stored review
            # and the atlas may have been rebuilt since it ran, so a renamed file must cost
            # the reader that one node rather than the whole map.
            # A name resolves to whichever nodes carry it, which is normally one. It is a
            # fallback for a finding recorded before the atlas id travelled with it, and it
            # is deliberately not the primary route: two nodes can answer to one qualified
            # name across a rebuild, and the map would then anchor on both.
            by_name: defaultdict[str, list[str]] = defaultdict(list)
            for node in atlas.nodes:
                by_name[node.qualified_name].append(node.atlas_id)
            named = [
                node_id
                for name in query.qualified_names
                for node_id in sorted(by_name.get(name, []))
            ]
            requested_ids = list(dict.fromkeys([*query.node_ids, *named]))
            found = [node_id for node_id in requested_ids if node_id in nodes]
            included = {node_id: nodes[node_id] for node_id in found}
            for node_id in found:
                touching = sorted(
                    [*edges_by_source[node_id], *edges_by_target[node_id]],
                    key=lambda edge: edge.edge_id,
                )
                admitted = 0
                for edge in touching:
                    if admitted == query.limit:
                        break
                    neighbour = edge.target_id if edge.source_id == node_id else edge.source_id
                    if neighbour in included or neighbour not in nodes:
                        continue
                    included[neighbour] = nodes[neighbour]
                    admitted += 1
            included_ids = set(included)
            profiles = {profile.node_id: profile for profile in atlas.metrics}
            return AtlasQueryResult(
                query=query,
                node_ids=found,
                summary=(
                    f"None of the {len(requested_ids)} requested nodes are in this atlas"
                    if not found
                    else (
                        f"{len(found)} of {len(requested_ids)} requested nodes found; "
                        f"{len(included)} nodes in context"
                    )
                ),
                node_summaries=self._summaries(list(included.values())),
                metric_values=[
                    value
                    for node_id in included
                    if (profile := profiles.get(node_id)) is not None
                    for value in self._profile_values(profile)
                ],
                relationships=self._relationships_within(atlas, included_ids),
                test_ids=self._test_ids(atlas, included_ids, nodes),
                signals=[
                    signal for signal in atlas.signals if signal.node_id in included_ids
                ],
            )
        if isinstance(query, RelationQuery):
            self._require_node(query.node_id, nodes)
            wanted, reverse = self._relation_filter(kind)
            candidates = (
                edges_by_target[query.node_id] if reverse else edges_by_source[query.node_id]
            )
            matching_edges = [edge for edge in candidates if edge.edge_type in wanted]
            node_ids = sorted(
                {edge.source_id if reverse else edge.target_id for edge in matching_edges}
            )[: query.limit]
            selected_ids = set(node_ids)
            return AtlasQueryResult(
                query=query,
                node_ids=node_ids,
                summary=(
                    f"{len(node_ids)} related nodes"
                    if node_ids
                    else self._nothing_related(kind, nodes[query.node_id], candidates)
                ),
                node_summaries=self._summaries(
                    [nodes[node_id] for node_id in node_ids if node_id in nodes]
                ),
                relationships=sorted(
                    [
                        edge
                        for edge in matching_edges
                        if (edge.source_id if reverse else edge.target_id) in selected_ids
                    ],
                    key=lambda edge: edge.edge_id,
                ),
                test_ids=self._test_ids(atlas, selected_ids, nodes),
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
                node_summaries=self._summaries(
                    [nodes[node_id] for node_id in node_ids if node_id in nodes]
                ),
                relationships=self._relationships_within(
                    atlas, {query.node_id, *node_ids}, dependency_only=True
                ),
                test_ids=self._test_ids(atlas, set(node_ids), nodes),
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
                node_summaries=self._summaries(
                    [nodes[node_id] for node_id in path if node_id in nodes]
                ),
                relationships=self._path_relationships(atlas, path),
                test_ids=self._test_ids(atlas, set(path), nodes),
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
                node_summaries=self._summaries(
                    [nodes[item.node_id] for item in selected if item.node_id in nodes]
                ),
                metric_values=[
                    observation
                    for item in selected
                    if (
                        observation := metric_observation(
                            item,
                            "dependency.cycle_size",
                        )
                    )
                    is not None
                ],
                relationships=self._relationships_within(
                    atlas, {item.node_id for item in selected}, dependency_only=True
                ),
                signals=[
                    signal
                    for signal in atlas.signals
                    if signal.node_id in {item.node_id for item in selected}
                    and signal.code == "cyclic-dependency"
                ],
            )
        if isinstance(query, SignalsQuery):
            wanted_codes = {code.casefold() for code in query.codes}
            matching = [
                signal
                for signal in atlas.signals
                if not wanted_codes or signal.code.casefold() in wanted_codes
            ][: query.limit]
            node_ids = list(dict.fromkeys(signal.node_id for signal in matching))
            return AtlasQueryResult(
                query=query,
                node_ids=node_ids,
                summary=(
                    f"{len(matching)} structural signals"
                    + (
                        f" matching {', '.join(sorted(wanted_codes))}"
                        if wanted_codes
                        else ""
                    )
                ),
                node_summaries=self._summaries(
                    [nodes[node_id] for node_id in node_ids if node_id in nodes]
                ),
                relationships=self._relationships_within(atlas, set(node_ids)),
                signals=matching,
                test_ids=self._test_ids(atlas, set(node_ids), nodes),
            )
        if isinstance(query, HotspotsQuery):
            metric_name = canonical_metric_name(query.metric)
            ranked: list[tuple[int | float, str, MetricProfile]] = []
            for profile in atlas.metrics:
                observation = metric_observation(profile, metric_name)
                if observation is not None:
                    ranked.append((observation.value, profile.node_id, profile))
            if not ranked:
                raise AtlasQueryValidationError(f"Unknown numeric atlas metric: {query.metric}")
            ranked.sort(key=lambda item: (-item[0], item[1]))
            selected = ranked[: query.limit]
            return AtlasQueryResult(
                query=query,
                node_ids=[node_id for _, node_id, _ in selected],
                summary=f"Ranked by {metric_name}",
                node_summaries=self._summaries(
                    [nodes[node_id] for _, node_id, _ in selected if node_id in nodes]
                ),
                metric_values=[
                    observation
                    for rank, (_, _, profile) in enumerate(selected, start=1)
                    if (
                        observation := metric_observation(
                            profile,
                            metric_name,
                            rank=rank,
                        )
                    )
                    is not None
                ],
                test_ids=self._test_ids(atlas, {node_id for _, node_id, _ in selected}, nodes),
            )
        if isinstance(query, SearchNodesQuery):
            terms = [term.casefold() for term in query.terms]
            # A module's constants are searchable through the module that defines them.
            #
            # A module-level constant is not an atlas node — nodes are modules, classes and
            # functions — so searching node names alone could not find one at all. That was
            # not a gap at the edge of the product: two of the three detectors are *about*
            # constants, `duplicated_knowledge` and `scattered_concept`, and the hinge
            # contract opens by telling the model to look up a qualified name from the
            # candidate. For every candidate of those two patterns the first lookup the
            # contract asks for came back "0 name/path matches", and the model then guessed
            # at node ids until something answered.
            #
            # The module node is the right answer rather than a consolation: it is where the
            # constant is defined, and it is the id every other lookup needs, since none of
            # them can take anything finer than a node.
            defined: dict[str, str] = {}
            for facts in atlas.module_facts:
                names = [constant.name for constant in facts.constants]
                if names:
                    defined[facts.node_id] = " ".join(names).casefold()
            matching = [
                node
                for node in atlas.nodes
                if all(
                    term
                    in (
                        f"{node.symbol_name} {node.qualified_name} {node.path} "
                        f"{defined.get(node.atlas_id, '')}"
                    ).casefold()
                    for term in terms
                )
            ]
            matching.sort(key=lambda node: (node.qualified_name, node.atlas_id))
            return AtlasQueryResult(
                query=query,
                node_ids=[node.atlas_id for node in matching[: query.limit]],
                summary=f"{len(matching)} name/path matches before limiting",
                node_summaries=self._summaries(matching[: query.limit]),
            )
        node = self._require_node(query.node_id, nodes)
        if node.start_line is None or node.end_line is None:
            raise AtlasQueryValidationError(f"Node {node.atlas_id} has no source span")
        start = max(1, node.start_line - query.context_lines)
        end = min(node.end_line + query.context_lines, start + query.max_lines - 1)
        # The revision the atlas was built from, asked for by name. These line numbers
        # belong to that revision and to no other, so this is the reading that is *right*
        # rather than the reading that is merely current — and it keeps answering after the
        # checkout has moved on, which is what a recorded lookup has to do to be repeatable.
        text = self._source_reader.at_revision(
            root=self._root(atlas),
            relative_path=node.path,
            start_line=start,
            end_line=end,
            revision=atlas.version.git_commit_sha or "",
            max_lines=query.max_lines,
        )
        if text is None:
            # No revision to read: an unversioned directory, or a commit git no longer has.
            # Then the working tree is the only source there is, and it may only be read
            # while it still is what was judged — the freshness check is what says so.
            if self._freshness_checker is not None:
                self._freshness_checker.ensure_fresh(atlas)
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
            node_summaries=self._summaries([node]),
            excerpts=[excerpt],
        )

    @staticmethod
    def _require_node(node_id: str, nodes: dict[str, AtlasNode]) -> AtlasNode:
        node = nodes.get(node_id)
        if node is None:
            raise AtlasQueryValidationError(f"Unknown atlas node ID: {node_id}")
        return node

    @classmethod
    def _nothing_related(
        cls, kind: str, node: AtlasNode, incident: list[AtlasEdge]
    ) -> str:
        """An empty relation answer that says what it looked for, and where the edges are.

        `0 related nodes` is a claim about the repository, and for three of these relations
        it was almost always a claim about the question instead. `calls` edges come from call
        expressions and `tests` edges are only ever recorded beside one, so neither reaches an
        abstraction — nobody calls a protocol. Asked `known_callers` and `related_tests` about
        an abstraction 42 times across the stored investigations, this service answered `0
        related nodes` every time, and a reader cannot tell that from "nothing uses it".

        So the empty answer names the edge kind it searched for, and then names the sibling
        relations that hold the edges this node actually has. Both halves are read off the
        atlas at query time rather than from a table of what is possible: a table would be a
        claim about the parser that goes stale the first time the parser changes, and this is
        only ever a statement about the snapshot in hand.
        """

        wanted, reverse = cls._relation_filter(kind)
        side = "target" if reverse else "source"
        searched = ", ".join(sorted(item.value for item in wanted))
        sentence = (
            f"0 related nodes: no {searched} edge in this snapshot has "
            f"{node.qualified_name} as its {side}."
        )
        present = {edge.edge_type for edge in incident}
        elsewhere = sorted(
            other
            for other in _RELATION_KINDS
            if other != kind
            and cls._relation_filter(other)[1] == reverse
            and cls._relation_filter(other)[0] & present
        )
        if not elsewhere:
            return sentence
        # Only the kinds some other relation would actually report. `contains` is incident to
        # nearly everything and no relation exposes it, so naming it would send the reader
        # after an edge they cannot ask for.
        reportable = {
            item
            for other in elsewhere
            for item in cls._relation_filter(other)[0] & present
        }
        holds = ", ".join(sorted(item.value for item in reportable))
        count = sum(1 for edge in incident if edge.edge_type in reportable)
        return (
            f"{sentence} It is the {side} of {count} {holds} edge(s), which "
            f"{' and '.join(repr(item) for item in elsewhere)} report."
        )

    @staticmethod
    def _relation_filter(kind: str) -> tuple[set[EdgeType], bool]:
        """Which edges answer one relation, and whether it is asked backwards.

        `references` belongs in both dependency directions and was in neither. An `imports`
        edge runs module to module and a `calls` edge runs callable to callable, so neither
        can ever reach a class or an abstraction: on this repository, every one of the 63
        abstractions had `direct_dependants` answer "nothing matched" while the candidate
        beside it reported four dependants, because all 125 edges reaching an abstraction
        were `references` and the filter excluded them. A judgement cannot read that as
        anything but the count being wrong, and the recorded investigations show it did —
        asking again, another way, until the budget ran out.

        `implementations` gained `inherits` for the same reason: the sole-implementation
        detector counts both, so an abstraction whose one implementor subclasses it was
        reported as having one implementation by the candidate and none by the tool.
        """

        mapping = {
            "direct_dependencies": (set(DEPENDS_ON_EDGES), False),
            "direct_dependants": (set(DEPENDS_ON_EDGES), True),
            "known_callers": ({EdgeType.CALLS}, True),
            "implementations": (set(IMPLEMENTS_EDGES), True),
            "related_tests": ({EdgeType.TESTS}, True),
        }
        return mapping[kind]

    @staticmethod
    def _descendants(node_id: str, edges: dict[str, list[AtlasEdge]]) -> list[str]:
        result: list[str] = []
        queue: deque[str] = deque([node_id])
        seen = {node_id}
        while queue:
            current = queue.popleft()
            children = sorted(
                edge.target_id for edge in edges[current] if edge.edge_type == EdgeType.CONTAINS
            )
            for child in children:
                if child in seen:
                    continue
                seen.add(child)
                result.append(child)
                queue.append(child)
        return result

    @staticmethod
    def _dependency_adjacency(atlas: Atlas, *, reverse: bool = False) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = {node.atlas_id: set() for node in atlas.nodes}
        for edge in atlas.edges:
            if edge.edge_type not in {EdgeType.IMPORTS, EdgeType.CALLS}:
                continue
            source, target = (
                (edge.target_id, edge.source_id) if reverse else (edge.source_id, edge.target_id)
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
    def _summaries(nodes: list[AtlasNode]) -> list[AtlasNodeSummary]:
        return [
            AtlasNodeSummary(
                node_id=node.atlas_id,
                qualified_name=node.qualified_name,
                node_type=node.node_type,
                path=node.path,
                location=(
                    SourceLocation(
                        path=node.path,
                        start_line=node.start_line,
                        end_line=node.end_line,
                    )
                    if node.start_line is not None and node.end_line is not None
                    else None
                ),
                is_public=node.is_public,
            )
            for node in nodes
        ]

    @staticmethod
    def _profile_values(profile: MetricProfile) -> list[AtlasMetricValue]:
        return profile_observations(profile)

    @staticmethod
    def _relationships_within(
        atlas: Atlas,
        node_ids: set[str],
        *,
        dependency_only: bool = False,
    ) -> list[AtlasEdge]:
        allowed_types = {EdgeType.IMPORTS, EdgeType.CALLS} if dependency_only else set(EdgeType)
        return sorted(
            [
                edge
                for edge in atlas.edges
                if edge.source_id in node_ids
                and edge.target_id in node_ids
                and edge.edge_type in allowed_types
            ],
            key=lambda edge: edge.edge_id,
        )

    @staticmethod
    def _path_relationships(atlas: Atlas, path: list[str]) -> list[AtlasEdge]:
        relationships: list[AtlasEdge] = []
        for source_id, target_id in pairwise(path):
            edge = next(
                (
                    candidate
                    for candidate in sorted(atlas.edges, key=lambda item: item.edge_id)
                    if candidate.source_id == source_id
                    and candidate.target_id == target_id
                    and candidate.edge_type in {EdgeType.IMPORTS, EdgeType.CALLS}
                ),
                None,
            )
            if edge is not None:
                relationships.append(edge)
        return relationships

    @staticmethod
    def _test_ids(atlas: Atlas, selected_ids: set[str], nodes: dict[str, AtlasNode]) -> list[str]:
        test_ids = {
            node_id
            for node_id in selected_ids
            if node_id in nodes
            and nodes[node_id].node_type in {NodeType.TEST_MODULE, NodeType.TEST_FUNCTION}
        }
        test_ids.update(
            edge.source_id
            for edge in atlas.edges
            if edge.edge_type == EdgeType.TESTS and edge.target_id in selected_ids
        )
        return sorted(test_ids)

    @staticmethod
    def _root(atlas: Atlas) -> Path:
        return Path(atlas.version.root_path)
