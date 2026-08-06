"""Deterministic Python repository atlas builder."""

from __future__ import annotations

import ast
import re
import subprocess
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import ClassVar

from archcompass.adapters.analysis.ast_support import (
    ParsedModule,
    ast_for_node,
    build_edge,
    canonical_roots,
    excluded_within,
    lexical_nodes,
    lies_within,
    module_name,
)
from archcompass.adapters.analysis.boundary_signals import (
    add_structural_protocol_edges,
    broad_input_boundary_preparation_signals,
    parallel_boundary_preparation_signals,
)
from archcompass.adapters.analysis.graph import (
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
    DefinedConstant,
    DependencyMetrics,
    EdgeType,
    LocalStructuralMetrics,
    MetricProfile,
    ModuleFacts,
    NamedMention,
    NodeType,
    ObscuritySignal,
    RepositoryContentIdentity,
    SourceLocation,
)
from archcompass.domain.base import canonical_json, stable_id
from archcompass.domain.errors import PathValidationError
from archcompass.ports.atlas import (
    ConformanceQuestion,
    EdgeResolutionRequest,
    EdgeResolver,
    ReferenceQuestion,
)

# v4 records per-module facts (constants stated, repository modules named). An atlas built
# by v3 has none, so it is stale rather than quietly missing them, and is re-analyzed.
#
# v5 gives each mention the lines it occurs on. A v4 atlas records that a module names a
# concept and not where, which left a scattered-concept participant with no span to point at
# — it said line 1, and line 1 of a Python file is the docstring, so the code shown as
# evidence of a leaked name was a docstring that did not contain it. Nothing can recover the
# positions from a stored v4 atlas, so it is stale and re-analyzed rather than read with the
# lines missing (ADR 0002). Re-analysis is cheap and lossless: an atlas is derived.
PARSER_VERSION = "python-ast-3.12-v5"
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


#: What the hash records when no resolver is configured. A marker rather than an omitted
#: key: an atlas built with typed edges and one built without them are different atlases,
#: and leaving the key out when the extra is absent would let the second be read as the
#: first the moment the extra is installed.
_RESOLUTION_ABSENT = "absent"


def _analysis_config_hash(resolution: Mapping[str, str] | None = None) -> str:
    return stable_id(
        "analysis",
        canonical_json(
            {
                "ignored": sorted(IGNORED_DIRECTORIES),
                "config_suffixes": sorted(CONFIG_SUFFIXES),
                "parser": PARSER_VERSION,
                "resolution": (
                    dict(sorted(resolution.items()))
                    if resolution is not None
                    else _RESOLUTION_ABSENT
                ),
            }
        ),
    )


@dataclass(frozen=True)
class SnapshotFile:
    path: Path
    relative_path: str
    content: bytes

    def text(self) -> str:
        return self.content.decode("utf-8")


@dataclass(frozen=True)
class GitFacts:
    """What git says about a checkout, or nothing at all.

    Three separate questions with three separate answers, because they fail separately: a
    directory outside git answers none of them, a repository with no commits yet answers
    neither sha, and a detached HEAD — the ordinary shape of a CI checkout — answers both
    shas and no branch. Read together behind one top-level lookup, since that lookup is the
    part all three share.
    """

    commit_sha: str | None = None
    #: The first commit of the history. What `repo_id` is derived from, because it is the one
    #: identifier that survives a clone. Reported only for a root that is the top level of its
    #: repository — see `_git_facts` for why a nested root reports neither this nor the branch.
    root_commit_sha: str | None = None
    #: The branch the working tree is on, or `None` when HEAD is detached — or when the root
    #: is nested inside a repository whose branch is not this project's to claim.
    branch_name: str | None = None


@dataclass(frozen=True)
class RepositorySnapshot:
    root: Path
    python_files: tuple[SnapshotFile, ...]
    configuration_files: tuple[SnapshotFile, ...]
    content_fingerprint: str
    git_commit_sha: str | None
    root_commit_sha: str | None = None
    branch_name: str | None = None


@dataclass(frozen=True)
class UnresolvedSite:
    """One call or name the parse could not attach to a symbol of this repository.

    Kept rather than only reported, because it is exactly the question the type-aware
    resolver is asked. The site carries its own source node so an answer can be turned
    into an edge without re-walking the module.
    """

    source: AtlasNode
    module_path: str
    line: int
    expression: str
    edge_type: EdgeType


#: Names too common to be worth reporting as unresolved. A call to `len` was never a missing
#: edge, and a signal per occurrence would bury the ones that are.
_UNREMARKABLE_CALLS = frozenset({"print", "len", "str", "int", "list", "dict"})


class PythonAstRepositoryAnalyzer:
    """The static parse, optionally corrected by a type oracle.

    The parse is always the source of nodes; the resolver only ever changes which edges
    exist between them. Without one the atlas is exactly what it has always been, which is
    what makes the extra optional rather than a fork of the analyzer.
    """

    def __init__(
        self,
        edge_resolver: EdgeResolver | None = None,
        *,
        excluded_roots: tuple[Path, ...] = (),
    ) -> None:
        self._edge_resolver = edge_resolver
        # Canonicalized once, and never folded into the analysis config hash: an excluded
        # root is where this machine happens to keep its workspace, exactly like `root_path`,
        # and hashing it would make two machines analysing the same commit disagree about
        # whether a stored atlas is stale.
        self._excluded_roots = canonical_roots(excluded_roots)

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
            # The facts a durable identity is derived from, carried rather than derived here:
            # the analyzer reads git, and which lineage a run attaches to is a decision with
            # an override on it (a CI checkout is detached), which belongs above this layer.
            root_commit_sha=snapshot.root_commit_sha,
            branch_name=snapshot.branch_name,
            content_fingerprint=snapshot.content_fingerprint,
            parser_version=PARSER_VERSION,
            analysis_config_hash=self._config_hash(),
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
            edges.append(build_edge(package.parent_id, package.atlas_id, EdgeType.CONTAINS))

        modules: list[ParsedModule] = []
        for source_file in python_files:
            parsed = self._parse_module(
                canonical_root, source_file, package_nodes, root_node, signals
            )
            modules.append(parsed)
            nodes[parsed.node.atlas_id] = parsed.node
            edges.append(build_edge(parsed.node.parent_id, parsed.node.atlas_id, EdgeType.CONTAINS))
            for symbol in parsed.symbols.values():
                nodes[symbol.atlas_id] = symbol
                edges.append(build_edge(symbol.parent_id, symbol.atlas_id, EdgeType.CONTAINS))

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
            edges.append(build_edge(parent.atlas_id, node.atlas_id, EdgeType.CONTAINS))

        module_by_name = {module.qualified_name: module for module in modules}
        symbol_by_qualified = {
            symbol.qualified_name: symbol
            for module in modules
            for symbol in module.symbols.values()
        }
        unresolved: list[UnresolvedSite] = []
        for module in modules:
            self._resolve_module_edges(
                module,
                module_by_name,
                symbol_by_qualified,
                edges,
                unresolved,
            )
        # Exactly one source of structural `IMPLEMENTS` edges. The heuristic guesses from
        # names and annotations at 0.8; the typed sweep answers the same question from the
        # type checker's own view. Running both would double every agreed pair and leave a
        # reader unable to say which pass believed what.
        if self._edge_resolver is None:
            add_structural_protocol_edges(nodes, edges, modules)
        else:
            unresolved = self._apply_resolution(
                self._edge_resolver, canonical_root, nodes, edges, unresolved
            )
        signals.extend(self._unresolved_call_signals(unresolved))
        edges = self._deduplicate_edges(edges)
        module_facts = self._module_facts(modules)
        self._add_duplicate_constant_signals(module_facts, signals)
        signals.extend(
            broad_input_boundary_preparation_signals(
                nodes,
                edges,
                modules,
            )
        )
        signals.extend(
            parallel_boundary_preparation_signals(
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
            module_facts=sorted(module_facts, key=lambda item: item.node_id),
        )

    def current_identity(self, root: Path) -> RepositoryContentIdentity:
        snapshot = self._snapshot(root)
        return RepositoryContentIdentity(
            root_path=str(snapshot.root),
            content_fingerprint=snapshot.content_fingerprint,
            git_commit_sha=snapshot.git_commit_sha,
            parser_version=PARSER_VERSION,
            analysis_config_hash=self._config_hash(),
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
        git = self._git_facts(canonical_root)
        return RepositorySnapshot(
            root=canonical_root,
            python_files=python_files,
            configuration_files=configuration_files,
            content_fingerprint=self._fingerprint(files),
            git_commit_sha=git.commit_sha,
            root_commit_sha=git.root_commit_sha,
            branch_name=git.branch_name,
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

    def _discover_files(self, root: Path) -> tuple[list[Path], list[Path]]:
        # What an ArchCompass workspace holds — its database, its authored policies, its run
        # outputs — changes whenever a review runs. A workspace inside the analysed
        # repository would therefore move the content fingerprint on every run, leaving the
        # atlas permanently stale and filling it with the tool's own state, so it is left out
        # exactly like an ignored directory.
        excluded = excluded_within(root, self._excluded_roots)
        python_files: list[Path] = []
        config_files: list[Path] = []
        for path in root.rglob("*"):
            relative_parts = path.relative_to(root).parts
            if any(part in IGNORED_DIRECTORIES for part in relative_parts):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if lies_within(path, excluded):
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

    @classmethod
    def _git_facts(cls, root: Path) -> GitFacts:
        """Everything the atlas records about this checkout's history, in one place.

        Git is read here and nowhere else, and every question is asked the same way: one
        subprocess with a short budget, and any failure is `None` rather than an exception.
        A repository is optional — a directory someone points at may simply not be one — so
        "git could not say" has to be an ordinary answer rather than a broken run.

        The history facts — the root commit and the branch — are reported only when the
        analysed root *is* the top level of the repository. The folder put up for review is
        the project, and a folder that merely sits inside some larger repository does not
        inherit that repository's identity: reported, the enclosing root commit would make
        every project under one checkout the same repository, so their reviews would group
        together and one project's baseline would stand over another's boundaries (see
        `domain.lineage.derive_repo_id`). Such a root is treated exactly like a folder outside
        git, which is what it is as far as identity goes.

        `commit_sha` is the exception and stays what it always was, including the `git log -1`
        against a subdirectory below. It answers a different question — has this folder's own
        content moved since the atlas was built — and freshness is about these files, not
        about whose repository they are in.
        """

        top_level = cls._git_top_level(root)
        if top_level is None:
            return GitFacts()
        if top_level != root:
            return GitFacts(commit_sha=cls._git_sha(root, top_level))
        return GitFacts(
            commit_sha=cls._git_sha(root, top_level),
            root_commit_sha=cls._git_root_commit_sha(top_level),
            branch_name=cls._git_branch_name(top_level),
        )

    @staticmethod
    def _run_git(*arguments: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *arguments],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip()

    @classmethod
    def _git_top_level(cls, root: Path) -> Path | None:
        output = cls._run_git("-C", str(root), "rev-parse", "--show-toplevel")
        if not output:
            return None
        try:
            return Path(output).resolve(strict=True)
        except OSError:
            return None

    @classmethod
    def _git_sha(cls, root: Path, top_level: Path) -> str | None:
        if top_level == root:
            output = cls._run_git("-C", str(root), "rev-parse", "HEAD")
        else:
            try:
                relative_root = root.relative_to(top_level).as_posix()
            except ValueError:
                return None
            output = cls._run_git(
                "-C", str(top_level), "log", "-1", "--format=%H", "--", relative_root
            )
        return cls._validated_sha(output)

    @classmethod
    def _git_root_commit_sha(cls, top_level: Path) -> str | None:
        """The first commit of this history, which is what survives a clone.

        A history can have more than one root — merging two unrelated histories is legal, and
        `rev-list --max-parents=0` then prints all of them. The lexicographically first is
        taken, because the identity has to be the same on every machine that asks, and git's
        own ordering here is by traversal rather than by anything stable.
        """

        output = cls._run_git("-C", str(top_level), "rev-list", "--max-parents=0", "HEAD")
        if not output:
            return None
        return cls._validated_sha(sorted(output.splitlines())[0].strip())

    @classmethod
    def _git_branch_name(cls, top_level: Path) -> str | None:
        """The branch the working tree is on, or `None` when there is not one.

        A detached HEAD answers with the literal string `HEAD`, which is not a branch name and
        is exactly what a CI checkout of a commit looks like. It is reported as absent so the
        caller can decide what to attribute the run to, rather than filing every CI run under
        a branch called `HEAD`.
        """

        output = cls._run_git("-C", str(top_level), "rev-parse", "--abbrev-ref", "HEAD")
        if not output or output == "HEAD":
            return None
        return output

    @staticmethod
    def _validated_sha(candidate: str | None) -> str | None:
        if candidate is None or len(candidate) != 40:
            return None
        return candidate if all(char in "0123456789abcdef" for char in candidate) else None

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

    #: The bases that make a class an abstraction rather than a thing. Resolved through the
    #: module's imports, so an alias or a dotted spelling reaches the same answer.
    _ABSTRACTION_BASES: ClassVar[frozenset[str]] = frozenset(
        {
            "typing.Protocol",
            "typing_extensions.Protocol",
            "abc.ABC",
        }
    )
    _ABSTRACTION_METACLASSES: ClassVar[frozenset[str]] = frozenset({"abc.ABCMeta"})

    def _declares_an_abstraction(self, module: ParsedModule, statement: ast.ClassDef) -> bool:
        """Whether this class declares a boundary, from what its bases resolve to.

        Resolved, never matched on the written name. The suffix test this replaces read
        `base.endswith("Protocol")`, which was wrong in both directions and silently: it
        missed `from typing import Protocol as P`, and — worse — it classified every
        subclass of a port named `*Protocol` as an abstraction too. Since the detector
        excludes abstractions from an abstraction's implementation count, a port called
        `GaugeProtocol` ended up with zero implementations and vanished from the review
        rather than being reported wrongly.
        """

        for base in statement.bases:
            if self._resolved_name(module, self._dotted(base)) in self._ABSTRACTION_BASES:
                return True
        # `class Store(metaclass=ABCMeta)` is the third spelling of an abstract base, and
        # a metaclass is a keyword rather than a base, so it is read separately.
        for keyword in statement.keywords:
            if keyword.arg == "metaclass" and self._resolved_name(
                module, self._dotted(keyword.value)
            ) in self._ABSTRACTION_METACLASSES:
                return True
        return any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                self._resolved_name(module, self._dotted(decorator)) == "abc.abstractmethod"
                or self._dotted(decorator) == "abstractmethod"
                for decorator in item.decorator_list
            )
            for item in statement.body
        )

    @staticmethod
    def _resolved_name(module: ParsedModule, dotted: str) -> str:
        """A written name expanded through this module's imports, or itself if unknown."""

        if not dotted:
            return ""
        head, _, rest = dotted.partition(".")
        origin = module.import_aliases.get(head)
        if origin is None:
            return dotted
        return f"{origin}.{rest}" if rest else origin

    def _record_import_aliases(self, module: ParsedModule) -> None:
        """Map every name this module imported to the dotted path it came from.

        Recorded during parsing rather than while resolving edges, because classification
        happens first and needs it. Edge resolution reads the same table afterwards.
        """

        for statement in module.tree.body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    module.import_aliases[alias.asname or alias.name.split(".")[0]] = alias.name
            elif isinstance(statement, ast.ImportFrom):
                imported_module = self._resolve_from_name(module, statement)
                for alias in statement.names:
                    module.import_aliases[alias.asname or alias.name] = (
                        f"{imported_module}.{alias.name}".strip(".")
                    )

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
                qualified=module_name(relative),
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
        qualified = module_name(relative)
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
        # Before symbols, because classifying a class needs to know what its bases resolve
        # to: `Protocol` imported under any name is still `typing.Protocol`, and reading it
        # off the written name instead is what made an aliased import invisible.
        self._record_import_aliases(parsed)
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
                interface = self._declares_an_abstraction(parsed, statement)
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
        unresolved: list[UnresolvedSite],
    ) -> None:
        for statement in module.tree.body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    target = self._best_module(alias.name, module_by_name)
                    if target:
                        import_edge = build_edge(
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
                    import_edge = build_edge(
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
        all_symbols = [module.node, *module.symbols.values()]
        for source_node in all_symbols:
            ast_node = ast_for_node(module, source_node)
            if ast_node is None:
                continue
            scoped_nodes = list(lexical_nodes(ast_node))
            for item in scoped_nodes:
                if isinstance(item, ast.Call):
                    dotted = self._dotted(item.func)
                    target, confidence = self._resolve_symbol(
                        dotted, source_node, module, symbol_by_qualified
                    )
                    if target:
                        edges.append(
                            build_edge(
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
                                build_edge(
                                    source_node.atlas_id,
                                    target.atlas_id,
                                    EdgeType.TESTS,
                                    confidence=confidence,
                                    path=module.relative_path,
                                    line=item.lineno,
                                )
                            )
                    elif dotted:
                        unresolved.append(
                            UnresolvedSite(
                                source=source_node,
                                module_path=module.relative_path,
                                line=item.lineno,
                                expression=dotted,
                                edge_type=EdgeType.CALLS,
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
                            build_edge(
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
                                build_edge(
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
                if target is None:
                    unresolved.append(
                        UnresolvedSite(
                            source=source_node,
                            module_path=module.relative_path,
                            line=item.lineno,
                            expression=item.id,
                            edge_type=EdgeType.REFERENCES,
                        )
                    )
                    continue
                if target.atlas_id == source_node.atlas_id:
                    continue
                edges.append(
                    build_edge(
                        source_node.atlas_id,
                        target.atlas_id,
                        EdgeType.REFERENCES,
                        confidence=confidence,
                        path=module.relative_path,
                        line=item.lineno,
                    )
                )

    def _config_hash(self) -> str:
        return _analysis_config_hash(
            self._edge_resolver.fingerprint() if self._edge_resolver is not None else None
        )

    def _apply_resolution(
        self,
        resolver: EdgeResolver,
        root: Path,
        nodes: dict[str, AtlasNode],
        edges: list[AtlasEdge],
        unresolved: list[UnresolvedSite],
    ) -> list[UnresolvedSite]:
        """Ask the type oracle everything at once, and keep the answers that are edges.

        Returns the sites still unresolved afterwards, so the signal that reports them says
        what is genuinely invisible rather than what the cheap pass alone could not see.
        """

        # Deduplicated for the request and kept whole for the signals: one site is one
        # question however many times it is written, but an unresolved call is reported
        # where it occurs, and collapsing occurrences here would silently change what the
        # resolver-absent path reports.
        sites: dict[tuple[str, int, str], list[UnresolvedSite]] = defaultdict(list)
        for site in unresolved:
            sites[(site.module_path, site.line, site.expression)].append(site)
        request = EdgeResolutionRequest(
            conformances=self._conformance_questions(nodes, edges),
            references=tuple(
                ReferenceQuestion(path=path, line=line, expression=expression)
                for path, line, expression in sorted(sites)
            ),
        )
        result = resolver.resolve(root, request)
        by_qualified = self._nodes_by_qualified_name(nodes)
        for verdict in result.conformances:
            implementation = by_qualified.get(verdict.question.class_qualified_name)
            abstraction = by_qualified.get(verdict.question.abstraction_qualified_name)
            if implementation is None or abstraction is None:
                continue
            edges.append(
                build_edge(
                    implementation.atlas_id,
                    abstraction.atlas_id,
                    EdgeType.IMPLEMENTS,
                    # A rule the checker itself endorsed is as certain as this project gets;
                    # the relaxed rule is one deliberate step below it, and above the 0.8 the
                    # name-and-annotation heuristic earns.
                    confidence=1.0 if verdict.rule == "strict" else 0.9,
                    path=implementation.path,
                    line=implementation.start_line,
                    resolved_by="types",
                    conformance=verdict.rule,
                )
            )
        resolved_sites: set[int] = set()
        for reference in result.references:
            question = reference.question
            target = by_qualified.get(reference.target_qualified_name)
            # A symbol outside this repository is not an edge. `builtins.list.append` is a
            # correct answer and there is no node for it, so the resolution is dropped and
            # the site stays unresolved rather than pointing at nothing.
            if target is None:
                continue
            for site in sites.get((question.path, question.line, question.expression), []):
                if target.atlas_id == site.source.atlas_id:
                    continue
                resolved_sites.add(id(site))
                edges.append(
                    build_edge(
                        site.source.atlas_id,
                        target.atlas_id,
                        site.edge_type,
                        path=site.module_path,
                        line=site.line,
                        resolved_by="types",
                    )
                )
                if site.edge_type == EdgeType.CALLS and site.source.node_type in {
                    NodeType.TEST_FUNCTION,
                    NodeType.TEST_MODULE,
                }:
                    edges.append(
                        build_edge(
                            site.source.atlas_id,
                            target.atlas_id,
                            EdgeType.TESTS,
                            path=site.module_path,
                            line=site.line,
                            resolved_by="types",
                        )
                    )
        return [site for site in unresolved if id(site) not in resolved_sites]

    @staticmethod
    def _conformance_questions(
        nodes: dict[str, AtlasNode], edges: list[AtlasEdge]
    ) -> tuple[ConformanceQuestion, ...]:
        """Every (class, abstraction) pair worth judging, and no more.

        The same population the untyped heuristic reads — abstractions declared here, and
        classes outside `tests/` — so the two passes answer for the same repository and a
        measurement of one is a measurement of the other. Pairs an inheritance already
        established are left alone; the parse named them with certainty and a second edge at
        the same site would only restate it.
        """

        stated = {
            (edge.source_id, edge.target_id)
            for edge in edges
            if edge.edge_type == EdgeType.IMPLEMENTS
        }
        abstractions = sorted(
            (node for node in nodes.values() if node.node_type == NodeType.INTERFACE),
            key=lambda item: item.atlas_id,
        )
        classes = sorted(
            (
                node
                for node in nodes.values()
                if node.node_type == NodeType.CLASS and not node.path.startswith("tests/")
            ),
            key=lambda item: item.atlas_id,
        )
        return tuple(
            ConformanceQuestion(
                class_path=candidate.path,
                class_qualified_name=candidate.qualified_name,
                abstraction_path=abstraction.path,
                abstraction_qualified_name=abstraction.qualified_name,
            )
            for abstraction in abstractions
            for candidate in classes
            if (candidate.atlas_id, abstraction.atlas_id) not in stated
        )

    @staticmethod
    def _nodes_by_qualified_name(nodes: dict[str, AtlasNode]) -> dict[str, AtlasNode]:
        """Qualified name back to the node that owns it.

        Packages and the repository itself are excluded: a package directory and the
        `__init__.py` inside it carry the same dotted name, and a resolver naming that name
        means the module.
        """

        return {
            node.qualified_name: node
            for node in sorted(nodes.values(), key=lambda item: item.atlas_id)
            if node.node_type not in {NodeType.REPOSITORY, NodeType.PACKAGE}
        }

    def _unresolved_call_signals(
        self, unresolved: Iterable[UnresolvedSite]
    ) -> list[ObscuritySignal]:
        return [
            self._signal(
                "unresolved-call",
                f"Static call target could not be resolved: {site.expression}",
                site.source,
                site.line,
            )
            for site in unresolved
            if site.edge_type == EdgeType.CALLS
            and site.expression not in _UNREMARKABLE_CALLS
        ]

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
            syntax = ast_for_node(parsed, node) if parsed else None
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
        scoped_nodes = list(lexical_nodes(syntax))
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
        # A subscripted name is still that name: `Protocol[T]` is Protocol, and
        # `Repository[Book]` inherits from Repository. Returning "" here made every generic
        # base invisible, so `class Port(Protocol[T])` was classified an ordinary class and
        # dropped out of detection entirely.
        if isinstance(node, ast.Subscript):
            return PythonAstRepositoryAnalyzer._dotted(node.value)
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
    def _deduplicate_edges(edges: list[AtlasEdge]) -> list[AtlasEdge]:
        return list({edge.edge_id: edge for edge in edges}.values())

    @staticmethod
    def _owning_module(node: AtlasNode, modules: dict[str, str]) -> str | None:
        return modules.get(node.path)

    def _module_facts(self, modules: list[ParsedModule]) -> list[ModuleFacts]:
        """What each module states, and which of this repository's modules it names.

        Both halves are facts about a file's whole text rather than about any symbol in it,
        which is why they are recorded here and not on a node. Neither is a judgement: two
        modules sharing a constant may be a coincidence, and naming another module is
        ordinarily how code works. Deciding which of those matter is the detector's job.
        """

        # Bounded to names this repository owns. Recording every token a file contains
        # would make the atlas a copy of the source; recording only the names that could
        # refer to something here keeps it a set of relationships.
        owned = {
            module.path.stem.casefold()
            for module in modules
            if not module.path.stem.startswith("_")
        }
        return [
            ModuleFacts(
                node_id=module.node.atlas_id,
                path=module.relative_path,
                qualified_name=module.qualified_name,
                constants=_declared_constants(module),
                mentions=_owned_mentions(module, owned),
            )
            for module in modules
        ]

    def _add_duplicate_constant_signals(
        self, facts: list[ModuleFacts], signals: list[ObscuritySignal]
    ) -> None:
        """The long-standing signal, now derived from the recorded facts.

        Kept because the atlas surfaces it and it is a cheap thing for a reader to see. The
        detector that turns the same fact into a reviewable candidate is separate and lives
        in the domain: a signal is a note, and a candidate is something a model must judge.
        """

        by_name: dict[str, list[ModuleFacts]] = defaultdict(list)
        for module in facts:
            for constant in module.constants:
                by_name[constant.name].append(module)
        node_by_id = {module.node_id: module for module in facts}
        for name, definitions in by_name.items():
            if len(definitions) < 2:
                continue
            for module in definitions:
                line = next(
                    constant.line
                    for constant in node_by_id[module.node_id].constants
                    if constant.name == name
                )
                signals.append(
                    ObscuritySignal(
                        code="similarly-named-constant",
                        message=f"Constant {name} is defined in {len(definitions)} modules",
                        node_id=module.node_id,
                        location=SourceLocation(
                            path=module.path, start_line=line, end_line=line
                        ),
                    )
                )



def _declared_constants(module: ParsedModule) -> list[DefinedConstant]:
    """Module-level SCREAMING_CASE assignments, with their value fingerprinted.

    Upper-case only, because that is the convention that says "this is knowledge, not
    working state", and a detector reading every module-level assignment would report the
    repository's plumbing at itself.
    """

    constants: list[DefinedConstant] = []
    for statement in module.tree.body:
        names: list[str] = []
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign):
            names = [target.id for target in statement.targets if isinstance(target, ast.Name)]
            value = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            names = [statement.target.id]
            value = statement.value
        for name in names:
            if not name.isupper():
                continue
            constants.append(
                DefinedConstant(
                    name=name,
                    value_fingerprint=_value_fingerprint(value),
                    line=statement.lineno,
                )
            )
    return constants


def _value_fingerprint(value: ast.expr | None) -> str:
    """A short hash of a literal value, or empty when it is not one.

    Hashed rather than stored. Two modules holding the same literal is the whole fact a
    detector needs, and a constant is exactly the kind of thing that turns out to be a
    token or a key — an atlas that copied the value would carry it into every prompt and
    every stored review.
    """

    if value is None:
        return ""
    try:
        literal = ast.literal_eval(value)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return ""
    return sha256(repr(literal).encode("utf-8")).hexdigest()[:16]


def _owned_mentions(module: ParsedModule, owned: set[str]) -> list[NamedMention]:
    """The names this module refers to that this repository owns, and where.

    Its own name is excluded: a module naming itself is not a concept that has spread.
    """

    found = _mentioned_names(module)
    return [
        NamedMention(name=name, lines=found[name])
        for name in sorted(found.keys() & owned - {module.path.stem.casefold()})
    ]


def _mentioned_names(module: ParsedModule) -> dict[str, list[int]]:
    """Every name this module's code and strings contain, casefolded, and where.

    Docstrings are skipped. Prose describing a vendor is documentation; the question a
    detector is asking is whether the *code* outside a module has to know that module
    exists, and a sentence in a docstring is not that.

    The lines come from the nodes themselves, which have carried them all along. Recording
    them is what lets a scattered-concept participant point at the import that names the
    vendor rather than at line 1 — see `NamedMention`, which exists because it did not.

    An `ast.alias` has no position of its own before Python 3.10 and is attributed to its
    statement here regardless, because `from x import y` is the line a reader wants either
    way: the name is on it, and the alias node's own column is not what they asked for.
    """

    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(module.tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    found: dict[str, set[int]] = defaultdict(set)

    def record(tokens: set[str], line: int | None) -> None:
        if line is None:
            return
        for token in tokens:
            found[token].add(line)

    for parent in ast.walk(module.tree):
        # Imports first, so an alias inherits the statement's line rather than being missed.
        if isinstance(parent, (ast.Import, ast.ImportFrom)):
            # The names, not the module they came from. `from provider.qwen import X` has
            # always contributed `x` and not `qwen`, and widening that here would change
            # which boundaries are detected — this change is about where a mention is, not
            # about what counts as one.
            for alias in parent.names:
                record(_name_tokens(alias.name.replace(".", "_")), parent.lineno)
                if alias.asname:
                    record(_name_tokens(alias.asname), parent.lineno)
            continue
        if isinstance(parent, ast.Name):
            record(_name_tokens(parent.id), parent.lineno)
        elif isinstance(parent, ast.Attribute):
            record(_name_tokens(parent.attr), parent.lineno)
        elif isinstance(parent, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            record(_name_tokens(parent.name), parent.lineno)
        elif (
            isinstance(parent, ast.Constant)
            and isinstance(parent.value, str)
            and id(parent) not in docstrings
        ):
            record(_name_tokens(parent.value), parent.lineno)
    return {name: sorted(lines) for name, lines in found.items()}


#: Splits a name wherever a reader would: at punctuation, at a camel-case hump, and between
#: letters and digits. `QwenSynthesisProvider`, `qwen_tts` and `"Qwen3-TTS"` all have to
#: reduce to `qwen`, because a concept that has spread through a codebase almost never
#: spread in one spelling — which is exactly why it is hard to notice by reading.
_TOKEN_BOUNDARY = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])"
)


def _name_tokens(text: str) -> set[str]:
    """Split an identifier or literal into comparable lower-case words."""

    spaced = _TOKEN_BOUNDARY.sub(" ", text)
    return {token.casefold() for token in re.split(r"[^A-Za-z0-9]+", spaced) if token}
