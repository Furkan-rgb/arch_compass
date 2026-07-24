"""Deterministic Python repository atlas builder."""

from __future__ import annotations

import ast
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from hashlib import sha256
from itertools import combinations, pairwise
from pathlib import Path

from archcompass.adapters.repository.graph import (
    maximum_reachable_depth,
    reachable,
    reverse_graph,
    strongly_connected_components,
)
from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasVersion,
    ChangeAmplificationMetrics,
    CognitiveScopeMetrics,
    DependencyMetrics,
    EdgeType,
    LocalStructuralMetrics,
    MetricNature,
    MetricProfile,
    NodeType,
    ObscuritySignal,
    RepositoryContentIdentity,
    SourceLocation,
)
from archcompass.domain.base import canonical_json, stable_id
from archcompass.domain.errors import PathValidationError

PARSER_VERSION = "python-ast-3.12-v3"
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
}
CONFIG_SUFFIXES = {".yaml", ".yml", ".toml", ".json", ".ini", ".cfg", ".env"}


def _analysis_config_hash() -> str:
    return stable_id(
        "analysis",
        canonical_json(
            {
                "ignored": sorted(IGNORED_DIRECTORIES),
                "config_suffixes": sorted(CONFIG_SUFFIXES),
                "parser": PARSER_VERSION,
            }
        ),
    )


@dataclass
class ParsedModule:
    path: Path
    relative_path: str
    qualified_name: str
    node: AtlasNode
    tree: ast.Module
    source: str
    symbols: dict[str, AtlasNode] = field(default_factory=dict[str, AtlasNode])
    import_aliases: dict[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class SnapshotFile:
    path: Path
    relative_path: str
    content: bytes

    def text(self) -> str:
        return self.content.decode("utf-8")


@dataclass(frozen=True)
class RepositorySnapshot:
    root: Path
    python_files: tuple[SnapshotFile, ...]
    configuration_files: tuple[SnapshotFile, ...]
    content_fingerprint: str
    git_commit_sha: str | None


@dataclass(frozen=True)
class _BoundaryPreparationFingerprint:
    """Static features used to locate broad input-to-request preparation."""

    input_paths: frozenset[str]
    mapping_keys: frozenset[str]


@dataclass(frozen=True)
class _BoundaryProjection:
    """One located request projection fed by one broad input substructure."""

    input_root: str
    deep_paths: frozenset[str]
    static_keys: frozenset[str]
    input_derived_keys: frozenset[str]
    line: int


class PythonAstRepositoryAnalyzer:
    def analyze(self, root: Path) -> Atlas:
        snapshot = self._snapshot(root)
        canonical_root = snapshot.root
        python_files = snapshot.python_files
        config_files = snapshot.configuration_files
        repository_identity = stable_id("repo", str(canonical_root))
        version = AtlasVersion(
            repository_identity=repository_identity,
            root_path=str(canonical_root),
            git_commit_sha=snapshot.git_commit_sha,
            content_fingerprint=snapshot.content_fingerprint,
            parser_version=PARSER_VERSION,
            analysis_config_hash=_analysis_config_hash(),
        )
        root_node = self._node(
            path=".",
            name=canonical_root.name,
            qualified=canonical_root.name,
            kind=NodeType.REPOSITORY,
            parent_id=None,
            start=None,
            end=None,
            public=True,
            docstring=False,
        )
        nodes: dict[str, AtlasNode] = {root_node.atlas_id: root_node}
        edges: list[AtlasEdge] = []
        signals: list[ObscuritySignal] = []

        package_nodes = self._create_packages(
            canonical_root, [item.path for item in python_files], root_node
        )
        for package in package_nodes.values():
            nodes[package.atlas_id] = package
            edges.append(self._edge(package.parent_id, package.atlas_id, EdgeType.CONTAINS))

        modules: list[ParsedModule] = []
        for source_file in python_files:
            parsed = self._parse_module(
                canonical_root, source_file, package_nodes, root_node, signals
            )
            modules.append(parsed)
            nodes[parsed.node.atlas_id] = parsed.node
            edges.append(self._edge(parsed.node.parent_id, parsed.node.atlas_id, EdgeType.CONTAINS))
            for symbol in parsed.symbols.values():
                nodes[symbol.atlas_id] = symbol
                edges.append(self._edge(symbol.parent_id, symbol.atlas_id, EdgeType.CONTAINS))

        for source_file in config_files:
            path = source_file.path
            relative = source_file.relative_path
            parent = self._parent_for_path(path, canonical_root, package_nodes, root_node)
            source = source_file.text()
            node = self._node(
                path=relative,
                name=path.name,
                qualified=relative,
                kind=NodeType.CONFIGURATION,
                parent_id=parent.atlas_id,
                start=1,
                end=max(1, len(source.splitlines())),
                public=None,
                docstring=False,
                language="configuration",
            )
            nodes[node.atlas_id] = node
            edges.append(self._edge(parent.atlas_id, node.atlas_id, EdgeType.CONTAINS))

        module_by_name = {module.qualified_name: module for module in modules}
        symbol_by_qualified = {
            symbol.qualified_name: symbol
            for module in modules
            for symbol in module.symbols.values()
        }
        for module in modules:
            self._resolve_module_edges(
                module,
                module_by_name,
                symbol_by_qualified,
                edges,
                signals,
            )
        self._add_structural_protocol_edges(nodes, edges, modules)
        edges = self._deduplicate_edges(edges)
        self._add_duplicate_constant_signals(modules, signals)
        signals.extend(
            self._broad_input_boundary_preparation_signals(
                nodes,
                edges,
                modules,
            )
        )
        signals.extend(
            self._parallel_boundary_preparation_signals(
                nodes,
                edges,
                modules,
            )
        )
        metrics = self._compute_metrics(nodes, edges, modules)
        signals.extend(self._cycle_signals(nodes, edges, modules))
        return Atlas(
            version=version,
            nodes=sorted(nodes.values(), key=lambda item: item.atlas_id),
            edges=sorted(edges, key=lambda item: item.edge_id),
            metrics=sorted(metrics, key=lambda item: item.node_id),
            signals=sorted(signals, key=lambda item: (item.node_id, item.code, item.message)),
        )

    def current_identity(self, root: Path) -> RepositoryContentIdentity:
        snapshot = self._snapshot(root)
        return RepositoryContentIdentity(
            root_path=str(snapshot.root),
            content_fingerprint=snapshot.content_fingerprint,
            git_commit_sha=snapshot.git_commit_sha,
            parser_version=PARSER_VERSION,
            analysis_config_hash=_analysis_config_hash(),
        )

    def _snapshot(self, root: Path) -> RepositorySnapshot:
        canonical_root = self._validate_root(root)
        python_paths, config_paths = self._discover_files(canonical_root)
        files = tuple(
            SnapshotFile(
                path=path,
                relative_path=path.relative_to(canonical_root).as_posix(),
                content=path.read_bytes(),
            )
            for path in sorted([*python_paths, *config_paths])
        )
        python_path_set = set(python_paths)
        python_files = tuple(item for item in files if item.path in python_path_set)
        configuration_files = tuple(item for item in files if item.path not in python_path_set)
        return RepositorySnapshot(
            root=canonical_root,
            python_files=python_files,
            configuration_files=configuration_files,
            content_fingerprint=self._fingerprint(files),
            git_commit_sha=self._git_sha(canonical_root),
        )

    @staticmethod
    def _validate_root(root: Path) -> Path:
        try:
            canonical = root.expanduser().resolve(strict=True)
        except OSError as error:
            raise PathValidationError(f"Repository does not exist: {root}") from error
        if not canonical.is_dir():
            raise PathValidationError(f"Repository path is not a directory: {root}")
        return canonical

    @staticmethod
    def _discover_files(root: Path) -> tuple[list[Path], list[Path]]:
        python_files: list[Path] = []
        config_files: list[Path] = []
        for path in root.rglob("*"):
            relative_parts = path.relative_to(root).parts
            if any(part in IGNORED_DIRECTORIES for part in relative_parts):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix == ".py":
                python_files.append(path)
            elif path.suffix.casefold() in CONFIG_SUFFIXES or path.name == ".env":
                config_files.append(path)
        return sorted(python_files), sorted(config_files)

    @staticmethod
    def _fingerprint(files: tuple[SnapshotFile, ...]) -> str:
        digest = sha256()
        for source_file in files:
            digest.update(source_file.relative_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(source_file.content)
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _git_sha(root: Path) -> str | None:
        try:
            top_level_result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            top_level = Path(top_level_result.stdout.strip()).resolve(strict=True)
            if top_level == root:
                command = ["git", "-C", str(root), "rev-parse", "HEAD"]
            else:
                relative_root = root.relative_to(top_level).as_posix()
                command = [
                    "git",
                    "-C",
                    str(top_level),
                    "log",
                    "-1",
                    "--format=%H",
                    "--",
                    relative_root,
                ]
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        sha = result.stdout.strip()
        return sha if len(sha) == 40 else None

    def _create_packages(
        self, root: Path, python_files: list[Path], root_node: AtlasNode
    ) -> dict[str, AtlasNode]:
        directories: set[Path] = set()
        for file_path in python_files:
            parent = file_path.parent
            while parent != root:
                directories.add(parent)
                parent = parent.parent
        packages: dict[str, AtlasNode] = {}
        for directory in sorted(directories, key=lambda item: len(item.parts)):
            relative = directory.relative_to(root).as_posix()
            parent_relative = directory.parent.relative_to(root).as_posix()
            parent = packages.get(parent_relative, root_node)
            qualified = relative.replace("/", ".")
            package = self._node(
                path=relative,
                name=directory.name,
                qualified=qualified,
                kind=NodeType.PACKAGE,
                parent_id=parent.atlas_id,
                start=None,
                end=None,
                public=not directory.name.startswith("_"),
                docstring=False,
            )
            packages[relative] = package
        return packages

    def _parse_module(
        self,
        root: Path,
        source_file: SnapshotFile,
        packages: dict[str, AtlasNode],
        root_node: AtlasNode,
        signals: list[ObscuritySignal],
    ) -> ParsedModule:
        path = source_file.path
        relative = source_file.relative_path
        source = source_file.text()
        try:
            tree = ast.parse(source, filename=relative, type_comments=True)
        except SyntaxError as error:
            node = self._node(
                path=relative,
                name=path.stem,
                qualified=self._module_name(relative),
                kind=NodeType.MODULE,
                parent_id=self._parent_for_path(path, root, packages, root_node).atlas_id,
                start=1,
                end=max(1, len(source.splitlines())),
                public=not path.stem.startswith("_"),
                docstring=False,
            )
            signals.append(
                ObscuritySignal(
                    code="parse-error",
                    message=str(error),
                    node_id=node.atlas_id,
                    location=SourceLocation(
                        path=relative,
                        start_line=max(1, error.lineno or 1),
                        end_line=max(1, error.lineno or 1),
                    ),
                )
            )
            return ParsedModule(
                path,
                relative,
                node.qualified_name,
                node,
                ast.Module(body=[], type_ignores=[]),
                source,
            )
        qualified = self._module_name(relative)
        is_test = path.name.startswith("test_") or "tests" in Path(relative).parts
        is_config = path.stem in {"config", "settings", "configuration"}
        kind = (
            NodeType.TEST_MODULE
            if is_test
            else NodeType.CONFIGURATION
            if is_config
            else NodeType.MODULE
        )
        module_node = self._node(
            path=relative,
            name=path.stem,
            qualified=qualified,
            kind=kind,
            parent_id=self._parent_for_path(path, root, packages, root_node).atlas_id,
            start=1,
            end=max(1, len(source.splitlines())),
            public=not path.stem.startswith("_"),
            docstring=ast.get_docstring(tree) is not None,
        )
        parsed = ParsedModule(path, relative, qualified, module_node, tree, source)
        self._collect_symbols(parsed, tree.body, module_node, class_name=None, signals=signals)
        self._collect_local_signals(parsed, signals)
        return parsed

    def _collect_symbols(
        self,
        parsed: ParsedModule,
        statements: Iterable[ast.stmt],
        parent: AtlasNode,
        *,
        class_name: str | None,
        signals: list[ObscuritySignal],
    ) -> None:
        for statement in statements:
            if isinstance(statement, ast.ClassDef):
                bases = {self._dotted(base) for base in statement.bases}
                interface = any(
                    base and (base.endswith("Protocol") or base.endswith("ABC")) for base in bases
                ) or any(
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and any(
                        self._dotted(decorator).endswith("abstractmethod")
                        for decorator in item.decorator_list
                    )
                    for item in statement.body
                )
                qualified = f"{parent.qualified_name}.{statement.name}"
                node = self._node(
                    path=parsed.relative_path,
                    name=statement.name,
                    qualified=qualified,
                    kind=NodeType.INTERFACE if interface else NodeType.CLASS,
                    parent_id=parent.atlas_id,
                    start=statement.lineno,
                    end=statement.end_lineno,
                    public=not statement.name.startswith("_"),
                    docstring=ast.get_docstring(statement) is not None,
                )
                parsed.symbols[qualified] = node
                self._collect_symbols(
                    parsed,
                    statement.body,
                    node,
                    class_name=statement.name,
                    signals=signals,
                )
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{parent.qualified_name}.{statement.name}"
                is_test = (
                    statement.name.startswith("test_")
                    or parsed.node.node_type == NodeType.TEST_MODULE
                )
                node = self._node(
                    path=parsed.relative_path,
                    name=statement.name,
                    qualified=qualified,
                    kind=(
                        NodeType.TEST_FUNCTION
                        if is_test
                        else NodeType.METHOD
                        if parent.node_type in {NodeType.CLASS, NodeType.INTERFACE}
                        else NodeType.FUNCTION
                    ),
                    parent_id=parent.atlas_id,
                    start=statement.lineno,
                    end=statement.end_lineno,
                    public=not statement.name.startswith("_"),
                    docstring=ast.get_docstring(statement) is not None,
                )
                parsed.symbols[qualified] = node
                if node.is_public and not node.has_docstring and not is_test:
                    signals.append(
                        self._signal(
                            "public-function-without-docstring",
                            f"Public callable {qualified} has no docstring",
                            node,
                            statement.lineno,
                        )
                    )
                self._collect_symbols(
                    parsed,
                    statement.body,
                    node,
                    class_name=None,
                    signals=signals,
                )

    def _collect_local_signals(self, parsed: ParsedModule, signals: list[ObscuritySignal]) -> None:
        for statement in parsed.tree.body:
            if isinstance(statement, (ast.ImportFrom,)) and any(
                alias.name == "*" for alias in statement.names
            ):
                signals.append(
                    self._signal(
                        "wildcard-import",
                        "Wildcard import obscures the names introduced into the module",
                        parsed.node,
                        statement.lineno,
                    )
                )
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                value = statement.value
                if isinstance(value, (ast.List, ast.Dict, ast.Set)):
                    signals.append(
                        self._signal(
                            "module-mutable-state",
                            "Module-level mutable value",
                            parsed.node,
                            statement.lineno,
                        )
                    )
        for item in ast.walk(parsed.tree):
            if isinstance(item, ast.Call) and self._dotted(item.func) in {
                "__import__",
                "importlib.import_module",
            }:
                signals.append(
                    self._signal(
                        "dynamic-import",
                        "Dynamic import cannot be resolved deterministically",
                        parsed.node,
                        item.lineno,
                    )
                )

    def _resolve_module_edges(
        self,
        module: ParsedModule,
        module_by_name: dict[str, ParsedModule],
        symbol_by_qualified: dict[str, AtlasNode],
        edges: list[AtlasEdge],
        signals: list[ObscuritySignal],
    ) -> None:
        for statement in module.tree.body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    module.import_aliases[alias.asname or alias.name.split(".")[0]] = alias.name
                    target = self._best_module(alias.name, module_by_name)
                    if target:
                        import_edge = self._edge(
                            module.node.atlas_id,
                            target.node.atlas_id,
                            EdgeType.IMPORTS,
                            path=module.relative_path,
                            line=statement.lineno,
                        )
                        edges.append(import_edge)
                        if module.node.node_type == NodeType.TEST_MODULE:
                            edges.append(
                                import_edge.model_copy(
                                    update={
                                        "edge_id": stable_id(
                                            "edge",
                                            module.node.atlas_id,
                                            target.node.atlas_id,
                                            EdgeType.TESTS,
                                            module.relative_path,
                                            str(statement.lineno),
                                        ),
                                        "edge_type": EdgeType.TESTS,
                                    }
                                )
                            )
                        if module.node.node_type == NodeType.CONFIGURATION:
                            edges.append(
                                import_edge.model_copy(
                                    update={
                                        "edge_id": stable_id(
                                            "edge",
                                            module.node.atlas_id,
                                            target.node.atlas_id,
                                            EdgeType.CONFIGURES,
                                            module.relative_path,
                                            str(statement.lineno),
                                        ),
                                        "edge_type": EdgeType.CONFIGURES,
                                    }
                                )
                            )
            elif isinstance(statement, ast.ImportFrom):
                imported_module = self._resolve_from_name(module, statement)
                target = self._best_module(imported_module, module_by_name)
                if target:
                    import_edge = self._edge(
                        module.node.atlas_id,
                        target.node.atlas_id,
                        EdgeType.IMPORTS,
                        path=module.relative_path,
                        line=statement.lineno,
                    )
                    edges.append(import_edge)
                    if module.node.node_type == NodeType.TEST_MODULE:
                        edges.append(
                            import_edge.model_copy(
                                update={
                                    "edge_id": stable_id(
                                        "edge",
                                        module.node.atlas_id,
                                        target.node.atlas_id,
                                        EdgeType.TESTS,
                                        module.relative_path,
                                        str(statement.lineno),
                                    ),
                                    "edge_type": EdgeType.TESTS,
                                }
                            )
                        )
                    if module.node.node_type == NodeType.CONFIGURATION:
                        edges.append(
                            import_edge.model_copy(
                                update={
                                    "edge_id": stable_id(
                                        "edge",
                                        module.node.atlas_id,
                                        target.node.atlas_id,
                                        EdgeType.CONFIGURES,
                                        module.relative_path,
                                        str(statement.lineno),
                                    ),
                                    "edge_type": EdgeType.CONFIGURES,
                                }
                            )
                        )
                for alias in statement.names:
                    module.import_aliases[alias.asname or alias.name] = (
                        f"{imported_module}.{alias.name}".strip(".")
                    )
        all_symbols = [module.node, *module.symbols.values()]
        for source_node in all_symbols:
            ast_node = self._ast_for_node(module, source_node)
            if ast_node is None:
                continue
            scoped_nodes = list(self._lexical_nodes(ast_node))
            for item in scoped_nodes:
                if isinstance(item, ast.Call):
                    dotted = self._dotted(item.func)
                    target, confidence = self._resolve_symbol(
                        dotted, source_node, module, symbol_by_qualified
                    )
                    if target:
                        edges.append(
                            self._edge(
                                source_node.atlas_id,
                                target.atlas_id,
                                EdgeType.CALLS,
                                confidence=confidence,
                                path=module.relative_path,
                                line=item.lineno,
                            )
                        )
                        if source_node.node_type in {
                            NodeType.TEST_FUNCTION,
                            NodeType.TEST_MODULE,
                        }:
                            edges.append(
                                self._edge(
                                    source_node.atlas_id,
                                    target.atlas_id,
                                    EdgeType.TESTS,
                                    confidence=confidence,
                                    path=module.relative_path,
                                    line=item.lineno,
                                )
                            )
                    elif dotted and dotted not in {"print", "len", "str", "int", "list", "dict"}:
                        signals.append(
                            self._signal(
                                "unresolved-call",
                                f"Static call target could not be resolved: {dotted}",
                                source_node,
                                item.lineno,
                            )
                        )
            if isinstance(ast_node, ast.ClassDef):
                for base in ast_node.bases:
                    dotted = self._dotted(base)
                    target, confidence = self._resolve_symbol(
                        dotted, source_node, module, symbol_by_qualified
                    )
                    if target:
                        edges.append(
                            self._edge(
                                source_node.atlas_id,
                                target.atlas_id,
                                EdgeType.INHERITS,
                                confidence=confidence,
                                path=module.relative_path,
                                line=base.lineno,
                            )
                        )
                        if target.node_type == NodeType.INTERFACE:
                            edges.append(
                                self._edge(
                                    source_node.atlas_id,
                                    target.atlas_id,
                                    EdgeType.IMPLEMENTS,
                                    confidence=confidence,
                                    path=module.relative_path,
                                    line=base.lineno,
                                )
                            )
            for item in scoped_nodes:
                if not isinstance(item, ast.Name) or not isinstance(item.ctx, ast.Load):
                    continue
                target, confidence = self._resolve_symbol(
                    item.id, source_node, module, symbol_by_qualified
                )
                if target is None or target.atlas_id == source_node.atlas_id:
                    continue
                edges.append(
                    self._edge(
                        source_node.atlas_id,
                        target.atlas_id,
                        EdgeType.REFERENCES,
                        confidence=confidence,
                        path=module.relative_path,
                        line=item.lineno,
                    )
                )

    def _compute_metrics(
        self,
        nodes: dict[str, AtlasNode],
        edges: list[AtlasEdge],
        modules: list[ParsedModule],
    ) -> list[MetricProfile]:
        module_for_path = {module.relative_path: module.node.atlas_id for module in modules}
        module_ids = set(module_for_path.values())
        module_graph: dict[str, set[str]] = {module_id: set() for module_id in module_ids}
        impact_graph: dict[str, set[str]] = {module_id: set() for module_id in module_ids}
        for edge in edges:
            if edge.edge_type not in {EdgeType.IMPORTS, EdgeType.CALLS}:
                continue
            source = self._owning_module(nodes[edge.source_id], module_for_path)
            target = self._owning_module(nodes[edge.target_id], module_for_path)
            if source and target and source != target:
                impact_graph[source].add(target)
                if edge.edge_type == EdgeType.IMPORTS:
                    module_graph[source].add(target)
        reverse = reverse_graph(module_graph)
        impact_reverse = reverse_graph(impact_graph)
        components = strongly_connected_components(module_graph)
        component_by_node = {
            node_id: component for component in components for node_id in component
        }
        call_outgoing: defaultdict[str, set[str]] = defaultdict(set)
        call_incoming: defaultdict[str, set[str]] = defaultdict(set)
        test_targets: defaultdict[str, set[str]] = defaultdict(set)
        implementations: defaultdict[str, set[str]] = defaultdict(set)
        config_targets: defaultdict[str, set[str]] = defaultdict(set)
        for edge in edges:
            if edge.edge_type == EdgeType.CALLS:
                call_outgoing[edge.source_id].add(edge.target_id)
                call_incoming[edge.target_id].add(edge.source_id)
            elif edge.edge_type == EdgeType.TESTS:
                test_targets[edge.target_id].add(edge.source_id)
            elif edge.edge_type == EdgeType.IMPLEMENTS:
                implementations[edge.target_id].add(edge.source_id)
            elif edge.edge_type == EdgeType.CONFIGURES:
                config_targets[edge.target_id].add(edge.source_id)
        parsed_by_path = {module.relative_path: module for module in modules}
        profiles: list[MetricProfile] = []
        for node in nodes.values():
            parsed = parsed_by_path.get(node.path)
            syntax = self._ast_for_node(parsed, node) if parsed else None
            owner = self._owning_module(node, module_for_path)
            direct_dependencies = sorted(module_graph.get(owner or "", set()))
            direct_dependants = sorted(reverse.get(owner or "", set()))
            forward: set[str] = reachable(module_graph, owner) if owner else set[str]()
            backward: set[str] = reachable(reverse, owner) if owner else set[str]()
            affected: set[str] = reachable(impact_reverse, owner) if owner else set[str]()
            component = component_by_node.get(owner or "", [])
            associated_tests: set[str | None] = {
                self._owning_module(nodes[test_id], module_for_path)
                for test_id in test_targets.get(node.atlas_id, set())
            }
            reverse_tests: set[str] = {
                candidate
                for candidate in affected
                if nodes[candidate].node_type == NodeType.TEST_MODULE
            }
            local = self._local_metrics(node, syntax, parsed, call_outgoing, call_incoming)
            representative_path = self._representative_call_path(call_outgoing, node.atlas_id)
            affected_modules = {*affected, *([owner] if owner else [])}
            crossed_interfaces = {
                edge.target_id
                for edge in edges
                if edge.edge_type == EdgeType.CALLS
                and self._owning_module(nodes[edge.source_id], module_for_path) in affected_modules
                and self._owning_module(nodes[edge.target_id], module_for_path) in affected_modules
                and nodes[edge.target_id].is_public
                and nodes[edge.target_id].node_type
                in {
                    NodeType.CLASS,
                    NodeType.FUNCTION,
                    NodeType.INTERFACE,
                    NodeType.METHOD,
                }
            }
            profiles.append(
                MetricProfile(
                    node_id=node.atlas_id,
                    local=local,
                    dependency=DependencyMetrics(
                        fan_in=len(direct_dependants),
                        fan_out=len(direct_dependencies),
                        direct_dependencies=direct_dependencies,
                        direct_dependants=direct_dependants,
                        forward_dependency_reach=len(forward),
                        reverse_dependency_reach=len(backward),
                        dependency_depth=maximum_reachable_depth(module_graph, owner)
                        if owner
                        else 0,
                        strongly_connected_component=(
                            stable_id("scc", *component) if len(component) > 1 else None
                        ),
                        cycle_size=len(component) if len(component) > 1 else 0,
                        interface_implementations=len(implementations[node.atlas_id]),
                        public_interface_callers=len(call_incoming[node.atlas_id])
                        if node.is_public
                        else 0,
                        directly_associated_tests=len(associated_tests - {None}),
                        transitively_affected_test_modules=len(reverse_tests),
                    ),
                    change_amplification=ChangeAmplificationMetrics(
                        likely_affected_modules=len(affected),
                        public_call_targets_in_affected_modules=len(crossed_interfaces),
                        coordinated_implementations=len(implementations[node.atlas_id]),
                        configuration_locations=len(config_targets[node.atlas_id]),
                        reverse_neighbourhood_tests=len(reverse_tests),
                    ),
                    cognitive_scope=CognitiveScopeMetrics(
                        dependency_neighbourhood_modules=len(forward | backward),
                        bounded_resolved_call_chain_nodes=len(representative_path),
                        abstraction_boundaries=self._abstraction_crossings(
                            representative_path, nodes
                        ),
                        related_configuration_locations=len(config_targets[node.atlas_id]),
                        local_control_flow_complexity=local.branch_count,
                        public_api_surface=local.public_symbol_count,
                    ),
                )
            )
        return profiles

    @staticmethod
    def _cycle_signals(
        nodes: dict[str, AtlasNode],
        edges: list[AtlasEdge],
        modules: list[ParsedModule],
    ) -> list[ObscuritySignal]:
        module_ids = {module.node.atlas_id for module in modules}
        graph = {node_id: set[str]() for node_id in module_ids}
        import_edges: list[AtlasEdge] = []
        for edge in edges:
            if (
                edge.edge_type == EdgeType.IMPORTS
                and edge.source_id in module_ids
                and edge.target_id in module_ids
                and edge.source_id != edge.target_id
            ):
                graph[edge.source_id].add(edge.target_id)
                import_edges.append(edge)
        signals: list[ObscuritySignal] = []
        for component in strongly_connected_components(graph):
            if len(component) < 2:
                continue
            names = ", ".join(sorted(nodes[node_id].qualified_name for node_id in component))
            component_ids = set(component)
            for node_id in component:
                location = next(
                    (
                        edge.location
                        for edge in sorted(import_edges, key=lambda item: item.edge_id)
                        if edge.source_id == node_id and edge.target_id in component_ids
                    ),
                    None,
                )
                signals.append(
                    ObscuritySignal(
                        code="cyclic-dependency",
                        message=f"Module participates in an import cycle: {names}",
                        node_id=node_id,
                        location=location,
                    )
                )
        return signals

    @staticmethod
    def _representative_call_path(
        graph: dict[str, set[str]], start: str, *, limit: int = 20
    ) -> list[str]:
        paths: list[list[str]] = [[start]]
        seen = {start}
        best = [start]
        while paths:
            path = paths.pop(0)
            if len(path) > len(best) or (len(path) == len(best) and tuple(path) < tuple(best)):
                best = path
            if len(path) >= limit:
                continue
            for target in sorted(graph.get(path[-1], set())):
                if target in seen:
                    continue
                seen.add(target)
                paths.append([*path, target])
        return best

    @staticmethod
    def _abstraction_crossings(path: list[str], nodes: dict[str, AtlasNode]) -> int:
        def interface_owner(node_id: str) -> str | None:
            cursor = nodes.get(node_id)
            while cursor is not None:
                if cursor.node_type == NodeType.INTERFACE:
                    return cursor.atlas_id
                cursor = nodes.get(cursor.parent_id or "")
            return None

        crossings = 0
        for source_id, target_id in pairwise(path):
            source_owner = interface_owner(source_id)
            target_owner = interface_owner(target_id)
            if source_owner != target_owner and (
                source_owner is not None or target_owner is not None
            ):
                crossings += 1
        return crossings

    def _local_metrics(
        self,
        node: AtlasNode,
        syntax: ast.AST | None,
        parsed: ParsedModule | None,
        call_outgoing: dict[str, set[str]],
        call_incoming: dict[str, set[str]],
    ) -> LocalStructuralMetrics:
        if syntax is None:
            return LocalStructuralMetrics(
                physical_lines=(node.end_line or 0) - (node.start_line or 1) + 1
                if node.end_line
                else 0
            )
        scoped_nodes = list(self._lexical_nodes(syntax))
        statements = sum(isinstance(item, ast.stmt) for item in scoped_nodes)
        branches = sum(
            isinstance(
                item,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.Try,
                    ast.ExceptHandler,
                    ast.Match,
                    ast.match_case,
                ),
            )
            for item in scoped_nodes
        )
        parameters = 0
        if isinstance(syntax, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = syntax.args
            parameters = (
                len(args.posonlyargs)
                + len(args.args)
                + len(args.kwonlyargs)
                + int(args.vararg is not None)
                + int(args.kwarg is not None)
            )
        public_symbols = (
            sum(
                isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and not item.name.startswith("_")
                for item in getattr(syntax, "body", [])
            )
            if hasattr(syntax, "body")
            else 0
        )
        imports: set[str] = set()
        for item in scoped_nodes:
            if isinstance(item, ast.Import):
                imports.update(alias.name for alias in item.names)
            elif isinstance(item, ast.ImportFrom):
                imports.add(f"{'.' * item.level}{item.module or ''}")
        return LocalStructuralMetrics(
            physical_lines=(node.end_line or 0) - (node.start_line or 1) + 1
            if node.end_line
            else 0,
            logical_statements=statements,
            branch_count=branches,
            maximum_nesting_depth=self._nesting_depth(syntax),
            parameter_count=parameters,
            public_symbol_count=public_symbols,
            imported_module_count=len(imports),
            outgoing_static_calls=len(call_outgoing[node.atlas_id]),
            incoming_known_callers=len(call_incoming[node.atlas_id]),
        )

    @staticmethod
    def _nesting_depth(syntax: ast.AST) -> int:
        control = (
            ast.If,
            ast.For,
            ast.AsyncFor,
            ast.While,
            ast.Try,
            ast.With,
            ast.AsyncWith,
            ast.Match,
        )

        scope_boundaries = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

        def depth(node: ast.AST, current: int, *, root: bool = False) -> int:
            if not root and isinstance(node, scope_boundaries):
                return current
            next_current = current + 1 if isinstance(node, control) else current
            child_depths = (depth(child, next_current) for child in ast.iter_child_nodes(node))
            return max([next_current, *child_depths])

        return depth(syntax, 0, root=True)

    @staticmethod
    def _lexical_nodes(syntax: ast.AST) -> Iterable[ast.AST]:
        """Walk one lexical body while treating nested definitions as opaque."""
        boundaries = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        if isinstance(syntax, (ast.Module, *boundaries)):
            stack: list[ast.AST] = list(reversed(syntax.body))
        else:
            stack = list(reversed(list(ast.iter_child_nodes(syntax))))
        while stack:
            node = stack.pop()
            yield node
            if isinstance(node, boundaries):
                continue
            stack.extend(reversed(list(ast.iter_child_nodes(node))))

    @staticmethod
    def _module_name(relative_path: str) -> str:
        parts = relative_path.removesuffix(".py").split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) or "__root__"

    @staticmethod
    def _parent_for_path(
        path: Path,
        root: Path,
        packages: dict[str, AtlasNode],
        root_node: AtlasNode,
    ) -> AtlasNode:
        parent_relative = path.parent.relative_to(root).as_posix()
        return packages.get(parent_relative, root_node)

    @staticmethod
    def _node(
        *,
        path: str,
        name: str,
        qualified: str,
        kind: NodeType,
        parent_id: str | None,
        start: int | None,
        end: int | None,
        public: bool | None,
        docstring: bool,
        language: str = "python",
    ) -> AtlasNode:
        return AtlasNode(
            atlas_id=stable_id("node", kind, path, qualified),
            path=path,
            symbol_name=name,
            qualified_name=qualified,
            node_type=kind,
            start_line=start,
            end_line=end,
            parent_id=parent_id,
            is_public=public,
            has_docstring=docstring,
            language=language,  # type: ignore[arg-type]
            parser_version=PARSER_VERSION,
        )

    @staticmethod
    def _edge(
        source: str | None,
        target: str,
        kind: EdgeType,
        *,
        confidence: float = 1.0,
        path: str | None = None,
        line: int | None = None,
    ) -> AtlasEdge:
        if source is None:
            raise ValueError("Atlas edge source cannot be absent")
        location = (
            SourceLocation(path=path, start_line=line, end_line=line)
            if path is not None and line is not None
            else None
        )
        return AtlasEdge(
            edge_id=stable_id("edge", source, target, kind, path or "", str(line or 0)),
            source_id=source,
            target_id=target,
            edge_type=kind,
            confidence=confidence,
            location=location,
        )

    @staticmethod
    def _signal(code: str, message: str, node: AtlasNode, line: int) -> ObscuritySignal:
        return ObscuritySignal(
            code=code,
            message=message,
            node_id=node.atlas_id,
            location=SourceLocation(path=node.path, start_line=line, end_line=line),
        )

    @staticmethod
    def _dotted(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = PythonAstRepositoryAnalyzer._dotted(node.value)
            return f"{prefix}.{node.attr}".strip(".")
        return ""

    @staticmethod
    def _best_module(name: str, modules: dict[str, ParsedModule]) -> ParsedModule | None:
        if name in modules:
            return modules[name]
        candidates = [module for qname, module in modules.items() if qname.startswith(f"{name}.")]
        return sorted(candidates, key=lambda item: item.qualified_name)[0] if candidates else None

    @staticmethod
    def _resolve_from_name(module: ParsedModule, statement: ast.ImportFrom) -> str:
        if statement.level == 0:
            return statement.module or ""
        package = module.qualified_name.split(".")[:-1]
        trim = max(0, statement.level - 1)
        if trim:
            package = package[:-trim]
        if statement.module:
            package.extend(statement.module.split("."))
        return ".".join(package)

    @staticmethod
    def _resolve_symbol(
        dotted: str,
        source: AtlasNode,
        module: ParsedModule,
        symbols: dict[str, AtlasNode],
    ) -> tuple[AtlasNode | None, float]:
        if not dotted:
            return None, 0
        if dotted.startswith("self."):
            class_qname = source.qualified_name.rsplit(".", maxsplit=1)[0]
            candidate = f"{class_qname}.{dotted.removeprefix('self.')}"
            if candidate in symbols:
                return symbols[candidate], 1.0
        first, *remaining = dotted.split(".")
        if first in module.import_aliases:
            candidate = ".".join([module.import_aliases[first], *remaining])
            if candidate in symbols:
                return symbols[candidate], 1.0
        local = f"{module.qualified_name}.{dotted}"
        if local in symbols:
            return symbols[local], 1.0
        suffix = f".{dotted}"
        matches = [node for qname, node in symbols.items() if qname.endswith(suffix)]
        if len(matches) == 1:
            return matches[0], 0.7
        return None, 0

    @staticmethod
    def _ast_for_node(module: ParsedModule | None, node: AtlasNode) -> ast.AST | None:
        if module is None:
            return None
        if node.atlas_id == module.node.atlas_id:
            return module.tree
        for item in ast.walk(module.tree):
            if not isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.lineno == node.start_line and item.name == node.symbol_name:
                return item
        return None

    @staticmethod
    def _deduplicate_edges(edges: list[AtlasEdge]) -> list[AtlasEdge]:
        return list({edge.edge_id: edge for edge in edges}.values())

    @staticmethod
    def _owning_module(node: AtlasNode, modules: dict[str, str]) -> str | None:
        return modules.get(node.path)

    def _add_duplicate_constant_signals(
        self, modules: list[ParsedModule], signals: list[ObscuritySignal]
    ) -> None:
        constants: dict[str, list[tuple[ParsedModule, int]]] = defaultdict(list)
        for module in modules:
            for statement in module.tree.body:
                names: list[str] = []
                if isinstance(statement, ast.Assign):
                    names = [
                        target.id for target in statement.targets if isinstance(target, ast.Name)
                    ]
                elif isinstance(statement, ast.AnnAssign) and isinstance(
                    statement.target, ast.Name
                ):
                    names = [statement.target.id]
                for name in names:
                    if name.isupper():
                        constants[name].append((module, statement.lineno))
        for name, definitions in constants.items():
            if len(definitions) < 2:
                continue
            for module, line in definitions:
                signals.append(
                    self._signal(
                        "similarly-named-constant",
                        f"Constant {name} is defined in {len(definitions)} modules",
                        module.node,
                        line,
                    )
                )

    def _parallel_boundary_preparation_signals(
        self,
        nodes: dict[str, AtlasNode],
        edges: list[AtlasEdge],
        modules: list[ParsedModule],
    ) -> list[ObscuritySignal]:
        """Surface repeated preparation in sibling implementations as a bounded proxy.

        The atlas cannot establish semantic ownership. It can, however, observe that
        implementations of the same resolved port operation repeatedly read the same
        paths from a broad input and construct similarly keyed request data. That
        makes the relevant methods discoverable for a later evidence-grounded
        consultation.
        """

        parsed_by_path = {module.relative_path: module for module in modules}
        children_by_parent: defaultdict[str, list[AtlasNode]] = defaultdict(list)
        for node in nodes.values():
            if node.parent_id is not None:
                children_by_parent[node.parent_id].append(node)

        implementations_by_port: defaultdict[str, list[AtlasNode]] = defaultdict(list)
        for edge in edges:
            if edge.edge_type != EdgeType.IMPLEMENTS:
                continue
            implementation = nodes.get(edge.source_id)
            port = nodes.get(edge.target_id)
            if (
                implementation is not None
                and port is not None
                and port.node_type == NodeType.INTERFACE
            ):
                implementations_by_port[port.atlas_id].append(implementation)

        matches: defaultdict[
            str,
            list[tuple[AtlasNode, AtlasNode, frozenset[str], frozenset[str]]],
        ] = defaultdict(list)
        for port_id, implementation_classes in implementations_by_port.items():
            if len(implementation_classes) < 2:
                continue
            port = nodes[port_id]
            port_operations = {
                child.symbol_name
                for child in children_by_parent[port_id]
                if child.node_type == NodeType.METHOD
            }
            for operation in sorted(port_operations):
                methods = [
                    child
                    for implementation in implementation_classes
                    for child in children_by_parent[implementation.atlas_id]
                    if child.node_type == NodeType.METHOD
                    and child.symbol_name == operation
                ]
                fingerprints = {
                    method.atlas_id: self._boundary_preparation_fingerprint(
                        method,
                        parsed_by_path.get(method.path),
                    )
                    for method in methods
                }
                for first, second in combinations(methods, 2):
                    first_fingerprint = fingerprints[first.atlas_id]
                    second_fingerprint = fingerprints[second.atlas_id]
                    shared_paths = (
                        first_fingerprint.input_paths & second_fingerprint.input_paths
                    )
                    shared_keys = (
                        first_fingerprint.mapping_keys & second_fingerprint.mapping_keys
                    )
                    if not self._is_parallel_preparation_match(
                        first_fingerprint,
                        second_fingerprint,
                        shared_paths=shared_paths,
                        shared_keys=shared_keys,
                    ):
                        continue
                    matches[first.atlas_id].append(
                        (port, second, shared_paths, shared_keys)
                    )
                    matches[second.atlas_id].append(
                        (port, first, shared_paths, shared_keys)
                    )

        result: list[ObscuritySignal] = []
        for method_id, peers in sorted(matches.items()):
            method = nodes[method_id]
            port = peers[0][0]
            peer_names = sorted({peer.qualified_name for _, peer, _, _ in peers})
            observed_paths: set[str] = set()
            observed_keys: set[str] = set()
            for _, _, peer_paths, peer_keys in peers:
                observed_paths.update(peer_paths)
                observed_keys.update(peer_keys)
            path_sample = ", ".join(sorted(observed_paths)[:4])
            key_sample = ", ".join(sorted(observed_keys)[:4])
            observations = [
                f"{len(observed_paths)} shared input paths"
                + (f" ({path_sample})" if path_sample else ""),
                f"{len(observed_keys)} shared mapping keys"
                + (f" ({key_sample})" if key_sample else ""),
            ]
            result.append(
                ObscuritySignal(
                    code="parallel-boundary-preparation",
                    message=(
                        f"{method.qualified_name} and {', '.join(peer_names)} implement or "
                        f"structurally match {port.qualified_name}.{method.symbol_name} with "
                        f"overlapping "
                        f"input-to-request preparation: {'; '.join(observations)}."
                    ),
                    node_id=method.atlas_id,
                    location=(
                        SourceLocation(
                            path=method.path,
                            start_line=method.start_line,
                            end_line=method.end_line,
                        )
                        if method.start_line is not None
                        and method.end_line is not None
                        else None
                    ),
                    nature=MetricNature.STRUCTURAL_PROXY,
                    definition=(
                        "Sibling implementations of one resolved or conservatively "
                        "structurally matched Protocol operation read overlapping "
                        "parameter-relative paths while constructing request-shaped data."
                    ),
                    limitations=(
                        "Static overlap does not prove semantic equivalence, provider-neutral "
                        "meaning, duplicated behavior, or misplaced ownership. Structural "
                        "Protocol matching is based on the complete method set and compatible "
                        "type annotations, not runtime dispatch. Inspect the port contract and "
                        "method excerpts before recommending a move."
                    ),
                )
            )
        return result

    def _broad_input_boundary_preparation_signals(
        self,
        nodes: dict[str, AtlasNode],
        edges: list[AtlasEdge],
        modules: list[ParsedModule],
    ) -> list[ObscuritySignal]:
        """Locate one port implementation that prepares requests from a broad input.

        This is deliberately independent of sibling implementations. It records the
        present structural fact that one boundary method reads several nested paths
        from the same input substructure while also constructing keyed request data.
        Whether those reads are legitimate translation or misplaced responsibility
        remains a consultation question.
        """

        parsed_by_path = {module.relative_path: module for module in modules}
        children_by_parent: defaultdict[str, list[AtlasNode]] = defaultdict(list)
        for node in nodes.values():
            if node.parent_id is not None:
                children_by_parent[node.parent_id].append(node)

        result: list[ObscuritySignal] = []
        inspected_methods: set[str] = set()
        for edge in sorted(edges, key=lambda item: item.edge_id):
            if edge.edge_type != EdgeType.IMPLEMENTS:
                continue
            implementation = nodes.get(edge.source_id)
            port = nodes.get(edge.target_id)
            if (
                implementation is None
                or port is None
                or port.node_type != NodeType.INTERFACE
            ):
                continue
            port_operations = {
                child.symbol_name
                for child in children_by_parent[port.atlas_id]
                if child.node_type == NodeType.METHOD
            }
            for method in children_by_parent[implementation.atlas_id]:
                if (
                    method.node_type != NodeType.METHOD
                    or method.symbol_name not in port_operations
                    or method.atlas_id in inspected_methods
                ):
                    continue
                inspected_methods.add(method.atlas_id)
                projections = self._boundary_projections(
                    method,
                    parsed_by_path.get(method.path),
                )
                if not projections:
                    continue
                projection = max(
                    projections,
                    key=lambda item: (
                        len(item.deep_paths),
                        len(item.input_derived_keys),
                        len(item.static_keys),
                        -item.line,
                    ),
                )
                path_sample = ", ".join(sorted(projection.deep_paths)[:4])
                key_sample = ", ".join(sorted(projection.static_keys)[:4])
                result.append(
                    ObscuritySignal(
                        code="broad-input-boundary-preparation",
                        message=(
                            f"{method.qualified_name} implements or structurally matches "
                            f"{port.qualified_name}.{method.symbol_name}, reads "
                            f"{len(projection.deep_paths)} nested input paths under "
                            f"{projection.input_root} ({path_sample}), and projects them into "
                            f"{len(projection.input_derived_keys)} of "
                            f"{len(projection.static_keys)} static fields ({key_sample}) in data "
                            "passed to another call or returned."
                        ),
                        node_id=method.atlas_id,
                        location=SourceLocation(
                            path=method.path,
                            start_line=projection.line,
                            end_line=projection.line,
                        ),
                        nature=MetricNature.STRUCTURAL_PROXY,
                        definition=(
                            "A resolved or conservatively structurally matched port "
                            "implementation reads at least three nested paths from one input "
                            "substructure, feeds them into at least two fields of one "
                            "three-or-more-field projection, and passes that projection to a "
                            "call or return boundary."
                        ),
                        limitations=(
                            "Static data flow does not prove that the fields are semantic "
                            "decisions, that the downstream call is remote transport, or that "
                            "responsibility is misplaced. Persistence mappers, presenters, "
                            "exporters, and deliberate anti-corruption adapters may legitimately "
                            "project broad inputs. Inspect the port contract and located excerpt "
                            "before advising."
                        ),
                    )
                )
        return result

    def _add_structural_protocol_edges(
        self,
        nodes: dict[str, AtlasNode],
        edges: list[AtlasEdge],
        modules: list[ParsedModule],
    ) -> None:
        """Add conservative Python Protocol conformance edges.

        Python adapters commonly rely on structural typing and therefore do not
        inherit their Protocol. We require the complete operation set, compatible
        arity, and at least two matching annotations across each operation before
        treating a class as a structural implementation.
        """

        parsed_by_path = {module.relative_path: module for module in modules}
        children_by_parent: defaultdict[str, list[AtlasNode]] = defaultdict(list)
        for node in nodes.values():
            if node.parent_id is not None:
                children_by_parent[node.parent_id].append(node)
        existing = {
            (edge.source_id, edge.target_id)
            for edge in edges
            if edge.edge_type == EdgeType.IMPLEMENTS
        }
        interfaces = [
            node for node in nodes.values() if node.node_type == NodeType.INTERFACE
        ]
        classes = [
            node
            for node in nodes.values()
            if node.node_type == NodeType.CLASS
            and not node.path.startswith("tests/")
        ]
        for interface in interfaces:
            operations = [
                child
                for child in children_by_parent[interface.atlas_id]
                if child.node_type == NodeType.METHOD
                and child.is_public
            ]
            if not operations:
                continue
            for candidate in classes:
                if (candidate.atlas_id, interface.atlas_id) in existing:
                    continue
                candidate_methods = {
                    child.symbol_name: child
                    for child in children_by_parent[candidate.atlas_id]
                    if child.node_type == NodeType.METHOD
                }
                if not all(operation.symbol_name in candidate_methods for operation in operations):
                    continue
                if not all(
                    self._structural_method_match(
                        operation,
                        candidate_methods[operation.symbol_name],
                        parsed_by_path,
                    )
                    for operation in operations
                ):
                    continue
                edges.append(
                    self._edge(
                        candidate.atlas_id,
                        interface.atlas_id,
                        EdgeType.IMPLEMENTS,
                        confidence=0.8,
                        path=candidate.path,
                        line=candidate.start_line,
                    )
                )

    def _structural_method_match(
        self,
        protocol_method: AtlasNode,
        candidate_method: AtlasNode,
        parsed_by_path: dict[str, ParsedModule],
    ) -> bool:
        protocol_syntax = self._ast_for_node(
            parsed_by_path.get(protocol_method.path),
            protocol_method,
        )
        candidate_syntax = self._ast_for_node(
            parsed_by_path.get(candidate_method.path),
            candidate_method,
        )
        if not isinstance(
            protocol_syntax,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ) or not isinstance(
            candidate_syntax,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            return False
        if isinstance(protocol_syntax, ast.AsyncFunctionDef) != isinstance(
            candidate_syntax,
            ast.AsyncFunctionDef,
        ):
            return False
        protocol_annotations = self._callable_annotations(protocol_syntax)
        candidate_annotations = self._callable_annotations(candidate_syntax)
        if len(protocol_annotations) != len(candidate_annotations):
            return False
        comparable = [
            (expected, actual)
            for expected, actual in zip(
                protocol_annotations,
                candidate_annotations,
                strict=True,
            )
            if expected
        ]
        return len(comparable) >= 2 and all(
            expected == actual for expected, actual in comparable
        )

    @staticmethod
    def _callable_annotations(
        syntax: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[str]:
        arguments = [
            *syntax.args.posonlyargs,
            *syntax.args.args,
            *syntax.args.kwonlyargs,
        ]
        non_receiver = [
            argument for argument in arguments if argument.arg not in {"self", "cls"}
        ]
        if syntax.args.vararg is not None:
            non_receiver.append(syntax.args.vararg)
        if syntax.args.kwarg is not None:
            non_receiver.append(syntax.args.kwarg)
        return [
            *[
                (
                    ast.unparse(argument.annotation).replace(" ", "")
                    if argument.annotation is not None
                    else ""
                )
                for argument in non_receiver
            ],
            (
                ast.unparse(syntax.returns).replace(" ", "")
                if syntax.returns is not None
                else ""
            ),
        ]

    def _boundary_preparation_fingerprint(
        self,
        method: AtlasNode,
        parsed: ParsedModule | None,
    ) -> _BoundaryPreparationFingerprint:
        syntax = self._ast_for_node(parsed, method)
        if not isinstance(syntax, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return _BoundaryPreparationFingerprint(frozenset(), frozenset())
        parameters = [
            argument.arg
            for argument in [
                *syntax.args.posonlyargs,
                *syntax.args.args,
                *syntax.args.kwonlyargs,
            ]
            if argument.arg not in {"self", "cls"}
        ]
        parameter_names = set(parameters)
        input_paths: set[str] = set()
        mapping_keys: set[str] = set()
        parent_by_node = {
            child: parent
            for parent in ast.walk(syntax)
            for child in ast.iter_child_nodes(parent)
        }
        for item in self._lexical_nodes(syntax):
            if (
                isinstance(item, ast.Attribute)
                and not isinstance(parent_by_node.get(item), ast.Attribute)
            ) or (
                isinstance(item, ast.Subscript)
                and not isinstance(
                    parent_by_node.get(item),
                    (ast.Attribute, ast.Subscript),
                )
            ):
                chain = self._input_access_chain(item, parameter_names)
                if chain is not None:
                    input_paths.add(chain)
            if isinstance(item, ast.Dict):
                mapping_keys.update(
                    key.value
                    for key in item.keys
                    if isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value
                )
            elif isinstance(item, ast.Call):
                mapping_keys.update(
                    keyword.arg
                    for keyword in item.keywords
                    if keyword.arg is not None
                )
        return _BoundaryPreparationFingerprint(
            input_paths=frozenset(input_paths),
            mapping_keys=frozenset(mapping_keys),
        )

    def _boundary_projections(
        self,
        method: AtlasNode,
        parsed: ParsedModule | None,
    ) -> list[_BoundaryProjection]:
        """Find request projections whose fields consume one broad input."""

        syntax = self._ast_for_node(parsed, method)
        if not isinstance(syntax, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return []
        parameter_names = {
            argument.arg
            for argument in [
                *syntax.args.posonlyargs,
                *syntax.args.args,
                *syntax.args.kwonlyargs,
            ]
            if argument.arg not in {"self", "cls"}
        }
        parent_by_node = {
            child: parent
            for parent in ast.walk(syntax)
            for child in ast.iter_child_nodes(parent)
        }
        lexical_nodes = list(self._lexical_nodes(syntax))
        position_by_node = {
            item: position for position, item in enumerate(lexical_nodes)
        }
        escaping_uses: defaultdict[str, list[int]] = defaultdict(list)
        binding_positions: defaultdict[str, list[int]] = defaultdict(list)
        for position, item in enumerate(lexical_nodes):
            for name in self._bound_names(item):
                binding_positions[name].append(position)
            expressions: list[ast.AST] = []
            if isinstance(item, ast.Call):
                expressions.extend(item.args)
                expressions.extend(keyword.value for keyword in item.keywords)
            elif isinstance(item, ast.Return) and item.value is not None:
                expressions.append(item.value)
            for expression in expressions:
                for child in ast.walk(expression):
                    if isinstance(child, ast.Name):
                        escaping_uses[child.id].append(position)

        local_paths: dict[str, frozenset[str]] = {}
        active_parameter_names = set(parameter_names)
        projections: list[_BoundaryProjection] = []
        for item in lexical_nodes:
            if isinstance(item, ast.Assign):
                value_paths = self._expression_input_paths(
                    item.value,
                    parameter_names=active_parameter_names,
                    local_paths=local_paths,
                )
                for target in item.targets:
                    names = self._assigned_names(target)
                    for name in names:
                        active_parameter_names.discard(name)
                        local_paths.pop(name, None)
                    if isinstance(target, ast.Name):
                        local_paths[target.id] = value_paths
            elif isinstance(item, ast.AnnAssign) and item.value is not None:
                value_paths = self._expression_input_paths(
                    item.value,
                    parameter_names=active_parameter_names,
                    local_paths=local_paths,
                )
                names = self._assigned_names(item.target)
                for name in names:
                    active_parameter_names.discard(name)
                    local_paths.pop(name, None)
                if isinstance(item.target, ast.Name):
                    local_paths[item.target.id] = value_paths
            else:
                for name in self._bound_names(item):
                    active_parameter_names.discard(name)
                    local_paths.pop(name, None)

            if isinstance(item, ast.Dict):
                line = getattr(item, "lineno", method.start_line or 1)
                projection_position = position_by_node[item]
                assigned_names = self._projection_assignment_names(
                    item,
                    parent_by_node=parent_by_node,
                )
                escapes = self._expression_reaches_call_or_return(
                    item,
                    parent_by_node=parent_by_node,
                ) or any(
                    use_position > projection_position
                    and not any(
                        projection_position < binding_position < use_position
                        for binding_position in binding_positions.get(name, [])
                    )
                    for name in assigned_names
                    for use_position in escaping_uses.get(name, [])
                )
                if not escapes:
                    continue
                fields = {
                    key.value: self._expression_input_paths(
                        value,
                        parameter_names=active_parameter_names,
                        local_paths=local_paths,
                    )
                    for key, value in zip(item.keys, item.values, strict=True)
                    if isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value
                }
                projections.extend(
                    self._qualifying_boundary_projections(
                        fields,
                        line=line,
                    )
                )
            elif isinstance(item, ast.Call):
                fields = {
                    keyword.arg: self._expression_input_paths(
                        keyword.value,
                        parameter_names=active_parameter_names,
                        local_paths=local_paths,
                    )
                    for keyword in item.keywords
                    if keyword.arg is not None
                }
                projections.extend(
                    self._qualifying_boundary_projections(
                        fields,
                        line=getattr(item, "lineno", method.start_line or 1),
                    )
                )

        unique = {
            (
                projection.input_root,
                projection.deep_paths,
                projection.static_keys,
                projection.input_derived_keys,
                projection.line,
            ): projection
            for projection in projections
        }
        return sorted(
            unique.values(),
            key=lambda item: (
                item.line,
                item.input_root,
                sorted(item.static_keys),
            ),
        )

    @classmethod
    def _expression_input_paths(
        cls,
        expression: ast.AST,
        *,
        parameter_names: set[str],
        local_paths: dict[str, frozenset[str]],
    ) -> frozenset[str]:
        scope_binders = (
            ast.DictComp,
            ast.GeneratorExp,
            ast.Lambda,
            ast.ListComp,
            ast.SetComp,
        )
        if any(isinstance(item, scope_binders) for item in ast.walk(expression)):
            # Conservatively decline data-flow claims across nested expression scopes.
            # Their binders may shadow the enclosing method parameters.
            return frozenset()
        parent_by_node = {
            child: parent
            for parent in ast.walk(expression)
            for child in ast.iter_child_nodes(parent)
        }
        paths: set[str] = set()
        for item in [expression, *cls._lexical_nodes(expression)]:
            if (
                isinstance(item, ast.Attribute)
                and not isinstance(parent_by_node.get(item), ast.Attribute)
            ) or (
                isinstance(item, ast.Subscript)
                and not isinstance(
                    parent_by_node.get(item),
                    (ast.Attribute, ast.Subscript),
                )
            ):
                chain = cls._input_access_chain_with_parameter(
                    item,
                    parameter_names,
                )
                if chain is not None:
                    paths.add(chain)
            if isinstance(item, ast.Name) and item.id in local_paths:
                paths.update(local_paths[item.id])
        return frozenset(paths)

    @staticmethod
    def _input_access_chain_with_parameter(
        node: ast.AST,
        parameter_names: set[str],
    ) -> str | None:
        parts: list[str] = []
        cursor = node
        while isinstance(cursor, (ast.Attribute, ast.Subscript)):
            if isinstance(cursor, ast.Attribute):
                parts.append(cursor.attr)
                cursor = cursor.value
                continue
            slice_node = cursor.slice
            if not (
                isinstance(slice_node, ast.Constant)
                and isinstance(slice_node.value, str)
            ):
                return None
            parts.append(slice_node.value)
            cursor = cursor.value
        if (
            not isinstance(cursor, ast.Name)
            or cursor.id not in parameter_names
            or len(parts) < 2
        ):
            return None
        parts.reverse()
        return ".".join([cursor.id, *parts])

    @staticmethod
    def _assigned_names(target: ast.AST) -> set[str]:
        if isinstance(target, ast.Name):
            return {target.id}
        if isinstance(target, (ast.List, ast.Tuple)):
            return {
                name
                for element in target.elts
                for name in PythonAstRepositoryAnalyzer._assigned_names(element)
            }
        return set()

    @classmethod
    def _bound_names(cls, node: ast.AST) -> set[str]:
        if isinstance(node, ast.Assign):
            return {
                name
                for target in node.targets
                for name in cls._assigned_names(target)
            }
        if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            return cls._assigned_names(node.target)
        if isinstance(node, (ast.For, ast.AsyncFor)):
            return cls._assigned_names(node.target)
        if isinstance(node, (ast.With, ast.AsyncWith)):
            return {
                name
                for item in node.items
                if item.optional_vars is not None
                for name in cls._assigned_names(item.optional_vars)
            }
        if isinstance(node, ast.ExceptHandler) and node.name is not None:
            return {node.name}
        return set()

    @classmethod
    def _projection_assignment_names(
        cls,
        expression: ast.AST,
        *,
        parent_by_node: dict[ast.AST, ast.AST],
    ) -> set[str]:
        parent = parent_by_node.get(expression)
        if isinstance(parent, ast.Assign) and parent.value is expression:
            return {
                name
                for target in parent.targets
                for name in cls._assigned_names(target)
            }
        if isinstance(parent, ast.AnnAssign) and parent.value is expression:
            return cls._assigned_names(parent.target)
        return set()

    @staticmethod
    def _expression_reaches_call_or_return(
        expression: ast.AST,
        *,
        parent_by_node: dict[ast.AST, ast.AST],
    ) -> bool:
        cursor = expression
        while parent := parent_by_node.get(cursor):
            if isinstance(parent, (ast.Call, ast.Return)):
                return True
            if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                return False
            if isinstance(parent, (ast.stmt, ast.FunctionDef, ast.AsyncFunctionDef)):
                return False
            cursor = parent
        return False

    @staticmethod
    def _qualifying_boundary_projections(
        fields: dict[str, frozenset[str]],
        *,
        line: int,
    ) -> list[_BoundaryProjection]:
        if len(fields) < 3:
            return []
        paths_by_root: defaultdict[str, set[str]] = defaultdict(set)
        keys_by_root: defaultdict[str, set[str]] = defaultdict(set)
        for key, paths in fields.items():
            for path in paths:
                parts = path.split(".")
                if len(parts) < 3:
                    continue
                root = ".".join(parts[:2])
                paths_by_root[root].add(path)
                keys_by_root[root].add(key)
        return [
            _BoundaryProjection(
                input_root=root,
                deep_paths=frozenset(paths),
                static_keys=frozenset(fields),
                input_derived_keys=frozenset(keys_by_root[root]),
                line=line,
            )
            for root, paths in paths_by_root.items()
            if len(paths) >= 3 and len(keys_by_root[root]) >= 2
        ]

    @staticmethod
    def _input_access_chain(
        node: ast.AST,
        parameter_names: set[str],
    ) -> str | None:
        parts: list[str] = []
        cursor = node
        while isinstance(cursor, (ast.Attribute, ast.Subscript)):
            if isinstance(cursor, ast.Attribute):
                parts.append(cursor.attr)
                cursor = cursor.value
                continue
            slice_node = cursor.slice
            if not (
                isinstance(slice_node, ast.Constant)
                and isinstance(slice_node.value, str)
            ):
                return None
            parts.append(slice_node.value)
            cursor = cursor.value
        if not isinstance(cursor, ast.Name) or cursor.id not in parameter_names:
            return None
        parts.reverse()
        return ".".join(parts) if len(parts) >= 2 else None

    @staticmethod
    def _is_parallel_preparation_match(
        first: _BoundaryPreparationFingerprint,
        second: _BoundaryPreparationFingerprint,
        *,
        shared_paths: frozenset[str],
        shared_keys: frozenset[str],
    ) -> bool:
        first_features = len(first.input_paths) + len(first.mapping_keys)
        second_features = len(second.input_paths) + len(second.mapping_keys)
        if min(first_features, second_features) < 4:
            return False
        shared_features = len(shared_paths) + len(shared_keys)
        overlap = shared_features / min(first_features, second_features)
        has_broad_shared_input = len(shared_paths) >= 3
        has_input_and_mapping_shape = len(shared_paths) >= 1 and len(shared_keys) >= 3
        return (
            shared_features >= 4
            and overlap >= 0.6
            and (has_broad_shared_input or has_input_and_mapping_shape)
        )
