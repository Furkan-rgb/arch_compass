from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from archcompass.adapters.repository.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.adapters.repository.query_service import DeterministicAtlasQueryService
from archcompass.adapters.repository.source_reader import SafeSourceReader
from archcompass.application.atlas import AtlasFreshnessService
from archcompass.application.safety import (
    safe_workspace_output_path,
    validate_workspace_repository_separation,
)
from archcompass.domain.atlas import (
    CyclesQuery,
    EdgeType,
    HotspotsQuery,
    NeighbourhoodQuery,
    NodeDetailsQuery,
    NodeType,
    RelationQuery,
    RepositorySummaryQuery,
    SearchNodesQuery,
    ShortestPathQuery,
    SourceExcerptQuery,
    SubsystemSummaryQuery,
)
from archcompass.domain.errors import (
    AtlasQueryValidationError,
    PathValidationError,
    StaleAtlasError,
)


def _write_repository(root: Path) -> None:
    root.mkdir()
    (root / "api.py").write_text(
        """
from typing import Protocol

class Port(Protocol):
    def execute(self) -> None: ...

def target() -> None:
    return None

def helper() -> None:
    target()
""".lstrip(),
        encoding="utf-8",
    )
    (root / "caller.py").write_text(
        """
from api import Port, helper, target
import cycle_a as first_cycle, cycle_b as second_cycle

class Adapter(Port):
    def execute(self) -> None:
        target()

def outer() -> None:
    def inner() -> None:
        target()
    inner()

def entry() -> None:
    Port()
    helper()
    target()
    target()

def boundary_entry() -> None:
    Port()
""".lstrip(),
        encoding="utf-8",
    )
    (root / "cycle_a.py").write_text("import cycle_b\n", encoding="utf-8")
    (root / "cycle_b.py").write_text("import cycle_a\n", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_api.py").write_text(
        """
from api import target

def test_target() -> None:
    target()
""".lstrip(),
        encoding="utf-8",
    )
    (root / "settings.yaml").write_text("feature: true\n", encoding="utf-8")


def _node(atlas, qualified_name: str):
    return next(node for node in atlas.nodes if node.qualified_name == qualified_name)


def test_indexing_snapshot_reads_each_discovered_file_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    _write_repository(repository)
    original = Path.read_bytes
    reads: dict[Path, int] = {}

    def counted(path: Path) -> bytes:
        reads[path] = reads.get(path, 0) + 1
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", counted)
    atlas = PythonAstRepositoryAnalyzer().analyze(repository)

    discovered = {
        path
        for path in repository.rglob("*")
        if path.is_file() and (path.suffix in {".py", ".yaml"})
    }
    assert reads == {path: 1 for path in discovered}
    assert atlas.version.schema_version == 2
    assert atlas.schema_version == 2


def test_freshness_rejects_changed_content_before_excerpt(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    _write_repository(repository)
    analyzer = PythonAstRepositoryAnalyzer()
    atlas = analyzer.analyze(repository)
    freshness = AtlasFreshnessService(analyzer)
    queries = DeterministicAtlasQueryService(SafeSourceReader(), freshness)
    target = _node(atlas, "api.target")
    excerpt_query = SourceExcerptQuery(
        kind="source_excerpt",
        node_id=target.atlas_id,
        context_lines=0,
        max_lines=10,
    )
    assert queries.execute(atlas, excerpt_query).excerpts

    (repository / "api.py").write_text(
        (repository / "api.py").read_text(encoding="utf-8") + "\nCHANGED = True\n",
        encoding="utf-8",
    )

    with pytest.raises(StaleAtlasError, match="repo index"):
        freshness.ensure_fresh(atlas)
    with pytest.raises(StaleAtlasError):
        queries.execute(atlas, excerpt_query)


def test_workspace_separation_and_output_paths_reject_escapes(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    nested_workspace = repository / "workspace"
    with pytest.raises(PathValidationError, match="must not equal or be contained"):
        validate_workspace_repository_separation(nested_workspace, repository)
    with pytest.raises(PathValidationError):
        validate_workspace_repository_separation(repository, repository)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    validate_workspace_repository_separation(workspace, repository)
    assert safe_workspace_output_path(workspace, "reports/result.md") == (
        workspace / "reports" / "result.md"
    )
    with pytest.raises(PathValidationError, match="traversal-free"):
        safe_workspace_output_path(workspace, "../result.md")
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "reports").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathValidationError, match="symlink"):
        safe_workspace_output_path(workspace, "reports/result.md")


def test_nested_repository_git_identity_ignores_unrelated_parent_commits(
    tmp_path: Path,
) -> None:
    git_root = tmp_path / "git-root"
    repository = git_root / "nested-repository"
    repository.mkdir(parents=True)
    (repository / "api.py").write_text("VALUE = 1\n", encoding="utf-8")
    (git_root / "README.md").write_text("initial\n", encoding="utf-8")

    def git(*arguments: str) -> None:
        subprocess.run(
            ["git", "-C", str(git_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    git("init")
    git("add", ".")
    git(
        "-c",
        "user.name=ArchCompass Tests",
        "-c",
        "user.email=tests@archcompass.local",
        "commit",
        "-m",
        "initial",
    )

    analyzer = PythonAstRepositoryAnalyzer()
    initial = analyzer.current_identity(repository)
    assert initial.git_commit_sha is not None

    (git_root / "README.md").write_text("unrelated parent change\n", encoding="utf-8")
    git("add", "README.md")
    git(
        "-c",
        "user.name=ArchCompass Tests",
        "-c",
        "user.email=tests@archcompass.local",
        "commit",
        "-m",
        "change parent",
    )
    after_parent_change = analyzer.current_identity(repository)
    assert after_parent_change == initial

    (repository / "api.py").write_text("VALUE = 2\n", encoding="utf-8")
    git("add", "nested-repository/api.py")
    git(
        "-c",
        "user.name=ArchCompass Tests",
        "-c",
        "user.email=tests@archcompass.local",
        "commit",
        "-m",
        "change nested repository",
    )
    after_repository_change = analyzer.current_identity(repository)
    assert after_repository_change.git_commit_sha != initial.git_commit_sha
    assert after_repository_change.content_fingerprint != initial.content_fingerprint


def test_lexical_call_ownership_import_metrics_tests_and_cycles(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    _write_repository(repository)
    atlas = PythonAstRepositoryAnalyzer().analyze(repository)
    outer = _node(atlas, "caller.outer")
    inner = _node(atlas, "caller.outer.inner")
    target = _node(atlas, "api.target")
    caller_module = _node(atlas, "caller")
    test_module = _node(atlas, "tests.test_api")
    test_function = _node(atlas, "tests.test_api.test_target")
    api_module = _node(atlas, "api")

    target_callers = {
        edge.source_id
        for edge in atlas.edges
        if edge.edge_type == EdgeType.CALLS and edge.target_id == target.atlas_id
    }
    assert inner.atlas_id in target_callers
    assert outer.atlas_id not in target_callers
    assert caller_module.atlas_id not in target_callers

    caller_metrics = next(
        profile for profile in atlas.metrics if profile.node_id == caller_module.atlas_id
    )
    assert caller_metrics.local.imported_module_count == 3
    assert any(
        edge.edge_type == EdgeType.TESTS
        and edge.source_id == test_module.atlas_id
        and edge.target_id == api_module.atlas_id
        for edge in atlas.edges
    )
    assert any(
        edge.edge_type == EdgeType.TESTS
        and edge.source_id == test_function.atlas_id
        and edge.target_id == target.atlas_id
        for edge in atlas.edges
    )
    cycle_signals = [
        signal for signal in atlas.signals if signal.code == "cyclic-dependency"
    ]
    assert len(cycle_signals) == 2


def test_call_path_and_public_interface_metrics_are_resolved_and_deterministic(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    _write_repository(repository)
    atlas = PythonAstRepositoryAnalyzer().analyze(repository)
    entry = _node(atlas, "caller.entry")
    boundary_entry = _node(atlas, "caller.boundary_entry")
    target = _node(atlas, "api.target")
    entry_profile = next(
        profile for profile in atlas.metrics if profile.node_id == entry.atlas_id
    )
    target_profile = next(
        profile for profile in atlas.metrics if profile.node_id == target.atlas_id
    )
    boundary_profile = next(
        profile for profile in atlas.metrics if profile.node_id == boundary_entry.atlas_id
    )

    assert entry_profile.cognitive_scope.symbols_in_representative_path >= 2
    assert boundary_profile.cognitive_scope.abstraction_boundaries == 1
    assert target_profile.change_amplification.public_interfaces_crossed >= 1


def test_every_query_kind_returns_typed_evidence(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    _write_repository(repository)
    atlas = PythonAstRepositoryAnalyzer().analyze(repository)
    queries = DeterministicAtlasQueryService(SafeSourceReader())
    root = next(node for node in atlas.nodes if node.node_type == NodeType.REPOSITORY)
    api = _node(atlas, "api")
    caller = _node(atlas, "caller")
    port = _node(atlas, "api.Port")
    target = _node(atlas, "api.target")

    results = [
        queries.execute(
            atlas, RepositorySummaryQuery(kind="repository_summary", limit=100)
        ),
        queries.execute(
            atlas,
            SubsystemSummaryQuery(
                kind="subsystem_summary", node_id=root.atlas_id, limit=100
            ),
        ),
        queries.execute(
            atlas, NodeDetailsQuery(kind="node_details", node_id=target.atlas_id)
        ),
        queries.execute(
            atlas,
            RelationQuery(
                kind="direct_dependencies", node_id=caller.atlas_id, limit=100
            ),
        ),
        queries.execute(
            atlas,
            RelationQuery(
                kind="direct_dependants", node_id=api.atlas_id, limit=100
            ),
        ),
        queries.execute(
            atlas,
            RelationQuery(kind="known_callers", node_id=target.atlas_id, limit=100),
        ),
        queries.execute(
            atlas,
            RelationQuery(kind="implementations", node_id=port.atlas_id, limit=100),
        ),
        queries.execute(
            atlas,
            RelationQuery(kind="related_tests", node_id=target.atlas_id, limit=100),
        ),
        queries.execute(
            atlas,
            NeighbourhoodQuery(
                kind="forward_neighbourhood",
                node_id=caller.atlas_id,
                depth=3,
                limit=100,
            ),
        ),
        queries.execute(
            atlas,
            NeighbourhoodQuery(
                kind="reverse_neighbourhood",
                node_id=api.atlas_id,
                depth=3,
                limit=100,
            ),
        ),
        queries.execute(
            atlas,
            ShortestPathQuery(
                kind="shortest_dependency_path",
                source_id=caller.atlas_id,
                target_id=api.atlas_id,
            ),
        ),
        queries.execute(atlas, CyclesQuery(kind="cyclic_components", limit=100)),
        queries.execute(
            atlas,
            HotspotsQuery(kind="hotspots", metric="reverse_dependency_reach", limit=5),
        ),
        queries.execute(
            atlas, SearchNodesQuery(kind="search_nodes", terms=["target"], limit=10)
        ),
        queries.execute(
            atlas,
            SourceExcerptQuery(
                kind="source_excerpt",
                node_id=target.atlas_id,
                context_lines=0,
                max_lines=10,
            ),
        ),
    ]

    assert all(result.node_summaries for result in results)
    assert results[2].metric_values
    assert results[3].relationships
    assert results[7].test_ids
    assert results[10].relationships
    assert results[12].metric_values[0].rank == 1
    assert results[14].excerpts
    with pytest.raises(AtlasQueryValidationError, match="Unknown numeric atlas metric"):
        queries.execute(
            atlas, HotspotsQuery(kind="hotspots", metric="not_a_metric", limit=5)
        )


def test_every_numeric_metric_is_queryable_deterministically(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    _write_repository(repository)
    atlas = PythonAstRepositoryAnalyzer().analyze(repository)
    queries = DeterministicAtlasQueryService(SafeSourceReader())
    sample = atlas.metrics[0]
    metric_names = {
        name
        for group_name in (
            "local",
            "dependency",
            "change_amplification",
            "cognitive_scope",
        )
        for name, value in getattr(sample, group_name).model_dump().items()
        if isinstance(value, (int, float))
    }

    first_run = {
        metric: queries.execute(
            atlas, HotspotsQuery(kind="hotspots", metric=metric, limit=100)
        ).metric_values
        for metric in metric_names
    }
    second_run = {
        metric: queries.execute(
            atlas, HotspotsQuery(kind="hotspots", metric=metric, limit=100)
        ).metric_values
        for metric in metric_names
    }

    assert all(first_run.values())
    assert first_run == second_run
