from pathlib import Path

from archcompass.domain.atlas import EdgeType, NodeType

FIXTURE = Path("eval/cases/premature-abstraction/repository").resolve()


def test_fixture_has_one_direct_local_implementation_without_abstractions(runtime) -> None:
    atlas = runtime.analyzer.analyze(FIXTURE)

    implementations = [
        node
        for node in atlas.nodes
        if node.node_type in {NodeType.FUNCTION, NodeType.METHOD}
    ]
    assert [(node.qualified_name, node.path) for node in implementations] == [
        ("labels.format_task_label", "labels.py")
    ]

    tests = [node for node in atlas.nodes if node.node_type == NodeType.TEST_FUNCTION]
    assert {node.symbol_name for node in tests} == {
        "test_formats_the_local_task_name",
        "test_ignores_surrounding_whitespace",
    }
    assert all(
        any(
            edge.edge_type == EdgeType.CALLS
            and edge.source_id == test.atlas_id
            and edge.target_id == implementations[0].atlas_id
            for edge in atlas.edges
        )
        for test in tests
    )

    assert not any(node.node_type == NodeType.INTERFACE for node in atlas.nodes)
    assert not any(
        "factory" in node.symbol_name.casefold()
        or "registry" in node.symbol_name.casefold()
        for node in atlas.nodes
    )
    assert not any(node.node_type == NodeType.CONFIGURATION for node in atlas.nodes)
