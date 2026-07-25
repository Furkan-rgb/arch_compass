from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.adapters.repository.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.adapters.repository.query_service import DeterministicAtlasQueryService
from archcompass.adapters.repository.source_reader import SafeSourceReader
from archcompass.application.atlas import AtlasFreshnessService
from archcompass.application.safety import (
    safe_workspace_output_path,
    validate_workspace_repository_separation,
)
from archcompass.domain.atlas import (
    Atlas,
    AtlasNode,
    AtlasVersion,
    CyclesQuery,
    EdgeType,
    HotspotsQuery,
    MetricNature,
    NeighbourhoodQuery,
    NodeDetailsQuery,
    NodeType,
    ObscuritySignal,
    RelationQuery,
    RepositorySummaryQuery,
    SearchNodesQuery,
    ShortestPathQuery,
    SignalsQuery,
    SourceExcerptQuery,
    SubsystemSummaryQuery,
)
from archcompass.domain.consultation import GlobalContext
from archcompass.domain.errors import (
    AtlasQueryValidationError,
    PathValidationError,
    StaleAtlasError,
)
from archcompass.workflows.consultation import ConsultationWorkflow

PROVIDER_CONTEXT_FIXTURE = Path(
    "eval/cases/provider-context-assembly/repository"
).resolve()


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


def _node(atlas: Atlas, qualified_name: str) -> AtlasNode:
    return next(node for node in atlas.nodes if node.qualified_name == qualified_name)


def _write_parallel_preparation_repository(root: Path) -> None:
    root.mkdir()
    (root / "ports.py").write_text(
        """
from typing import Protocol

class ReportQuestionPort(Protocol):
    def answer(self, run, question: str): ...

class SingleReportPort(Protocol):
    def explain(self, run, question: str): ...

class SplitInputPort(Protocol):
    def combine(self, left, right): ...

class UnrelatedMappingPort(Protocol):
    def send(self, run): ...

class FlatContextPort(Protocol):
    def answer_flat(self, context): ...

class ReboundInputPort(Protocol):
    def send_rebound(self, run): ...

class OverwrittenProjectionPort(Protocol):
    def send_overwritten(self, run): ...

class DestructuredAliasPort(Protocol):
    def send_destructured(self, run): ...

class ShadowedInputPort(Protocol):
    def send_shadowed(self, run): ...

class ThinPort(Protocol):
    def send(self, request): ...

class TypedPort(Protocol):
    def transform(self, value: int, label: str) -> str: ...
""".lstrip(),
        encoding="utf-8",
    )
    common_body = """
from ports import ReportQuestionPort

class {class_name}(ReportQuestionPort):
    def __init__(self, client):
        self.client = client

    def answer(self, {run_name}, question: str):
        context = {{
            "decision": {run_name}.report.decision.summary,
            "findings": {run_name}.report.analysis.findings,
            "evidence": {run_name}.report.evidence.items,
            "question": question,
        }}
        return self.client.complete(context)
"""
    (root / "ollama_adapter.py").write_text(
        common_body.format(class_name="OllamaAdapter", run_name="run").lstrip(),
        encoding="utf-8",
    )
    (root / "hosted_adapter.py").write_text(
        common_body.format(class_name="HostedAdapter", run_name="consultation").lstrip(),
        encoding="utf-8",
    )
    (root / "single_adapter.py").write_text(
        """
from ports import SingleReportPort

class SingleReportAdapter(SingleReportPort):
    def __init__(self, client):
        self.client = client

    def explain(self, run, question: str):
        context = {
            "decision": run.report.decision.summary,
            "findings": run.report.analysis.findings,
            "evidence": run.report.evidence.items,
            "question": question,
        }
        return self.client.complete(context)
""".lstrip(),
        encoding="utf-8",
    )
    (root / "negative_adapters.py").write_text(
        """
from ports import (
    DestructuredAliasPort,
    FlatContextPort,
    OverwrittenProjectionPort,
    ReboundInputPort,
    ShadowedInputPort,
    SplitInputPort,
    UnrelatedMappingPort,
)

class SplitInputAdapter(SplitInputPort):
    def combine(self, left, right):
        request = {
            "first": left.report.first,
            "second": right.report.second,
            "third": right.report.third,
        }
        return self.client.send(request)

class UnrelatedMappingAdapter(UnrelatedMappingPort):
    def send(self, run):
        selected = [
            run.report.first,
            run.report.second,
            run.report.third,
        ]
        unrelated = {"one": 1, "two": 2, "three": 3}
        self.log(unrelated)
        return self.client.send(selected)

class FlatContextAdapter(FlatContextPort):
    def answer_flat(self, context):
        request = {
            "question": context.question,
            "decision": context.decision,
            "claims": context.claims,
        }
        return self.client.send(request)

class PlainMapper:
    def project(self, run):
        request = {
            "decision": run.report.decision,
            "findings": run.report.findings,
            "policies": run.report.policies,
        }
        return request

class ReboundInputAdapter(ReboundInputPort):
    def send_rebound(self, run):
        run = self.load_default()
        request = {
            "decision": run.report.decision,
            "findings": run.report.findings,
            "policies": run.report.policies,
        }
        return self.client.send(request)

class OverwrittenProjectionAdapter(OverwrittenProjectionPort):
    def send_overwritten(self, run):
        request = {
            "decision": run.report.decision,
            "findings": run.report.findings,
            "policies": run.report.policies,
        }
        request = {"safe": True}
        return self.client.send(request)

class DestructuredAliasAdapter(DestructuredAliasPort):
    def send_destructured(self, run):
        decision, findings = run.report.decision, run.report.findings
        request = {
            "decision": decision,
            "findings": findings,
            "policies": run.report.policies,
        }
        return self.client.send(request)

class ShadowedInputAdapter(ShadowedInputPort):
    def send_shadowed(self, run):
        request = {
            "decision": [run.report.decision for run in self.examples],
            "findings": [run.report.findings for run in self.examples],
            "policies": [run.report.policies for run in self.examples],
        }
        return self.client.send(request)
""".lstrip(),
        encoding="utf-8",
    )
    (root / "thin_adapters.py").write_text(
        """
from ports import ThinPort

class FirstThinAdapter(ThinPort):
    def send(self, request):
        return request

class SecondThinAdapter(ThinPort):
    def send(self, request):
        return request

class IncompatibleLookalike:
    def transform(self, value: str, label: str) -> int:
        return len(value + label)
""".lstrip(),
        encoding="utf-8",
    )


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


def test_parallel_port_preparation_is_a_bounded_structural_proxy(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    _write_parallel_preparation_repository(repository)

    atlas = PythonAstRepositoryAnalyzer().analyze(repository)
    signals = [
        signal
        for signal in atlas.signals
        if signal.code == "parallel-boundary-preparation"
    ]

    assert len(signals) == 2
    assert {
        _node(atlas, "ollama_adapter.OllamaAdapter.answer").atlas_id,
        _node(atlas, "hosted_adapter.HostedAdapter.answer").atlas_id,
    } == {signal.node_id for signal in signals}
    assert all(signal.nature == "structural_proxy" for signal in signals)
    assert all("does not prove" in signal.limitations for signal in signals)
    assert all("report.analysis.findings" in signal.message for signal in signals)
    assert not any("ThinAdapter" in signal.message for signal in signals)
    broad_input_signals = [
        signal
        for signal in atlas.signals
        if signal.code == "broad-input-boundary-preparation"
    ]
    single = _node(atlas, "single_adapter.SingleReportAdapter.explain")
    assert len(broad_input_signals) == 3
    assert single.atlas_id in {
        signal.node_id for signal in broad_input_signals
    }
    assert any(
        "reads 3 nested input paths under run.report" in signal.message
        and signal.node_id == single.atlas_id
        for signal in broad_input_signals
    )
    assert all(signal.nature == "structural_proxy" for signal in broad_input_signals)
    assert not any(
        name in signal.message
        for signal in broad_input_signals
        for name in (
            "FlatContextAdapter",
            "DestructuredAliasAdapter",
            "OverwrittenProjectionAdapter",
            "PlainMapper",
            "ReboundInputAdapter",
            "ShadowedInputAdapter",
            "SplitInputAdapter",
            "ThinAdapter",
            "UnrelatedMappingAdapter",
        )
    )
    incompatible = _node(atlas, "thin_adapters.IncompatibleLookalike")
    typed_port = _node(atlas, "ports.TypedPort")
    assert not any(
        edge.edge_type == EdgeType.IMPLEMENTS
        and edge.source_id == incompatible.atlas_id
        and edge.target_id == typed_port.atlas_id
        for edge in atlas.edges
    )


def test_structural_provider_context_fixture_is_visible_before_a_case_names_it() -> None:
    atlas = PythonAstRepositoryAnalyzer().analyze(PROVIDER_CONTEXT_FIXTURE)
    queries = DeterministicAtlasQueryService(SafeSourceReader())

    overview = ConsultationWorkflow._atlas_overview(  # pyright: ignore[reportPrivateUsage]
        atlas
    )
    assert overview.signal_code_counts["broad-input-boundary-preparation"] == 1
    assert overview.signal_code_counts.get("parallel-boundary-preparation", 0) == 0
    overview_signal = next(
        signal
        for signal in overview.signals
        if signal.code == "broad-input-boundary-preparation"
    )
    assert overview_signal.nature == "structural_proxy"
    assert overview_signal.limitations

    result = queries.execute(
        atlas,
        SignalsQuery(
            kind="signals",
            codes=["broad-input-boundary-preparation"],
            limit=10,
        ),
    )
    assert len(result.node_ids) == 1
    assert len(result.node_summaries) == 1
    assert len(result.signals) == 1
    assert all(
        signal.code == "broad-input-boundary-preparation"
        for signal in result.signals
    )

    context = GlobalContext(
        case_id="case-generic-review",
        revision=1,
        title="Review repository architecture",
        problem="Assess the current architecture.",
        desired_outcome="Identify material architectural risks.",
        goals=[],
        constraints=[],
        future_changes=[],
        non_goals=[],
        confirmed_facts=[],
        assumptions=[],
        atlas_overview=overview,
        atlas_summary="Repository evidence is available.",
    )
    reasoner = DeterministicReasoningProvider()
    forces = reasoner.discover_design_forces(context)
    # The discovered force must name the signal the overview ranked first, which is
    # evidence the overview reached discovery. Asserting a fixed title would only
    # prove the fake still contains that string.
    leading_code = overview.signals[0].code
    assert any(leading_code in force.description for force in forces)
    clusters = reasoner.cluster_design_forces(context, forces)
    plans = reasoner.plan_atlas_queries(
        context,
        forces,
        clusters,
        iteration=1,
        prior_results={},
    )
    assert any(
        query.kind == "signals"
        and query.codes == ["broad-input-boundary-preparation"]
        for plan in plans
        for query in plan.plan.queries
        if isinstance(query, SignalsQuery)
    )


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

    old_parser_atlas = atlas.model_copy(
        update={
            "version": atlas.version.model_copy(
                update={"parser_version": "python-ast-legacy"}
            )
        }
    )
    with pytest.raises(StaleAtlasError, match="parser version"):
        freshness.ensure_fresh(old_parser_atlas)

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
    cycle_signals = [signal for signal in atlas.signals if signal.code == "cyclic-dependency"]
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
    entry_profile = next(profile for profile in atlas.metrics if profile.node_id == entry.atlas_id)
    target_profile = next(
        profile for profile in atlas.metrics if profile.node_id == target.atlas_id
    )
    boundary_profile = next(
        profile for profile in atlas.metrics if profile.node_id == boundary_entry.atlas_id
    )

    assert entry_profile.cognitive_scope.bounded_resolved_call_chain_nodes >= 2
    assert (
        entry_profile.cognitive_scope.bounded_resolved_call_chain_nodes
        == entry_profile.cognitive_scope.bounded_resolved_call_chain_nodes
    )
    assert boundary_profile.cognitive_scope.abstraction_boundaries == 1
    assert target_profile.change_amplification.public_call_targets_in_affected_modules >= 1
    assert (
        target_profile.change_amplification.public_call_targets_in_affected_modules
        == target_profile.change_amplification.public_call_targets_in_affected_modules
    )
    serialized = target_profile.model_dump(mode="json")
    assert "public_call_targets_in_affected_modules" in serialized["change_amplification"]
    assert "public_interfaces_crossed" not in serialized["change_amplification"]


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
        queries.execute(atlas, RepositorySummaryQuery(kind="repository_summary", limit=100)),
        queries.execute(
            atlas,
            SubsystemSummaryQuery(kind="subsystem_summary", node_id=root.atlas_id, limit=100),
        ),
        queries.execute(atlas, NodeDetailsQuery(kind="node_details", node_id=target.atlas_id)),
        queries.execute(
            atlas,
            RelationQuery(kind="direct_dependencies", node_id=caller.atlas_id, limit=100),
        ),
        queries.execute(
            atlas,
            RelationQuery(kind="direct_dependants", node_id=api.atlas_id, limit=100),
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
        queries.execute(atlas, SearchNodesQuery(kind="search_nodes", terms=["target"], limit=10)),
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
    assert results[12].metric_values[0].definition
    assert results[12].metric_values[0].nature in {
        "objective_measurement",
        "structural_proxy",
    }
    assert results[14].excerpts
    with pytest.raises(AtlasQueryValidationError, match="Unknown numeric atlas metric"):
        queries.execute(atlas, HotspotsQuery(kind="hotspots", metric="not_a_metric", limit=5))


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


def test_boundary_signals_outrank_default_codes_regardless_of_alphabet() -> None:
    """The Atlas overview ranks interpretive signals ahead of routine ones.

    The evaluation tier reads `overview.signals[0]` to decide which signal a
    consultation investigates first, so this ordering is a contract rather than a
    presentation detail. Pinning it here means relocating the priority table cannot
    silently change what those evaluations assert.

    The fixture is chosen so a plain alphabetical sort fails: `aaa-routine-code`
    sorts first by name and must still rank last by priority.
    """

    def signal(code: str) -> ObscuritySignal:
        return ObscuritySignal(
            code=code,
            message=f"{code} observed for the ranking fixture.",
            node_id="node-ranking",
            nature=MetricNature.STRUCTURAL_PROXY,
            definition="Fixture signal.",
        )

    atlas = Atlas(
        version=AtlasVersion(
            root_path="/tmp/ranking",
            repository_identity="ranking-fixture",
            content_fingerprint="ranking",
            parser_version="test",
            analysis_config_hash="ranking-config",
        ),
        nodes=[],
        edges=[],
        metrics=[],
        signals=[
            signal("aaa-routine-code"),
            signal("parallel-boundary-preparation"),
            signal("broad-input-boundary-preparation"),
        ],
    )

    ordered = [item.code for item in ConsultationWorkflow._atlas_overview(atlas).signals]  # pyright: ignore[reportPrivateUsage]

    assert ordered == [
        "broad-input-boundary-preparation",
        "parallel-boundary-preparation",
        "aaa-routine-code",
    ]
    assert ordered != sorted(ordered), "a plain alphabetical sort must not satisfy this"
