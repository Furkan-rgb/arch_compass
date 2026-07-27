"""A detector reports a shape and how it knows. It never reports a verdict.

These pin the distinction the whole design rests on: `sole_implementation` fires on a dozen
abstractions in ArchCompass's own source, and every one of them is a deliberate hexagonal
port with a single adapter. If the pattern were treated as a violation the advisor would be
wrong a dozen times in one run, so the tests assert what a candidate carries — participants,
measurements, limitations — and never that it means anything.

The count is left approximate on purpose. It was written as an exact number once, and by
the time anyone read it again the number was wrong — which is how a stale claim in a
docstring quietly becomes evidence for the wrong conclusion.
"""

from __future__ import annotations

from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasVersion,
    EdgeType,
    FindingPattern,
    NodeType,
)
from archcompass.domain.finding_detectors import (
    detect_finding_candidates,
    sole_implementation_candidates,
)


def _node(
    atlas_id: str,
    name: str,
    node_type: NodeType,
    *,
    line: int = 10,
) -> AtlasNode:
    return AtlasNode(
        atlas_id=atlas_id,
        path=f"src/{name}.py",
        symbol_name=name,
        qualified_name=f"package.{name}",
        node_type=node_type,
        start_line=line,
        end_line=line + 20,
        is_public=True,
        parser_version="test-parser",
    )


def _edge(source: str, target: str, edge_type: EdgeType = EdgeType.IMPLEMENTS) -> AtlasEdge:
    return AtlasEdge(
        edge_id=f"{source}->{target}:{edge_type.value}",
        source_id=source,
        target_id=target,
        edge_type=edge_type,
        confidence=1.0,
    )


def _graph(implementor_count: int) -> tuple[dict[str, AtlasNode], list[AtlasEdge]]:
    nodes = {"port": _node("port", "Port", NodeType.INTERFACE)}
    edges: list[AtlasEdge] = []
    for ordinal in range(1, implementor_count + 1):
        node_id = f"impl{ordinal}"
        nodes[node_id] = _node(node_id, f"Adapter{ordinal}", NodeType.CLASS, line=ordinal * 100)
        edges.append(_edge(node_id, "port"))
    return nodes, edges


def test_an_abstraction_with_one_implementation_becomes_a_candidate() -> None:
    nodes, edges = _graph(1)

    candidates = sole_implementation_candidates(nodes, edges)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern is FindingPattern.SOLE_IMPLEMENTATION
    assert candidate.node_ids == ["port", "impl1"]
    assert [item.role for item in candidate.participants] == [
        "Declares the abstraction.",
        "The only implementation of it in this repository.",
    ]


def test_an_abstraction_with_two_implementations_is_not_a_candidate() -> None:
    """Two implementations is variation, which is what an abstraction is for."""

    nodes, edges = _graph(2)

    assert sole_implementation_candidates(nodes, edges) == []


def test_a_lone_subclass_of_a_plain_class_is_not_a_candidate() -> None:
    """The pattern is about declared abstractions, not about any class with one subclass.

    Without this the detector would fire on ordinary inheritance and drown the real
    signal in noise the case can do nothing with.
    """

    nodes = {
        "base": _node("base", "Base", NodeType.CLASS),
        "child": _node("child", "Child", NodeType.CLASS, line=200),
    }

    assert sole_implementation_candidates(nodes, [_edge("child", "base", EdgeType.INHERITS)]) == []


def test_an_abstraction_extending_another_abstraction_is_not_an_implementation() -> None:
    """Composition, not implementation — and a live false positive before this existed.

    `ports.reasoning` once split its reasoning port in two, and a real run reported the
    parent as an abstraction with exactly one implementation behind it — the protocol that
    extended it. Nothing concrete had been found; the advisor was about to reason about a
    protocol as though it were an adapter. (It was right that the split earned nothing, and
    the two are one protocol now, but for the other reason.)
    """

    nodes = {
        "port": _node("port", "Port", NodeType.INTERFACE),
        "wider": _node("wider", "WiderPort", NodeType.INTERFACE, line=200),
    }

    assert sole_implementation_candidates(nodes, [_edge("wider", "port")]) == []


def test_a_candidate_states_what_it_measured_and_what_it_cannot_see() -> None:
    """Evidence, not opinion — and honest about the method that produced it.

    A detector that claims no limitations is claiming the static view is complete. The
    stage that decides materiality needs to know a single adapter today may be a port
    whose second adapter is the entire point.
    """

    nodes, edges = _graph(1)
    edges += [
        _edge("caller", "port", EdgeType.IMPORTS),
        _edge("caller", "port", EdgeType.CALLS),
    ]

    candidate = sole_implementation_candidates(nodes, edges)[0]

    measured = {item.name: item.value for item in candidate.measurements}
    assert measured == {"implementations": 1, "dependants_of_abstraction": 2}
    assert all(item.limitations for item in candidate.measurements)
    assert "deliberate at a port boundary" in candidate.limitations


def test_a_candidate_carries_the_edges_between_its_participants() -> None:
    """Blast radius has to be visible without a second lookup (master plan 8A.2)."""

    nodes, edges = _graph(1)

    candidate = sole_implementation_candidates(nodes, edges)[0]

    assert [(edge.source_id, edge.target_id) for edge in candidate.relationships] == [
        ("impl1", "port")
    ]


def test_an_implementation_missing_from_the_graph_is_not_counted() -> None:
    """An edge to a node the snapshot does not contain proves nothing about arity."""

    nodes = {"port": _node("port", "Port", NodeType.INTERFACE)}

    assert sole_implementation_candidates(nodes, [_edge("absent", "port")]) == []


def test_the_catalogue_runs_every_detector_over_one_atlas() -> None:
    """Consumers call the catalogue, so a second pattern reaches them without a change."""

    nodes, edges = _graph(1)
    atlas = Atlas(
        version=AtlasVersion(
            repository_identity="test-repo",
            root_path="/repo",
            content_fingerprint="fingerprint",
            parser_version="test-parser",
            analysis_config_hash="config",
        ),
        nodes=list(nodes.values()),
        edges=edges,
        metrics=[],
    )

    assert [item.pattern for item in detect_finding_candidates(atlas)] == [
        FindingPattern.SOLE_IMPLEMENTATION
    ]
