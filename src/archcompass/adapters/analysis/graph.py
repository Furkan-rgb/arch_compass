"""Small deterministic graph algorithms used by atlas metrics and queries."""

from __future__ import annotations

from collections import deque


def reachable(graph: dict[str, set[str]], start: str, *, max_depth: int | None = None) -> set[str]:
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    while queue:
        current, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            continue
        for target in sorted(graph.get(current, set())):
            if target == start or target in seen:
                continue
            seen.add(target)
            queue.append((target, depth + 1))
    return seen


def reverse_graph(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {node: set() for node in graph}
    for source, targets in graph.items():
        for target in targets:
            result.setdefault(target, set()).add(source)
    return result


def shortest_path(graph: dict[str, set[str]], source: str, target: str) -> list[str]:
    if source == target:
        return [source]
    queue: deque[str] = deque([source])
    previous: dict[str, str | None] = {source: None}
    while queue:
        current = queue.popleft()
        for neighbour in sorted(graph.get(current, set())):
            if neighbour in previous:
                continue
            previous[neighbour] = current
            if neighbour == target:
                path = [target]
                cursor: str | None = current
                while cursor is not None:
                    path.append(cursor)
                    cursor = previous[cursor]
                return list(reversed(path))
            queue.append(neighbour)
    return []


def strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph.get(node, set())):
            if target not in indexes:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[target])
        if lowlinks[node] != indexes[node]:
            return
        component: list[str] = []
        while stack:
            item = stack.pop()
            on_stack.remove(item)
            component.append(item)
            if item == node:
                break
        components.append(sorted(component))

    all_nodes = sorted(set(graph).union(*(targets for targets in graph.values())))
    for node in all_nodes:
        if node not in indexes:
            visit(node)
    return sorted(components, key=lambda component: component[0])


def maximum_reachable_depth(graph: dict[str, set[str]], start: str) -> int:
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    best: dict[str, int] = {start: 0}
    maximum = 0
    while queue:
        node, depth = queue.popleft()
        for target in sorted(graph.get(node, set())):
            next_depth = depth + 1
            if next_depth <= best.get(target, -1):
                continue
            best[target] = next_depth
            maximum = max(maximum, next_depth)
            if next_depth <= len(graph):
                queue.append((target, next_depth))
    return min(maximum, len(graph))
