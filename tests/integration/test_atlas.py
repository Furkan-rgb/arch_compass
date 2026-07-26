from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.domain.atlas import (
    EdgeType,
    HotspotsQuery,
    NodeType,
    SourceExcerptQuery,
)
from archcompass.domain.errors import AtlasQueryValidationError, PathValidationError

FIXTURE = Path("eval/cases/speech-vendor/repository").resolve()


def test_ast_atlas_contains_structure_edges_metrics_and_signals(runtime) -> None:
    atlas = runtime.analyzer.analyze(FIXTURE)
    node_types = {node.node_type for node in atlas.nodes}
    edge_types = {edge.edge_type for edge in atlas.edges}
    assert {
        NodeType.REPOSITORY,
        NodeType.MODULE,
        NodeType.CLASS,
        NodeType.FUNCTION,
        NodeType.INTERFACE,
        NodeType.TEST_FUNCTION,
    } <= node_types
    assert {EdgeType.CONTAINS, EdgeType.IMPORTS, EdgeType.CALLS, EdgeType.IMPLEMENTS} <= edge_types
    assert any(profile.dependency.reverse_dependency_reach > 0 for profile in atlas.metrics)
    assert any(signal.code == "similarly-named-constant" for signal in atlas.signals)


def test_atlas_versions_are_immutable(runtime) -> None:
    first = runtime.analyzer.analyze(FIXTURE)
    second = runtime.analyzer.analyze(FIXTURE)
    runtime.atlas_repository.save(first)
    runtime.atlas_repository.save(second)
    assert first.version.version_id != second.version.version_id
    assert first.version.content_fingerprint == second.version.content_fingerprint
    assert runtime.atlas_repository.get(first.version.version_id) == first


def test_queries_validate_ids_and_bound_source(runtime) -> None:
    atlas = runtime.analyzer.analyze(FIXTURE)
    hotspots = runtime.query_service.execute(
        atlas, HotspotsQuery(kind="hotspots", metric="reverse_dependency_reach", limit=5)
    )
    assert hotspots.node_ids
    source_node = next(
        node
        for node in atlas.nodes
        if node.node_type == NodeType.FUNCTION and node.start_line is not None
    )
    excerpt = runtime.query_service.execute(
        atlas,
        SourceExcerptQuery(
            kind="source_excerpt",
            node_id=source_node.atlas_id,
            context_lines=0,
            max_lines=5,
        ),
    )
    assert len(excerpt.excerpts[0].text.splitlines()) <= 5
    with pytest.raises(AtlasQueryValidationError):
        runtime.query_service.execute(
            atlas,
            SourceExcerptQuery(
                kind="source_excerpt",
                node_id="node_invented",
                context_lines=0,
                max_lines=5,
            ),
        )
    with pytest.raises(PathValidationError):
        runtime.query_service._source_reader.excerpt(
            FIXTURE, "../outside.py", 1, 1, max_lines=1
        )
