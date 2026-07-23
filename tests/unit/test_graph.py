from archcompass.adapters.repository.graph import (
    reachable,
    shortest_path,
    strongly_connected_components,
)


def test_graph_algorithms_are_deterministic() -> None:
    graph = {"a": {"b"}, "b": {"c"}, "c": {"a", "d"}, "d": set()}
    assert reachable(graph, "a") == {"b", "c", "d"}
    assert shortest_path(graph, "a", "d") == ["a", "b", "c", "d"]
    assert ["a", "b", "c"] in strongly_connected_components(graph)

