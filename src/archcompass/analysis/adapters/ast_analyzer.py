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

from archcompass.analysis.adapters.ast_support import (
    DefinitionIndex,
    ParsedModule,
    TreeSource,
    ast_for_node,
    build_edge,
    canonical_roots,
    excluded_within,
    lexical_nodes,
    lies_within,
    module_name,
)
from archcompass.analysis.adapters.boundary_signals import (
    add_structural_protocol_edges,
    broad_input_boundary_preparation_signals,
    parallel_boundary_preparation_signals,
)
from archcompass.analysis.adapters.concentration_signals import (
    concentrated_scope_signals,
)
from archcompass.analysis.adapters.graph import (
    maximum_reachable_depth,
    reachable,
    reverse_graph,
    strongly_connected_components,
)
from archcompass.analysis.atlas import (
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
from archcompass.analysis.scope import CONFIG_SUFFIXES, IGNORED_DIRECTORIES, excludes
from archcompass.domain.errors import PathValidationError
from archcompass.ports.atlas import (
    ConformanceQuestion,
    EdgeResolutionRequest,
    EdgeResolver,
    ReferenceQuestion,
)
from archcompass.records import canonical_json, stable_id

# v4 records per-module facts (constants stated, repository modules named). An atlas built
# by v3 has none, so it is stale rather than quietly missing them, and is re-analyzed.
#
# v5 gives each mention the lines it occurs on. A v4 atlas records that a module names a
# concept and not where, which left a scattered-concept participant with no span to point at
# — it said line 1, and line 1 of a Python file is the docstring, so the code shown as
# evidence of a leaked name was a docstring that did not contain it. Nothing can recover the
# positions from a stored v4 atlas, so it is stale and re-analyzed rather than read with the
# lines missing. Re-analysis is cheap and lossless because an atlas is derived.
#
# v6 emits the `concentrated-scope` signal. Signals are stored, not recomputed on read, so a
# v5 atlas of unchanged source would go on reporting nothing about concentration and give a
# reader no way to tell that from a repository with none. Same rule as above: a stored atlas
# that cannot answer a question the analyzer now answers is stale.
PARSER_VERSION = "python-ast-3.12-v6"


@dataclass(frozen=True)
class AnalysisLimits:
    """How much repository an analysis will take on, where something has to say.

    Absent by default, which is what a workspace on somebody's own machine wants: they
    chose the directory, it is their memory being spent, and a cap that silently dropped
    half their code would be worse than a slow run.

    A deployment that analyses repositories strangers name needs the opposite. Every file
    is read whole into memory and every parsed module is held for the length of the run,
    so without a limit the size of the analysis is the size of whatever was pointed at —
    and on a container whose filesystem is memory, one repository is enough to end every
    session on the instance.
    """

    #: Files larger than this are left out. A source file this big is machine-generated or
    #: is not source at all, and neither is something a review has anything to say about.
    max_file_bytes: int | None = None
    #: How many files are taken in total, Python and configuration together.
    max_files: int | None = None
    #: How many atlas nodes one repository may produce. The cap that measures what is
    #: actually being spent: memory runs at roughly forty kilobytes a node, and a node is a
    #: module, a class, a function or a method rather than a megabyte of anything. Repository
    #: density varies fourfold — psf/black carries about 430 nodes per megabyte of Python and
    #: sqlalchemy about 1,975 — so the byte cap below cannot see the difference between a
    #: repository that will fit and one four times heavier, and this one can.
    #:
    #: Checked while the parse runs rather than afterwards, because afterwards is after the
    #: memory was spent.
    max_nodes: int | None = None
    #: How much Python one repository may contribute, in bytes. The cap that matters most,
    #: and the one that is refused rather than trimmed: leaving half a repository out would
    #: produce an atlas with holes in it and a review confidently wrong about what is there.
    #:
    #: Sized from measurement rather than from a round number. Peak memory runs at roughly
    #: 48 MB per megabyte of Python — pallets/flask at 0.6 MB peaks at 142 MB, psf/black at
    #: 5.2 MB peaks at 361 MB — because `_compute_metrics` is O(nodes x edges) and holds
    #: every parsed tree while it runs. django/django, at 30 MB, passed 814 MB and had not
    #: finished after twelve minutes. Until that loop is not quadratic, the honest thing is
    #: to say no to the repositories it cannot finish.
    max_python_bytes: int | None = None
    #: Whether `.env` files are read into the atlas. True everywhere a person is reviewing
    #: their own code, where the file is part of how the repository is configured and is
    #: exactly the kind of thing a review should be able to point at.
    #:
    #: False where the repository belongs to somebody who is only passing through. An
    #: excerpt of a `.env` reaches the model provider like any other file, and a demo that
    #: forwarded a stranger's secrets to a third party because they pasted a URL would be
    #: doing something they never asked for and would have no way to notice.
    include_environment_files: bool = True

    def __bool__(self) -> bool:
        return (
            self.max_file_bytes is not None
            or self.max_files is not None
            or self.max_nodes is not None
            or self.max_python_bytes is not None
            or not self.include_environment_files
        )


#: No ceiling at all, which is what every caller that does not ask for one gets. A singleton
#: because it is immutable and there is only one way to have no limits.
UNLIMITED_ANALYSIS = AnalysisLimits()


#: What the hash records when no resolver is configured. A marker rather than an omitted
#: key: an atlas built with typed edges and one built without them are different atlases,
#: and leaving the key out when the extra is absent would let the second be read as the
#: first the moment the extra is installed.
_RESOLUTION_ABSENT = "absent"


def _error_line(error: BaseException) -> int:
    """Which line to point the unreadable-module signal at.

    A `SyntaxError` names one. The exhaustion errors that reach the same handler do not —
    there is no single line that was too deeply nested — so they point at the top of the
    file, which is where a reader opening it would start anyway.
    """

    lineno = getattr(error, "lineno", None)
    return max(1, lineno if isinstance(lineno, int) else 1)


def _analysis_config_hash(
    resolution: Mapping[str, str] | None = None,
    limits: AnalysisLimits = UNLIMITED_ANALYSIS,
) -> str:
    recorded: dict[str, object] = {
        "ignored": sorted(IGNORED_DIRECTORIES),
        "config_suffixes": sorted(CONFIG_SUFFIXES),
        "parser": PARSER_VERSION,
        "resolution": (
            dict(sorted(resolution.items()))
            if resolution is not None
            else _RESOLUTION_ABSENT
        ),
    }
    # Recorded only where there are limits, so that an unlimited analysis hashes to exactly
    # what it always did. An atlas built under a cap genuinely is a different atlas — it may
    # be missing files — and has to be told apart from one built without; an atlas built
    # without a cap is the same one it was before this key existed, and making every stored
    # atlas stale to say so would be a re-analysis of every workspace for no new fact.
    if limits:
        recorded["limits"] = {
            "max_file_bytes": limits.max_file_bytes,
            "max_files": limits.max_files,
            "max_nodes": limits.max_nodes,
            "max_python_bytes": limits.max_python_bytes,
            "environment_files": limits.include_environment_files,
        }
    return stable_id("analysis", canonical_json(recorded))


@dataclass(frozen=True)
class SnapshotFile:
    """One file of the repository, read when it is wanted rather than kept.

    Held as a path and not as bytes. Every file of a repository read into memory at once and
    kept there for the length of the run is a copy of the repository sitting beside the
    parsed trees, and neither the fingerprint nor the parse needs it to be: the fingerprint
    reads each file in turn and keeps only the digest, and the parse reads a file, turns it
    into nodes, and has no further use for the text.
    """

    path: Path
    relative_path: str

    def text(self) -> str:
        """The file as text, read now, with whatever is not UTF-8 replaced rather than raised.

        A repository is allowed to contain a file that is not UTF-8 — a fixture of raw
        bytes under a `.json` suffix, a `.py` saved in a legacy encoding — and strict
        decoding made one such file end the analysis of everything around it. Replaced,
        the file is still hashed as the bytes it is, still counted, and still parsed: if
        the substitution broke the syntax, that is a `SyntaxError`, which this analyzer
        already reports as a signal rather than a failure.
        """

        return self.path.read_bytes().decode("utf-8", errors="replace")


@dataclass(frozen=True)
class _Reference:
    """One name a module wrote, and what kind of edge it would be if it resolves.

    Read out of the tree while the file is in hand, resolved later against the symbol table
    of the whole repository. The two cannot happen together — a name is only unambiguous once
    every file has been read — and keeping them together is what used to require every tree
    to stay in memory until the last file was parsed.
    """

    source: AtlasNode
    line: int
    expression: str
    kind: EdgeType


@dataclass(frozen=True)
class _ModuleReferences:
    """Everything one module names, in the order it named it.

    Order is preserved because edge identity is not the only thing that matters: the first
    edge recorded between a pair of nodes is the one `_deduplicate_edges` keeps, so replaying
    these in a different order than they were read would keep a different edge.
    """

    imports: tuple[tuple[str, int], ...]
    references: tuple[_Reference, ...]


@dataclass(frozen=True)
class _SyntacticMetrics:
    """What a node's own syntax says about it, with nothing about the rest of the repository.

    Split out because the two halves of `LocalStructuralMetrics` become knowable at different
    moments: everything here is readable from the node's own tree the instant it is parsed,
    while how many calls go out of it and come into it is a fact about the resolved edge
    graph and cannot be known until every file has been read.

    Recording this half early is what lets a tree be released as soon as its file is done,
    rather than every tree being held until the last one is.
    """

    physical_lines: int = 0
    logical_statements: int = 0
    branch_count: int = 0
    maximum_nesting_depth: int = 0
    parameter_count: int = 0
    public_symbol_count: int = 0
    imported_module_count: int = 0


@dataclass(frozen=True)
class _ModuleMetrics:
    """What every node in one module shares, computed once for all of them.

    Frozen, and holding frozensets rather than sets, because one instance is handed to every
    node in its module: a caller that mutated what it was given would be editing the metrics
    of every symbol in the file.
    """

    direct_dependencies: list[str]
    direct_dependants: list[str]
    forward: frozenset[str]
    backward: frozenset[str]
    affected: frozenset[str]
    component: list[str]
    depth: int
    reverse_tests: frozenset[str]
    crossed_interfaces: frozenset[str]


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
        limits: AnalysisLimits = UNLIMITED_ANALYSIS,
    ) -> None:
        self._edge_resolver = edge_resolver
        self._limits = limits
        # Canonicalized once, and never folded into the analysis config hash: an excluded
        # root is where this machine happens to keep its workspace, exactly like `root_path`,
        # and hashing it would make two machines analysing the same commit disagree about
        # whether a stored atlas is stale.
        self._excluded_roots = canonical_roots(excluded_roots)

    def analyze(self, root: Path, *, excluded_paths: tuple[str, ...] = ()) -> Atlas:
        """The atlas of this repository, less whatever subtrees the caller asked to leave out.

        `excluded_paths` arrives already validated (see `domain.scope`) and relative to the
        root. It is deliberately not part of the analysis configuration hash: the files it
        leaves out never reach the digest, so the content fingerprint already says that this
        is an atlas of a different set of files. Hashing it as well would say the same thing
        twice, and would make an unscoped analysis hash differently than it always has.
        """

        snapshot = self._snapshot(root, excluded_paths)
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

        # Complete before the first parse, because it is a fact about which files exist
        # rather than about what any of them contain.
        owned_names = self._owned_names([item.path for item in python_files])
        module_facts: list[ModuleFacts] = []
        syntactic_metrics: dict[str, _SyntacticMetrics] = {}
        references_by_path: dict[str, _ModuleReferences] = {}
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
            # Between files rather than inside one: a module is the smallest thing this can
            # stop at without leaving a half-read file behind, and one module is not what
            # takes a run past the limit.
            # Recorded while this module's tree is the one in hand. Everything below this
            # line is about the repository rather than about a file, and none of it reads a
            # tree — which is what makes it possible to stop holding them.
            module_facts.append(self._facts_for(parsed, owned_names))
            references_by_path[parsed.relative_path] = self._module_references(parsed)
            definitions = DefinitionIndex()
            for owned_node in (parsed.node, *parsed.symbols.values()):
                syntactic_metrics[owned_node.atlas_id] = self._syntactic_metrics(
                    owned_node, definitions.get(parsed, owned_node)
                )
            # Everything this file had to say has been said. Holding its tree from here to
            # the end of the run is what made the cost of an analysis the size of the whole
            # repository rather than the size of its largest file.
            parsed.tree = None
            parsed.source = ""
            self._refuse_if_too_many_nodes(len(nodes))

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
        # Built once for the whole repository, not once per module: it is a view of every
        # symbol there is, and rebuilding it per file would put back the cost it removes.
        suffix_index = self._suffix_index(symbol_by_qualified)
        # The few readers that still want syntax after the parse loop get it from here,
        # which parses a file again rather than having kept it.
        trees = TreeSource(modules)
        unresolved: list[UnresolvedSite] = []
        for module in modules:
            self._edges_from_references(
                module,
                references_by_path[module.relative_path],
                module_by_name,
                symbol_by_qualified,
                suffix_index,
                edges,
                unresolved,
            )
        # Exactly one source of structural `IMPLEMENTS` edges. The heuristic guesses from
        # names and annotations at 0.8; the typed sweep answers the same question from the
        # type checker's own view. Running both would double every agreed pair and leave a
        # reader unable to say which pass believed what.
        if self._edge_resolver is None:
            add_structural_protocol_edges(nodes, edges, trees)
        else:
            unresolved = self._apply_resolution(
                self._edge_resolver, canonical_root, nodes, edges, unresolved
            )
        signals.extend(self._unresolved_call_signals(unresolved))
        edges = self._deduplicate_edges(edges)
        self._add_duplicate_constant_signals(module_facts, signals)
        signals.extend(
            broad_input_boundary_preparation_signals(
                nodes,
                edges,
                trees,
            )
        )
        signals.extend(
            parallel_boundary_preparation_signals(
                nodes,
                edges,
                trees,
            )
        )
        metrics = self._compute_metrics(nodes, edges, modules, syntactic_metrics)
        # After the metrics rather than beside the other signals, because it is derived from
        # them: concentration is a statement about a module's surface and its dependants,
        # both of which are already counted above.
        signals.extend(concentrated_scope_signals(nodes, metrics))
        signals.extend(self._cycle_signals(nodes, edges, modules))
        return Atlas(
            version=version,
            nodes=sorted(nodes.values(), key=lambda item: item.atlas_id),
            edges=sorted(edges, key=lambda item: item.edge_id),
            metrics=sorted(metrics, key=lambda item: item.node_id),
            signals=sorted(signals, key=lambda item: (item.node_id, item.code, item.message)),
            module_facts=sorted(module_facts, key=lambda item: item.node_id),
        )

    def current_identity(
        self, root: Path, *, excluded_paths: tuple[str, ...] = ()
    ) -> RepositoryContentIdentity:
        """What this repository would fingerprint as right now, under the same exclusions.

        The exclusions have to be the ones the atlas was built with, or the two fingerprints
        are digests of different file sets and the atlas is reported stale every time it is
        opened. That is why a selection is remembered rather than passed once: the caller
        that checks freshness is not the caller that chose the scope.
        """

        snapshot = self._snapshot(root, excluded_paths)
        return RepositoryContentIdentity(
            root_path=str(snapshot.root),
            content_fingerprint=snapshot.content_fingerprint,
            git_commit_sha=snapshot.git_commit_sha,
            parser_version=PARSER_VERSION,
            analysis_config_hash=self._config_hash(),
        )

    def _snapshot(
        self, root: Path, excluded_paths: tuple[str, ...] = ()
    ) -> RepositorySnapshot:
        canonical_root = self._validate_root(root)
        python_paths, config_paths = self._discover_files(canonical_root, excluded_paths)
        self._refuse_if_too_large(python_paths)
        files = tuple(
            SnapshotFile(
                path=path,
                relative_path=path.relative_to(canonical_root).as_posix(),
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

    def _refuse_if_too_many_nodes(self, counted: int) -> None:
        """Stop while there is still memory to stop in.

        Said in terms of what a reader can see — how much there is in the repository — rather
        than in terms of nodes, which is this program's word for it and not theirs.
        """

        cap = self._limits.max_nodes
        if cap is not None and counted > cap:
            raise PathValidationError(
                f"This repository has more in it than this workspace analyses: over {cap:,} "
                "modules, classes and functions. Run Arch Compass locally to review a "
                "repository this size."
            )

    def _refuse_if_too_large(self, python_paths: list[Path]) -> None:
        """Say no before reading anything, when this is more than can be finished.

        Measured from the directory entries rather than from the bytes, so a repository that
        is too big to analyse is refused without ever being loaded — the failure this avoids
        is running out of memory, and a check made after reading the files has already spent
        what it was protecting.

        Refused rather than truncated. An atlas built from the first N megabytes of a
        repository is an atlas with holes in it, and a review is a set of claims about what
        the code does: silently leaving half of it out would make those claims wrong in a way
        the reader could not see.
        """

        cap = self._limits.max_python_bytes
        if cap is None:
            return
        total = sum(path.stat().st_size for path in python_paths)
        if total > cap:
            raise PathValidationError(
                f"This repository has {total / (1024 * 1024):.0f} MB of Python in it, and "
                f"this workspace analyses up to {cap // (1024 * 1024)} MB. Run Arch Compass "
                "locally to review a repository this size."
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

    def _discover_files(
        self, root: Path, excluded_paths: tuple[str, ...] = ()
    ) -> tuple[list[Path], list[Path]]:
        # What an ArchCompass workspace holds — its database, its authored policies, its run
        # outputs — changes whenever a review runs. A workspace inside the analysed
        # repository would therefore move the content fingerprint on every run, leaving the
        # atlas permanently stale and filling it with the tool's own state, so it is left out
        # exactly like an ignored directory.
        excluded = excluded_within(root, self._excluded_roots)
        python_files: list[Path] = []
        config_files: list[Path] = []
        max_file_bytes = self._limits.max_file_bytes
        max_files = self._limits.max_files
        for path in sorted(root.rglob("*")):
            if max_files is not None and len(python_files) + len(config_files) >= max_files:
                break
            relative_parts = path.relative_to(root).parts
            if any(part in IGNORED_DIRECTORIES for part in relative_parts):
                continue
            # The caller's own exclusions, applied here and nowhere else, so that the
            # fingerprint, the node set and the freshness check are all computed over one
            # set of files by construction rather than by three call sites agreeing.
            if excludes(relative_parts, excluded_paths):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if lies_within(path, excluded):
                continue
            # Asked of the directory entry rather than of the bytes, so an oversized file
            # is never read at all — the cap exists to stop it being held in memory, and
            # measuring it after reading it would be measuring the damage.
            if max_file_bytes is not None and path.stat().st_size > max_file_bytes:
                continue
            if path.suffix == ".py":
                python_files.append(path)
            elif path.name == ".env":
                if self._limits.include_environment_files:
                    config_files.append(path)
            elif path.suffix.casefold() in CONFIG_SUFFIXES:
                config_files.append(path)
        return sorted(python_files), sorted(config_files)

    @staticmethod
    def _fingerprint(files: tuple[SnapshotFile, ...]) -> str:
        """One digest over every file, read one at a time and kept none.

        The order is the caller's — Python and configuration files interleaved by path — and
        it is load-bearing: this digest is what tells a stored atlas from a stale one, so a
        change to the order would mark every atlas in every workspace stale at once.
        """

        digest = sha256()
        for source_file in files:
            digest.update(source_file.relative_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(source_file.path.read_bytes())
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

        for statement in module.syntax().body:
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
        # `RecursionError` and `MemoryError` alongside `SyntaxError`: CPython's parser
        # recurses on nested expressions, so a file of ten thousand nested brackets is
        # syntactically valid and still cannot be parsed. Uncaught, one such file ends the
        # analysis of the repository around it, which is a denial of indexing that costs an
        # attacker one file. Reported as the same unreadable-module signal a syntax error is.
        except (SyntaxError, RecursionError, MemoryError) as error:
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
                        start_line=_error_line(error),
                        end_line=_error_line(error),
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
        for statement in parsed.syntax().body:
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
        for item in ast.walk(parsed.syntax()):
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

    def _module_references(self, module: ParsedModule) -> _ModuleReferences:
        """Every name this module writes, read from its tree and nothing else.

        The counterpart of `_edges_from_references`, which turns these into edges without a
        tree in sight. Split at exactly this line because everything above it is about one
        file and everything below it is about the repository.
        """

        imports: list[tuple[str, int]] = []
        for statement in module.syntax().body:
            if isinstance(statement, ast.Import):
                imports.extend((alias.name, statement.lineno) for alias in statement.names)
            elif isinstance(statement, ast.ImportFrom):
                imports.append((self._resolve_from_name(module, statement), statement.lineno))

        references: list[_Reference] = []
        for source_node in (module.node, *module.symbols.values()):
            ast_node = ast_for_node(module, source_node)
            if ast_node is None:
                continue
            scoped_nodes = list(lexical_nodes(ast_node))
            # Three passes over the same scope, in this order, because that is the order the
            # edges were built in and the first edge between a pair of nodes is the one kept.
            references.extend(
                _Reference(source_node, item.lineno, self._dotted(item.func), EdgeType.CALLS)
                for item in scoped_nodes
                if isinstance(item, ast.Call)
            )
            if isinstance(ast_node, ast.ClassDef):
                references.extend(
                    _Reference(
                        source_node, base.lineno, self._dotted(base), EdgeType.INHERITS
                    )
                    for base in ast_node.bases
                )
            references.extend(
                _Reference(source_node, item.lineno, item.id, EdgeType.REFERENCES)
                for item in scoped_nodes
                if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
            )
        return _ModuleReferences(imports=tuple(imports), references=tuple(references))

    def _edges_from_references(
        self,
        module: ParsedModule,
        recorded: _ModuleReferences,
        module_by_name: dict[str, ParsedModule],
        symbol_by_qualified: dict[str, AtlasNode],
        suffix_index: dict[str, list[AtlasNode]],
        edges: list[AtlasEdge],
        unresolved: list[UnresolvedSite],
    ) -> None:
        """Turn what a module named into edges, against the whole repository's symbols.

        Reads no syntax. Everything it needs about the module itself — what it is called,
        what it imported things as, which node it is — is carried on `ParsedModule` beside
        the tree, and survives the tree being released.
        """

        for imported_name, line in recorded.imports:
            target = self._best_module(imported_name, module_by_name)
            if not target:
                continue
            import_edge = build_edge(
                module.node.atlas_id,
                target.node.atlas_id,
                EdgeType.IMPORTS,
                path=module.relative_path,
                line=line,
            )
            edges.append(import_edge)
            # A test importing a module is a test of it, and a configuration module
            # importing one configures it. The same edge, said again under another name.
            for derived, when in (
                (EdgeType.TESTS, NodeType.TEST_MODULE),
                (EdgeType.CONFIGURES, NodeType.CONFIGURATION),
            ):
                if module.node.node_type is not when:
                    continue
                edges.append(
                    import_edge.model_copy(
                        update={
                            "edge_id": stable_id(
                                "edge",
                                module.node.atlas_id,
                                target.node.atlas_id,
                                derived,
                                module.relative_path,
                                str(line),
                            ),
                            "edge_type": derived,
                        }
                    )
                )

        for reference in recorded.references:
            source_node = reference.source
            target, confidence = self._resolve_symbol(
                reference.expression, source_node, module, symbol_by_qualified, suffix_index
            )
            if reference.kind is EdgeType.CALLS:
                if target:
                    edges.append(
                        build_edge(
                            source_node.atlas_id,
                            target.atlas_id,
                            EdgeType.CALLS,
                            confidence=confidence,
                            path=module.relative_path,
                            line=reference.line,
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
                                line=reference.line,
                            )
                        )
                elif reference.expression:
                    unresolved.append(
                        UnresolvedSite(
                            source=source_node,
                            module_path=module.relative_path,
                            line=reference.line,
                            expression=reference.expression,
                            edge_type=EdgeType.CALLS,
                        )
                    )
            elif reference.kind is EdgeType.INHERITS:
                if target:
                    edges.append(
                        build_edge(
                            source_node.atlas_id,
                            target.atlas_id,
                            EdgeType.INHERITS,
                            confidence=confidence,
                            path=module.relative_path,
                            line=reference.line,
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
                                line=reference.line,
                            )
                        )
            else:
                if target is None:
                    unresolved.append(
                        UnresolvedSite(
                            source=source_node,
                            module_path=module.relative_path,
                            line=reference.line,
                            expression=reference.expression,
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
                        line=reference.line,
                    )
                )

    def _config_hash(self) -> str:
        return _analysis_config_hash(
            self._edge_resolver.fingerprint() if self._edge_resolver is not None else None,
            self._limits,
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
        syntactic: dict[str, _SyntacticMetrics],
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
        profiles: list[MetricProfile] = []
        # Everything a node's metrics need beyond the node itself is a property of the module
        # it lives in — its dependencies, what it reaches, what reaches it, the interfaces
        # crossed to get there. Computed once per module rather than once per node, because
        # the two differ by a factor of the symbols in a file: a repository with fifty
        # thousand nodes has under three thousand modules, and the edge scan behind
        # `crossed_interfaces` was being repeated for every one of the fifty thousand.
        #
        # Memoised rather than restructured into a separate loop so the reading order of this
        # function is unchanged. The cached sets are read and copied, never mutated, so
        # handing the same object to every node in a module is safe.
        by_module: dict[str | None, _ModuleMetrics] = {}

        def module_metrics(owner: str | None) -> _ModuleMetrics:
            cached = by_module.get(owner)
            if cached is not None:
                return cached
            if owner is None:
                # A node outside every module reaches nothing and is reached by nothing, so
                # every one of these is empty by construction. Short-circuited rather than
                # computed, which also spares the guaranteed-empty scan over all edges.
                computed = _ModuleMetrics(
                    direct_dependencies=[],
                    direct_dependants=[],
                    forward=frozenset(),
                    backward=frozenset(),
                    affected=frozenset(),
                    component=[],
                    depth=0,
                    reverse_tests=frozenset(),
                    crossed_interfaces=frozenset(),
                )
            else:
                affected_here = reachable(impact_reverse, owner)
                affected_modules = {*affected_here, owner}
                computed = _ModuleMetrics(
                    direct_dependencies=sorted(module_graph.get(owner, set())),
                    direct_dependants=sorted(reverse.get(owner, set())),
                    forward=frozenset(reachable(module_graph, owner)),
                    backward=frozenset(reachable(reverse, owner)),
                    affected=frozenset(affected_here),
                    component=component_by_node.get(owner, []),
                    depth=maximum_reachable_depth(module_graph, owner),
                    reverse_tests=frozenset(
                        candidate
                        for candidate in affected_here
                        if nodes[candidate].node_type == NodeType.TEST_MODULE
                    ),
                    crossed_interfaces=frozenset(
                        edge.target_id
                        for edge in edges
                        if edge.edge_type == EdgeType.CALLS
                        and self._owning_module(nodes[edge.source_id], module_for_path)
                        in affected_modules
                        and self._owning_module(nodes[edge.target_id], module_for_path)
                        in affected_modules
                        and nodes[edge.target_id].is_public
                        and nodes[edge.target_id].node_type
                        in {
                            NodeType.CLASS,
                            NodeType.FUNCTION,
                            NodeType.INTERFACE,
                            NodeType.METHOD,
                        }
                    ),
                )
            by_module[owner] = computed
            return computed

        for node in nodes.values():
            owner = self._owning_module(node, module_for_path)
            shared = module_metrics(owner)
            direct_dependencies = shared.direct_dependencies
            direct_dependants = shared.direct_dependants
            forward = shared.forward
            backward = shared.backward
            affected = shared.affected
            component = shared.component
            associated_tests: set[str | None] = {
                self._owning_module(nodes[test_id], module_for_path)
                for test_id in test_targets.get(node.atlas_id, set())
            }
            reverse_tests = shared.reverse_tests
            # A node with nothing recorded is one with no syntax of its own to record: the
            # repository root, a package, a configuration file. It still has a span, and the
            # span is what its size has always been measured as — computed here rather than
            # defaulted to zero, which silently shrank every configuration file to nothing.
            recorded = syntactic.get(node.atlas_id)
            if recorded is None:
                recorded = self._syntactic_metrics(node, None)
            local = LocalStructuralMetrics(
                physical_lines=recorded.physical_lines,
                logical_statements=recorded.logical_statements,
                branch_count=recorded.branch_count,
                maximum_nesting_depth=recorded.maximum_nesting_depth,
                parameter_count=recorded.parameter_count,
                public_symbol_count=recorded.public_symbol_count,
                imported_module_count=recorded.imported_module_count,
                outgoing_static_calls=len(call_outgoing[node.atlas_id]),
                incoming_known_callers=len(call_incoming[node.atlas_id]),
            )
            representative_path = self._representative_call_path(call_outgoing, node.atlas_id)
            crossed_interfaces = shared.crossed_interfaces
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
                        dependency_depth=shared.depth,
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

    def _syntactic_metrics(
        self,
        node: AtlasNode,
        syntax: ast.AST | None,
    ) -> _SyntacticMetrics:
        if syntax is None:
            return _SyntacticMetrics(
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
        return _SyntacticMetrics(
            physical_lines=(node.end_line or 0) - (node.start_line or 1) + 1
            if node.end_line
            else 0,
            logical_statements=statements,
            branch_count=branches,
            maximum_nesting_depth=self._nesting_depth(syntax),
            parameter_count=parameters,
            public_symbol_count=public_symbols,
            imported_module_count=len(imports),
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
    def _suffix_index(symbols: dict[str, AtlasNode]) -> dict[str, list[AtlasNode]]:
        """Every dotted tail a qualified name has, and what answers to it.

        The last resort in `_resolve_symbol` is "one symbol in this repository ends with the
        name that was written", and it used to be asked by scanning every symbol for every
        reference. That is the size of the repository multiplied by the number of names in
        it: on psf/black it was fifty-six million string comparisons and two thirds of the
        whole analysis.

        Asked instead of a table built once. A name has as many tails as it has segments —
        `a.b.c` answers to `.b.c` and `.c` — so the table costs a few entries per symbol and
        replaces the scan with a lookup. Only the tails matter, because the scan it replaces
        matched on a leading dot: a reference never resolves against a partial segment.
        """

        index: dict[str, list[AtlasNode]] = {}
        for qualified, node in symbols.items():
            segments = qualified.split(".")
            for start in range(1, len(segments)):
                index.setdefault("." + ".".join(segments[start:]), []).append(node)
        return index

    @staticmethod
    def _resolve_symbol(
        dotted: str,
        source: AtlasNode,
        module: ParsedModule,
        symbols: dict[str, AtlasNode],
        suffixes: dict[str, list[AtlasNode]],
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
        # Unambiguous or nothing: a name that two symbols answer to is not evidence about
        # either of them, which is why this asks for exactly one and is why the index can
        # hold lists without needing them ordered.
        matches = suffixes.get(f".{dotted}", ())
        if len(matches) == 1:
            return matches[0], 0.7
        return None, 0

    @staticmethod
    def _deduplicate_edges(edges: list[AtlasEdge]) -> list[AtlasEdge]:
        return list({edge.edge_id: edge for edge in edges}.values())

    @staticmethod
    def _owning_module(node: AtlasNode, modules: dict[str, str]) -> str | None:
        return modules.get(node.path)

    @staticmethod
    def _owned_names(paths: list[Path]) -> set[str]:
        """The module names this repository owns, known from the file list alone.

        Bounded to names this repository owns. Recording every token a file contains would
        make the atlas a copy of the source; recording only the names that could refer to
        something here keeps it a set of relationships.

        Derived from paths rather than from parsed modules so that it is complete before the
        first file is parsed — which is what lets a module's facts be recorded while its tree
        is in hand, instead of holding every tree until the last one has been read.
        """

        return {path.stem.casefold() for path in paths if not path.stem.startswith("_")}

    @staticmethod
    def _facts_for(module: ParsedModule, owned: set[str]) -> ModuleFacts:
        """What one module states, and which of this repository's modules it names.

        Both halves are facts about a file's whole text rather than about any symbol in it,
        which is why they are recorded here and not on a node. Neither is a judgement: two
        modules sharing a constant may be a coincidence, and naming another module is
        ordinarily how code works. Deciding which of those matter is the detector's job.
        """

        return ModuleFacts(
            node_id=module.node.atlas_id,
            path=module.relative_path,
            qualified_name=module.qualified_name,
            constants=_declared_constants(module),
            mentions=_owned_mentions(module, owned),
        )

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
    for statement in module.syntax().body:
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
        for node in ast.walk(module.syntax())
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

    for parent in ast.walk(module.syntax()):
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
