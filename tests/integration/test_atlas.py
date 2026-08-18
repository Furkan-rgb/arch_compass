from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.models.catalog import DETERMINISTIC_MODEL
from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.boundary.atlas import (
    EdgeType,
    HotspotsQuery,
    NodeType,
    SourceExcerptQuery,
)
from archcompass.domain.errors import AtlasQueryValidationError, PathValidationError

FIXTURE = Path("eval/cases/speech-vendor/repository").resolve()


def _repository_around_its_own_workspace(tmp_path: Path) -> tuple[Path, Path, Runtime]:
    """A repository with an ArchCompass workspace living inside it, and its runtime.

    The workspace holds a `.py` and a `.toml` because those are exactly the suffixes the
    snapshot collects; a workspace of database files alone would pass the tests below
    without the exclusion doing anything.
    """

    repository = tmp_path / "project"
    (repository / "package").mkdir(parents=True)
    (repository / "package" / "service.py").write_text("VALUE = 1\n", encoding="utf-8")
    workspace = repository / "workspace"
    runtime = build_runtime(workspace, pin=pinned_model("fake", DETERMINISTIC_MODEL))
    (workspace / "notes.py").write_text("KEPT_OUT = 1\n", encoding="utf-8")
    (workspace / "settings.toml").write_text("[section]\nvalue = 1\n", encoding="utf-8")
    return repository, workspace, runtime


def test_a_repository_containing_its_own_workspace_is_indexed_without_it(
    tmp_path: Path,
) -> None:
    repository, _, runtime = _repository_around_its_own_workspace(tmp_path)
    version = runtime.repository_service.index(repository)
    atlas = runtime.atlas_repository.get(version.version_id)
    paths = {node.path for node in atlas.nodes}
    assert "package/service.py" in paths
    assert not any(path.startswith("workspace") for path in paths)


def test_writing_in_a_contained_workspace_does_not_move_the_content_fingerprint(
    tmp_path: Path,
) -> None:
    repository, workspace, runtime = _repository_around_its_own_workspace(tmp_path)
    first = runtime.repository_service.index(repository)
    (workspace / "notes.py").write_text("KEPT_OUT = 2\n", encoding="utf-8")
    (workspace / "run-output.json").write_text('{"run": 2}', encoding="utf-8")
    second = runtime.repository_service.index(repository)
    assert first.version_id != second.version_id
    assert first.content_fingerprint == second.content_fingerprint
    assert (
        runtime.analyzer.current_identity(repository).content_fingerprint
        == first.content_fingerprint
    )


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


def test_a_repository_that_is_its_own_workspace_keeps_its_files_and_drops_its_state(
    tmp_path: Path,
) -> None:
    """The case this project is: `make web` opens the repository itself as the workspace.

    The workspace cannot be excluded whole here without emptying the atlas, so what
    ArchCompass writes into it is what gets left out.
    """

    repository = tmp_path / "project"
    repository.mkdir()
    (repository / "service.py").write_text("VALUE = 1\n", encoding="utf-8")
    runtime = build_runtime(repository, pin=pinned_model("fake", DETERMINISTIC_MODEL))
    (repository / ".archcompass" / "leftover.py").write_text("STATE = 1\n", encoding="utf-8")

    first = runtime.repository_service.index(repository)
    atlas = runtime.atlas_repository.get(first.version_id)
    paths = {node.path for node in atlas.nodes}
    assert "service.py" in paths
    assert not any(path.startswith(".archcompass") for path in paths)

    (repository / ".archcompass" / "leftover.py").write_text("STATE = 2\n", encoding="utf-8")
    second = runtime.repository_service.index(repository)
    assert first.content_fingerprint == second.content_fingerprint


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
