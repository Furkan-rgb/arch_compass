"""The review-context query: one question, a drawable subgraph.

Every other query in this language answers about a single node, and `node_details` answers
with that node alone. A caller drawing a map from those answers is handed edges whose other
endpoint it was never given, so it drops them and renders unconnected boxes. What is pinned
here is the shape that makes a map possible — anchors *and* their neighbours in one result,
edges only between nodes the result contains — and the tolerance the caller depends on: the
ids come from a stored review, the atlas may have been rebuilt since, and a node that has
gone must cost the reader that node rather than the whole map.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from archcompass.analysis.adapters.query_service import DeterministicAtlasQueryService
from archcompass.analysis.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasVersion,
    EdgeType,
    LocalStructuralMetrics,
    MetricProfile,
    NodeType,
    ObscuritySignal,
    RelationQuery,
    ReviewContextQuery,
)


class _NoSource:
    """The source reader this query never reaches — only `source_excerpt` reads files."""

    def excerpt(
        self,
        root: Path,
        relative_path: str,
        start_line: int,
        end_line: int,
        *,
        max_lines: int,
    ) -> str:
        raise AssertionError("A review-context query must not read source")


def _node(atlas_id: str, node_type: NodeType = NodeType.MODULE) -> AtlasNode:
    return AtlasNode(
        atlas_id=atlas_id,
        path=f"src/{atlas_id}.py",
        symbol_name=atlas_id,
        qualified_name=f"package.{atlas_id}",
        node_type=node_type,
        start_line=1,
        end_line=40,
        is_public=True,
        parser_version="test-parser",
    )


def _edge(
    edge_id: str,
    source: str,
    target: str,
    edge_type: EdgeType = EdgeType.IMPORTS,
) -> AtlasEdge:
    return AtlasEdge(
        edge_id=edge_id,
        source_id=source,
        target_id=target,
        edge_type=edge_type,
        confidence=1.0,
    )


def _atlas(
    nodes: list[AtlasNode],
    edges: list[AtlasEdge],
    *,
    metrics: list[MetricProfile] | None = None,
    signals: list[ObscuritySignal] | None = None,
) -> Atlas:
    return Atlas(
        version=AtlasVersion(
            repository_identity="test-repo",
            root_path="/repo",
            content_fingerprint="fingerprint",
            parser_version="test-parser",
            analysis_config_hash="config",
        ),
        nodes=nodes,
        edges=edges,
        metrics=metrics or [],
        signals=signals or [],
    )


def _service() -> DeterministicAtlasQueryService:
    return DeterministicAtlasQueryService(_NoSource())


def test_review_context_anchors_on_a_name_where_it_has_no_id() -> None:
    """The map of a review judged before a finding carried the atlas node it was found on.

    Those findings record only the qualified name, and without this the whole surface is a
    sentence saying it cannot draw. Resolving the name is strictly worse than the id — one
    name can answer to two nodes across a rebuild — so it is a fallback and the id, where
    there is one, is what is asked for.
    """

    atlas = _atlas(
        [_node("anchor_a"), _node("imported"), _node("stranger")],
        [_edge("e1", "anchor_a", "imported")],
    )

    result = _service().execute(
        atlas,
        ReviewContextQuery(kind="review_context", qualified_names=["package.anchor_a"]),
    )

    assert result.node_ids == ["anchor_a"]
    assert {summary.node_id for summary in result.node_summaries} == {"anchor_a", "imported"}


def test_review_context_refuses_a_request_that_anchors_on_nothing() -> None:
    """Neither an id nor a name is not a small map; it is a query with no subject, and the
    tolerant lookup below would answer it with an empty result that reads as "nothing is
    there" rather than as "you asked about nothing"."""

    with pytest.raises(ValidationError):
        ReviewContextQuery(kind="review_context")


def test_review_context_returns_the_anchors_with_their_neighbourhood() -> None:
    """Both directions, every edge type, plus whatever the included nodes carry.

    A boundary's dependants matter as much as its dependencies — a map drawn only forwards
    hides everything that would break — and `contains` matters as much as `imports`, because
    a module's place in the tree is part of what a reader is looking at.
    """

    atlas = _atlas(
        [
            _node("anchor_a"),
            _node("anchor_b"),
            _node("importer"),
            _node("imported"),
            _node("parent", NodeType.PACKAGE),
            _node("suite", NodeType.TEST_MODULE),
            _node("stranger"),
        ],
        [
            _edge("e1", "anchor_a", "imported"),
            _edge("e2", "importer", "anchor_a"),
            _edge("e3", "parent", "anchor_b", EdgeType.CONTAINS),
            _edge("e4", "suite", "anchor_b", EdgeType.TESTS),
            _edge("e5", "importer", "stranger"),
        ],
        metrics=[
            MetricProfile(
                node_id="anchor_a",
                local=LocalStructuralMetrics(physical_lines=40),
            )
        ],
        signals=[
            ObscuritySignal(code="undocumented", message="No docstring", node_id="imported"),
            ObscuritySignal(code="undocumented", message="No docstring", node_id="stranger"),
        ],
    )

    result = _service().execute(
        atlas,
        ReviewContextQuery(kind="review_context", node_ids=["anchor_a", "anchor_b"]),
    )

    assert result.node_ids == ["anchor_a", "anchor_b"]
    assert {summary.node_id for summary in result.node_summaries} == {
        "anchor_a",
        "anchor_b",
        "imported",
        "importer",
        "parent",
        "suite",
    }
    # The edge that leaves the neighbourhood is not reported: a client cannot draw it, and one
    # that received it would either invent an endpoint or silently discard the edge.
    assert [edge.edge_id for edge in result.relationships] == ["e1", "e2", "e3", "e4"]
    assert {value.node_id for value in result.metric_values} == {"anchor_a"}
    assert [signal.node_id for signal in result.signals] == ["imported"]
    assert result.test_ids == ["suite"]
    assert result.summary == "2 of 2 requested nodes found; 6 nodes in context"


def test_review_context_skips_an_id_the_atlas_no_longer_holds() -> None:
    """A renamed file costs the reader that node, not the map."""

    atlas = _atlas(
        [_node("anchor"), _node("neighbour")],
        [_edge("e1", "anchor", "neighbour")],
    )

    result = _service().execute(
        atlas,
        ReviewContextQuery(kind="review_context", node_ids=["anchor", "node_departed"]),
    )

    assert result.node_ids == ["anchor"]
    assert {summary.node_id for summary in result.node_summaries} == {"anchor", "neighbour"}
    assert result.summary == "1 of 2 requested nodes found; 2 nodes in context"


def test_review_context_of_wholly_stale_ids_says_so_rather_than_failing() -> None:
    """An empty result with a sentence, not an exception a tab would render as a crash."""

    atlas = _atlas([_node("survivor")], [])

    result = _service().execute(
        atlas,
        ReviewContextQuery(kind="review_context", node_ids=["gone_one", "gone_two"]),
    )

    assert result.node_ids == []
    assert result.node_summaries == []
    assert result.relationships == []
    assert result.summary == "None of the 2 requested nodes are in this atlas"


def test_review_context_bounds_neighbours_per_anchor_deterministically() -> None:
    """The bound holds per anchor, and which neighbours arrive does not vary between runs.

    Per anchor rather than in total, so one densely connected boundary cannot spend the whole
    budget and leave its siblings bare. Ordered by edge id, so two identical requests produce
    the same map — a limit applied to an unordered set would show a reader a different
    neighbourhood each time they opened the tab.
    """

    atlas = _atlas(
        [_node("hub"), _node("other"), *(_node(f"leaf{ordinal}") for ordinal in range(1, 6))],
        [
            *(_edge(f"e{ordinal}", "hub", f"leaf{ordinal}") for ordinal in range(1, 6)),
            _edge("f1", "other", "leaf5"),
        ],
    )

    result = _service().execute(
        atlas,
        ReviewContextQuery(kind="review_context", node_ids=["hub", "other"], limit=2),
    )

    assert [summary.node_id for summary in result.node_summaries] == [
        "hub",
        "other",
        "leaf1",
        "leaf2",
        "leaf5",
    ]


def test_what_depends_on_an_abstraction_includes_what_only_references_it() -> None:
    """The relation that could never answer about the thing it is most asked about.

    `imports` runs module to module and `calls` runs callable to callable, so on an
    abstraction — a class — neither can ever have an endpoint. Measured on ArchCompass's own
    source, all 63 abstractions had every incoming edge be `references`, and this query
    answered "nothing matched" for every one of them while the candidate beside it reported
    four dependants. A judgement cannot read that as anything but the count being wrong.
    """

    atlas = _atlas(
        [_node("port", NodeType.INTERFACE), _node("consumer", NodeType.METHOD)],
        [_edge("e1", "consumer", "port", EdgeType.REFERENCES)],
    )

    result = _service().execute(
        atlas, RelationQuery(kind="direct_dependants", node_id="port")
    )

    assert [summary.node_id for summary in result.node_summaries] == ["consumer"]


def test_the_implementations_of_an_abstraction_include_what_subclasses_it() -> None:
    """The detector counts both, so a query that counted one disagreed with the candidate."""

    atlas = _atlas(
        [_node("port", NodeType.INTERFACE), _node("child", NodeType.CLASS)],
        [_edge("e1", "child", "port", EdgeType.INHERITS)],
    )

    result = _service().execute(
        atlas, RelationQuery(kind="implementations", node_id="port")
    )

    assert [summary.node_id for summary in result.node_summaries] == ["child"]


def test_the_measurement_and_the_relation_that_names_it_count_the_same_edges() -> None:
    """The invariant that would have caught the defect, pinned where it can only be broken once.

    `dependants_of_abstraction` is a number on the candidate and `direct_dependants` is the
    relation an investigation calls to find out who those dependants are. They were computed
    from two independently written edge sets, so the count said four and the relation said
    nothing matched — and a judgement has no way to read that except as the count being
    wrong. They are one constant now; this says so, so that splitting them again fails here
    rather than in a review.
    """

    from archcompass.analysis.atlas import DEPENDS_ON_EDGES, IMPLEMENTS_EDGES

    depends, reverse = _service()._relation_filter("direct_dependants")
    assert depends == set(DEPENDS_ON_EDGES)
    assert reverse

    implements, reverse = _service()._relation_filter("implementations")
    assert implements == set(IMPLEMENTS_EDGES)
    assert reverse


def test_an_empty_relation_says_what_it_looked_for_rather_than_reporting_absence() -> None:
    """`0 related nodes` is a claim about the repository. Usually it was one about the question.

    A `tests` edge is only ever recorded beside a `calls` edge, and nothing calls a protocol,
    so this relation is empty on every abstraction there is. Asked about one 25 times across
    the stored investigations, it answered `0 related nodes` every time — indistinguishable
    from "nothing tests it", which is what the model reasonably took it for.
    """

    atlas = _atlas(
        [_node("port", NodeType.INTERFACE), _node("consumer", NodeType.METHOD)],
        [_edge("e1", "consumer", "port", EdgeType.REFERENCES)],
    )

    result = _service().execute(atlas, RelationQuery(kind="related_tests", node_id="port"))

    assert result.node_ids == []
    assert "no tests edge in this snapshot" in result.summary
    # And it says where the edges this node does have are reported, so the next lookup is a
    # better one rather than the same question asked another way.
    assert "'direct_dependants'" in result.summary
    assert "references" in result.summary
