"""Shared AST and file-selection helpers for Python repository analysis.

The analyzer core and the boundary-preparation detectors both need to walk one
lexical body, find the syntax behind an Atlas node, and mint an edge. Keeping these
here lets the detectors live in their own module without either importing the other.

The subtree-exclusion pair is here for the same reason: the analyzer and the type
resolver each build their own file list, and they have to leave out the same files or
the resolver would answer about code the atlas has no nodes for.
"""

from __future__ import annotations

import ast
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from archcompass.analysis.atlas import AtlasEdge, AtlasNode, EdgeType, SourceLocation
from archcompass.records import stable_id


@dataclass
class ParsedModule:
    """One parsed source file and the Atlas identities derived from it."""

    path: Path
    relative_path: str
    qualified_name: str
    node: AtlasNode
    #: The parsed syntax, or `None` once it has been released. Released deliberately: a
    #: repository's worth of trees is ten to twenty times its source in memory, and almost
    #: everything that reads one is finished with it the moment its file has been turned
    #: into nodes. What still wants syntax afterwards asks `TreeSource`, which parses the
    #: file again and keeps a handful at a time.
    tree: ast.Module | None
    source: str
    symbols: dict[str, AtlasNode] = field(default_factory=dict[str, AtlasNode])
    import_aliases: dict[str, str] = field(default_factory=dict[str, str])

    def syntax(self) -> ast.Module:
        """The tree, for a caller that runs while it is still there.

        Everything reached from the parse loop is such a caller: the file has just been read
        and nothing has released it yet. Anything running after that loop asks `TreeSource`
        instead, which will parse the file again. Raising rather than returning `None` keeps
        those two worlds apart — a reader that gets here after the release is a bug in the
        order of the analysis, not a module that happens to have no syntax.
        """

        if self.tree is None:
            raise RuntimeError(
                f"The syntax of {self.relative_path} was released. Read it through "
                "TreeSource, which parses the file again."
            )
        return self.tree


def import_roots(relative_paths: Iterable[str]) -> frozenset[str]:
    """The directories that would be on `sys.path`, derived the way Python derives them.

    A file's package is the run of directories above it that each hold an `__init__.py`;
    the directory above *that* run is what an import statement counts from. So a `src`
    layout yields `{"src"}`, a flat repository yields `{""}`, and a repository that is
    itself a package yields `{""}` too, because its own root has no parent inside the
    snapshot.

    This exists because leaving it out silently gutted every src-layout repository — which
    is the modern default, and this project's own shape. `src/archcompass/analysis/atlas.py`
    was named `src.archcompass.analysis.atlas`, no import statement anywhere says that, so
    every import edge failed to resolve: analysed from its own root this repository showed
    **95 import edges instead of 454**, and with them went every cyclic-dependency and
    concentrated-scope signal and the whole dependency and change-amplification metric
    families. The atlas looked complete and was not.

    No configuration is read. A `pyproject.toml` can say where the packages are, but the
    directories themselves already say it, and a rule that reads the repository's own
    configuration is a rule that behaves differently for repositories that have none.
    """

    paths = tuple(relative_paths)
    packages = {
        path.rsplit("/", 1)[0] if "/" in path else ""
        for path in paths
        if path.endswith("/__init__.py") or path == "__init__.py"
    }
    holds_a_package = {
        package.rsplit("/", 1)[0] for package in packages if "/" in package
    } | {"" for package in packages if "/" not in package}
    roots: set[str] = set()
    for path in paths:
        directory = path.rsplit("/", 1)[0] if "/" in path else ""
        # Climb while each directory is a package. The first one that is not is where an
        # import would count from — but only if it holds a package at all.
        #
        # That last clause is the difference between `src` and `tests`. A `src` directory
        # exists to put packages on the path, so it is an import root. A `tests` directory
        # with no `__init__.py` holds loose modules, and calling it a root would rename
        # `tests.test_scheduler` to `test_scheduler` — losing where the module lives, and
        # with it the identity of every candidate that names it. Python itself would import
        # it that way under a rootdir insertion; an atlas of a repository should not.
        while directory and directory in packages:
            directory = directory.rsplit("/", 1)[0] if "/" in directory else ""
        roots.add(directory if directory in holds_a_package else "")
    return frozenset(roots)


def module_name(relative_path: str, roots: frozenset[str] = frozenset()) -> str:
    """The dotted name a repository-relative source path is imported under.

    Shared with the type-aware resolver, which has to hand the same names to its backend or
    the qualified names it answers with will not line up with the atlas's own.

    `roots` comes from `import_roots`. Empty — the default — names the path from the
    repository root, which is right for a flat layout and is what every caller did before
    `src` layouts were handled.
    """

    trimmed = relative_path
    for root in sorted(roots, key=len, reverse=True):
        if root and relative_path.startswith(f"{root}/"):
            trimmed = relative_path[len(root) + 1 :]
            break
    parts = trimmed.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or "__root__"


def canonical_roots(roots: Iterable[Path]) -> tuple[Path, ...]:
    """Excluded subtrees as absolute, symlink-free paths, resolved once."""

    return tuple(sorted(root.expanduser().resolve() for root in roots))


def excluded_within(root: Path, excluded_roots: tuple[Path, ...]) -> tuple[Path, ...]:
    """The excluded subtrees that lie strictly inside this repository.

    A root equal to or containing the repository is dropped rather than honoured. The
    ArchCompass workspace is excluded so that a repository holding one can still be
    analysed; a workspace that *is* the repository, or that has the repository inside it,
    would exclude every file and leave an empty atlas — which is a worse answer than
    indexing the tool's own state, and not the question the caller asked.
    """

    return tuple(
        excluded
        for excluded in excluded_roots
        if excluded != root and excluded.is_relative_to(root)
    )


def lies_within(path: Path, roots: tuple[Path, ...]) -> bool:
    """Whether a file sits under one of these subtrees, symlinked parents included.

    Resolved rather than compared as written, so a subtree reached through a symlinked
    parent is still recognised. Only reached when something is excluded, because it costs a
    syscall per file.
    """

    if not roots:
        return False
    canonical = path.resolve()
    return any(canonical.is_relative_to(root) for root in roots)


def lexical_nodes(syntax: ast.AST) -> Iterable[ast.AST]:
    """Walk one lexical body while treating nested definitions as opaque.

    A function's signature is part of it. Seeding from `body` alone left every parameter
    annotation and every return annotation outside the walk, so a name a function was
    written entirely in terms of was not a name it referenced — and the shape that hides
    is the one this codebase is built from. `class Runtime: lineage: LineageRepository`
    was seen, because a class attribute's annotation is a statement in the body;
    `def __init__(self, source_repository: PolicySourceRepository)` was not, because a
    parameter's is not. So the ports declared as dataclass fields had dependants and the
    ports injected through constructors had none, and `dependants_of_abstraction` reported
    zero for most of the ports in the repository while every one of them was wired.

    Decorators are still left out. A decorator names something the definition is passed
    to rather than something its body is written in terms of, and pulling it in here would
    change what a reference means as well as how many there are.
    """

    boundaries = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    if isinstance(syntax, (ast.FunctionDef, ast.AsyncFunctionDef)):
        signature: list[ast.AST] = [syntax.args]
        if syntax.returns is not None:
            signature.append(syntax.returns)
        stack: list[ast.AST] = list(reversed([*signature, *syntax.body]))
    elif isinstance(syntax, (ast.Module, ast.ClassDef)):
        stack = list(reversed(syntax.body))
    else:
        stack = list(reversed(list(ast.iter_child_nodes(syntax))))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, boundaries):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


class DefinitionIndex:
    """Every definition in a module, found by where it starts and what it is called.

    The same answer `ast_for_node` gives, asked once per module instead of once per node.
    That function walks the whole tree on every call, and it is called for each node in the
    file — so a module with two hundred symbols walked its own tree two hundred times, and
    the cost of a repository was the number of its symbols times the size of its trees.

    First match in `ast.walk` order wins, exactly as the linear scan did: two definitions can
    share a line and a name — a decorated function inside a conditional, most often — and
    which one was returned is behaviour, not an accident to be tidied up.

    Keyed by `id(module)`, which is only sound because an instance of this class lives inside
    one call and every `ParsedModule` it sees is held alive for that whole call by the
    caller's own map. An index promoted to instance or module scope would outlive the modules
    it cached, and CPython would hand a recycled id to a different object: not a crash, but a
    wrong answer, silently. Build one per analysis and let it go with the analysis.
    """

    def __init__(self) -> None:
        self._by_module: dict[int, dict[tuple[int | None, str], ast.AST]] = {}

    def get(self, module: ParsedModule | None, node: AtlasNode) -> ast.AST | None:
        if module is None or module.tree is None:
            return None
        if node.atlas_id == module.node.atlas_id:
            return module.tree
        return self._definitions(module).get((node.start_line, node.symbol_name))

    def _definitions(self, module: ParsedModule) -> dict[tuple[int | None, str], ast.AST]:
        cached = self._by_module.get(id(module))
        if cached is not None:
            return cached
        found: dict[tuple[int | None, str], ast.AST] = {}
        for item in ast.walk(module.tree or ast.Module(body=[], type_ignores=[])):
            if not isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            found.setdefault((item.lineno, item.name), item)
        self._by_module[id(module)] = found
        return found


class TreeSource:
    """Syntax for a module whose tree was released, parsed again and not kept for long.

    The comparisons that outlive a file — a protocol's method against a candidate's, one
    implementation's shape against another's — are the only readers left that need syntax
    after the parse loop, and they need two files at a time rather than all of them. So the
    trees go, and this brings back the few that are asked for.

    Parsing a file again costs milliseconds and the analysis is no longer short of time; a
    repository's worth of retained trees costs hundreds of megabytes and the container is
    short of those. `limit` is what bounds the trade: small enough that the cache is not the
    thing it replaced, large enough that a pairwise comparison never evicts its own operand.
    """

    def __init__(self, modules: list[ParsedModule], *, limit: int = 8) -> None:
        self._by_path = {module.relative_path: module for module in modules}
        self._limit = limit
        self._live: OrderedDict[str, ParsedModule] = OrderedDict()

    def for_path(self, relative_path: str | None) -> ParsedModule | None:
        if relative_path is None:
            return None
        module = self._by_path.get(relative_path)
        if module is None:
            return None
        if module.tree is None:
            # The same refusals the first parse made, made again. A file that would not
            # parse then will not parse now, and a caller asking for one must get the
            # absence rather than an exception thrown from somewhere it cannot expect —
            # the first parse reports an unreadable module as a signal and carries on,
            # and a second parse that killed the analysis instead would undo that.
            try:
                module.tree = ast.parse(
                    module.path.read_bytes().decode("utf-8", errors="replace"),
                    filename=module.relative_path,
                    type_comments=True,
                )
            except (SyntaxError, RecursionError, MemoryError, OSError):
                return None
        self._live[relative_path] = module
        self._live.move_to_end(relative_path)
        while len(self._live) > self._limit:
            _, evicted = self._live.popitem(last=False)
            evicted.tree = None
        return module


def ast_for_node(module: ParsedModule | None, node: AtlasNode) -> ast.AST | None:
    """The syntax an Atlas node was derived from, when it is still resolvable."""

    if module is None or module.tree is None:
        return None
    if node.atlas_id == module.node.atlas_id:
        return module.tree
    for item in ast.walk(module.tree):
        if not isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if item.lineno == node.start_line and item.name == node.symbol_name:
            return item
    return None


def build_edge(
    source: str | None,
    target: str,
    kind: EdgeType,
    *,
    confidence: float = 1.0,
    path: str | None = None,
    line: int | None = None,
    resolved_by: Literal["parse", "types"] = "parse",
    conformance: Literal["strict", "structural"] | None = None,
) -> AtlasEdge:
    if source is None:
        raise ValueError("Atlas edge source cannot be absent")
    location = (
        SourceLocation(path=path, start_line=line, end_line=line)
        if path is not None and line is not None
        else None
    )
    # Provenance is deliberately outside the identity. The two passes that can produce a
    # structural `IMPLEMENTS` edge never both run, so an edge at one site is one edge, and
    # keying on the pass would make an atlas rebuilt with the extra installed look like it
    # had gained edges it had merely re-derived.
    return AtlasEdge(
        edge_id=stable_id("edge", source, target, kind, path or "", str(line or 0)),
        source_id=source,
        target_id=target,
        edge_type=kind,
        confidence=confidence,
        location=location,
        resolved_by=resolved_by,
        conformance=conformance,
    )
